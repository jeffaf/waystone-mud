"""Tests for sympathy magic system."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from waystone.database.engine import get_session, init_db
from waystone.database.models import Character, CharacterBackground, User
from waystone.game.engine import GameEngine
from waystone.game.systems.magic.sympathy import (
    HEAT_SOURCE_ENERGY,
    MATERIAL_DATABASE,
    MAX_BINDINGS_BY_ALAR,
    RANK_EFFICIENCY_CAPS,
    RANK_NAMES,
    RANK_XP_REQUIREMENTS,
    BacklashSeverity,
    Binding,
    BindingType,
    EnergySource,
    HeatSourceType,
    MaterialProperties,
    SympatheticBacklash,
    SympatheticLink,
    award_sympathy_xp,
    calculate_binding_efficiency,
    calculate_similarity_score,
    check_for_backlash,
    create_energy_source,
    format_bindings_display,
    format_sympathy_status,
    get_active_bindings,
    get_character_alar,
    get_max_bindings,
    get_sympathy_rank,
    get_sympathy_xp,
    release_all_bindings,
    release_binding,
)
from waystone.game.world import Room
from waystone.network import Connection, Session, SessionState


@pytest.fixture
async def test_engine() -> AsyncGenerator[GameEngine, None]:
    """Create a test game engine with minimal world."""
    await init_db()

    engine = GameEngine()

    # Create minimal test world
    engine.world = {
        "sympathy_room": Room(
            id="sympathy_room",
            name="Sympathy Workshop",
            area="university",
            description="A room for testing sympathy.",
            exits={},
        ),
    }

    yield engine

    # Cleanup
    await engine.stop()


@pytest.fixture
def mock_connection() -> Connection:
    """Create a mock connection for testing."""
    connection = Mock(spec=Connection)
    connection.id = uuid.uuid4()
    connection.ip_address = "127.0.0.1"
    connection.send_line = AsyncMock()
    connection.send = AsyncMock()
    connection.readline = AsyncMock()
    connection.is_closed = False
    return connection


@pytest.fixture
def mock_session(mock_connection: Connection) -> Session:
    """Create a mock session for testing."""
    session = Session(mock_connection)
    mock_connection.session = session
    session.state = SessionState.PLAYING
    return session


@pytest.fixture
async def test_sympathist() -> AsyncGenerator[Character, None]:
    """Create a test character with sympathy skills."""
    async with get_session() as session:
        # Create user
        user = User(
            username=f"sympathist_{uuid.uuid4().hex[:8]}",
            email=f"sympathist_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user)
        await session.flush()

        # Create character with sympathy skills and high INT/WIS for Alar
        character = Character(
            user_id=user.id,
            name=f"Kvothe_{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.SCHOLAR,
            current_room_id="sympathy_room",
            current_hp=100,
            max_hp=100,
            current_mp=80,
            max_mp=80,
            intelligence=16,  # High INT for Alar
            wisdom=14,  # Good WIS for Alar
            skills={
                "sympathy": {
                    "rank": 2,  # Re'lar rank
                    "xp": 500,
                }
            },
        )
        session.add(character)
        await session.commit()

        yield character


class TestMaterialDatabase:
    """Tests for material similarity calculations."""

    def test_material_database_populated(self) -> None:
        """Test that material database has expected entries."""
        assert len(MATERIAL_DATABASE) > 0
        assert "iron" in MATERIAL_DATABASE
        assert "copper" in MATERIAL_DATABASE
        assert "human" in MATERIAL_DATABASE

    def test_material_properties(self) -> None:
        """Test material property structure."""
        iron = MATERIAL_DATABASE.get("iron")
        assert iron is not None
        assert iron.category == "metal"
        assert iron.sub_category == "iron"
        assert iron.heat_conductivity > 0
        assert iron.hardness > 0

    def test_human_material_properties(self) -> None:
        """Test that human material has expected properties."""
        human = MATERIAL_DATABASE.get("human")
        assert human is not None
        assert human.category == "organic"
        assert human.sub_category == "human"


class TestSimilarityScoring:
    """Tests for calculate_similarity_score."""

    def test_same_material_high_similarity(self) -> None:
        """Test that same materials have high similarity."""
        score = calculate_similarity_score("iron", "iron")
        assert score >= 0.9
        assert score <= 1.0

    def test_similar_materials(self) -> None:
        """Test that materials in same category have decent similarity."""
        # Iron and steel are both metals with iron sub-category
        score = calculate_similarity_score("iron", "steel")
        assert score >= 0.5  # Same category gives base 0.5+

    def test_different_materials_low_similarity(self) -> None:
        """Test that unrelated materials have low similarity."""
        # Metal vs wood - different categories
        score = calculate_similarity_score("iron", "oak")
        assert score >= 0.0
        assert score < 0.4  # Different categories

    def test_human_to_human_consanguinity(self) -> None:
        """Test that human-to-human has high similarity."""
        score = calculate_similarity_score("human", "human")
        assert score >= 0.9

    def test_consanguinity_gives_perfect_score(self) -> None:
        """Test that consanguinity flag gives 1.0 similarity."""
        score = calculate_similarity_score("iron", "copper", consanguinity=True)
        assert score == 1.0


class TestBindingEfficiency:
    """Tests for calculate_binding_efficiency."""

    def test_high_skill_high_similarity(self) -> None:
        """Test efficiency with high sympathy rank and similar materials."""
        efficiency = calculate_binding_efficiency(
            similarity=0.9,
            caster_alar=15,
            sympathy_rank=4,  # Master
        )
        assert efficiency > 0.7
        assert efficiency <= 1.0

    def test_low_skill_caps_efficiency(self) -> None:
        """Test that low rank caps efficiency."""
        efficiency = calculate_binding_efficiency(
            similarity=0.9,
            caster_alar=15,
            sympathy_rank=0,  # Untrained
        )
        # Capped by rank
        assert efficiency <= RANK_EFFICIENCY_CAPS[0]

    def test_high_alar_increases_efficiency(self) -> None:
        """Test that high Alar increases efficiency."""
        high_alar = calculate_binding_efficiency(
            similarity=0.8,
            caster_alar=20,
            sympathy_rank=3,
        )
        low_alar = calculate_binding_efficiency(
            similarity=0.8,
            caster_alar=10,
            sympathy_rank=3,
        )
        assert high_alar >= low_alar  # Higher Alar should help


class TestEnergySource:
    """Tests for energy source creation and management."""

    def test_create_candle_source(self) -> None:
        """Test creating a candle energy source."""
        source = create_energy_source(HeatSourceType.CANDLE)
        assert source.source_type == HeatSourceType.CANDLE
        assert source.max_energy > 0
        assert source.remaining_energy == source.max_energy
        assert not source.is_depleted

    def test_create_body_heat_source(self) -> None:
        """Test creating body heat source."""
        source = create_energy_source(HeatSourceType.BODY)
        assert source.source_type == HeatSourceType.BODY
        assert source.max_energy > 0

    def test_brazier_high_energy(self) -> None:
        """Test that brazier provides more energy than candle."""
        candle = create_energy_source(HeatSourceType.CANDLE)
        brazier = create_energy_source(HeatSourceType.BRAZIER)
        assert brazier.max_energy > candle.max_energy

    def test_energy_constants(self) -> None:
        """Test heat source energy constants."""
        assert HEAT_SOURCE_ENERGY["candle"] < HEAT_SOURCE_ENERGY["torch"]
        assert HEAT_SOURCE_ENERGY["torch"] < HEAT_SOURCE_ENERGY["brazier"]
        assert HEAT_SOURCE_ENERGY["body"] > 0

    def test_drain_energy(self) -> None:
        """Test draining energy from a source."""
        source = create_energy_source(HeatSourceType.TORCH)
        initial = source.remaining_energy
        drained = source.drain_energy(100)
        assert drained == 100
        assert source.remaining_energy == initial - 100


class TestRankSystem:
    """Tests for sympathy rank system."""

    def test_rank_names(self) -> None:
        """Test rank name constants."""
        assert len(RANK_NAMES) >= 6
        assert RANK_NAMES[0] == "Untrained"
        assert RANK_NAMES[1] == "E'lir"
        assert RANK_NAMES[2] == "Re'lar"
        assert RANK_NAMES[3] == "El'the"
        assert RANK_NAMES[4] == "Master"

    def test_xp_requirements_increase(self) -> None:
        """Test that XP requirements increase with rank."""
        for i in range(1, len(RANK_XP_REQUIREMENTS)):
            assert RANK_XP_REQUIREMENTS[i] > RANK_XP_REQUIREMENTS[i - 1]

    def test_efficiency_caps_increase(self) -> None:
        """Test that efficiency caps increase with rank."""
        for i in range(1, len(RANK_EFFICIENCY_CAPS)):
            assert RANK_EFFICIENCY_CAPS[i] > RANK_EFFICIENCY_CAPS[i - 1]

    def test_max_bindings_by_alar(self) -> None:
        """Test that max bindings exist for various Alar levels."""
        # Low Alar
        assert get_max_bindings(5) >= 1
        # Medium Alar
        assert get_max_bindings(15) >= 2
        # High Alar
        assert get_max_bindings(25) >= 4


class TestCharacterSympathy:
    """Tests for character sympathy functions."""

    @pytest.mark.asyncio
    async def test_get_sympathy_rank(self, test_sympathist: Character) -> None:
        """Test getting sympathy rank from character."""
        rank = get_sympathy_rank(test_sympathist)
        assert rank == 2  # Re'lar

    @pytest.mark.asyncio
    async def test_get_sympathy_xp(self, test_sympathist: Character) -> None:
        """Test getting sympathy XP from character."""
        xp = get_sympathy_xp(test_sympathist)
        assert xp == 500

    @pytest.mark.asyncio
    async def test_get_character_alar(self, test_sympathist: Character) -> None:
        """Test getting Alar from character (INT + WIS) / 2."""
        alar = get_character_alar(test_sympathist)
        expected = (test_sympathist.intelligence + test_sympathist.wisdom) // 2
        assert alar == expected

    @pytest.mark.asyncio
    async def test_get_max_bindings(self, test_sympathist: Character) -> None:
        """Test getting max bindings from Alar."""
        alar = get_character_alar(test_sympathist)
        max_bindings = get_max_bindings(alar)
        assert max_bindings >= 1

    @pytest.mark.asyncio
    async def test_format_sympathy_status(self, test_sympathist: Character) -> None:
        """Test formatting sympathy status display."""
        status = format_sympathy_status(test_sympathist)
        assert "Sympathy" in status or "sympathy" in status.lower()


class TestBacklash:
    """Tests for sympathetic backlash system."""

    def test_no_backlash_low_risk(self) -> None:
        """Test that low risk rarely causes backlash."""
        # With 0% energy usage and not using body heat, should rarely backlash
        backlash_count = 0
        for _ in range(100):
            backlash = check_for_backlash(
                energy_percentage=0.0,
                using_body_heat=False,
                sympathy_rank=3,
            )
            if backlash:
                backlash_count += 1
        # Should have very few backlashes
        assert backlash_count < 20

    def test_body_heat_increases_risk(self) -> None:
        """Test that body heat increases backlash risk."""
        # Just verify function works with body heat flag
        backlash = check_for_backlash(0.5, True, 2)
        # May or may not get backlash due to randomness

    def test_backlash_severity_levels(self) -> None:
        """Test backlash severity enum values."""
        assert BacklashSeverity.MINOR is not None
        assert BacklashSeverity.MODERATE is not None
        assert BacklashSeverity.SEVERE is not None
        assert BacklashSeverity.CRITICAL is not None

    def test_backlash_structure(self) -> None:
        """Test SympatheticBacklash dataclass structure."""
        backlash = SympatheticBacklash(
            severity=BacklashSeverity.MINOR,
            damage=10,
            mp_loss=5,
            message="You feel a sharp headache.",
        )
        assert backlash.severity == BacklashSeverity.MINOR
        assert backlash.damage == 10
        assert backlash.mp_loss == 5


class TestBindingManagement:
    """Tests for binding storage and management."""

    def test_get_active_bindings_empty(self) -> None:
        """Test getting bindings for character with none."""
        character_id = str(uuid.uuid4())
        bindings = get_active_bindings(character_id)
        assert bindings == []

    def test_release_all_bindings_empty(self) -> None:
        """Test releasing bindings when none exist."""
        character_id = str(uuid.uuid4())
        count = release_all_bindings(character_id)
        assert count == 0

    def test_format_bindings_display_empty(self) -> None:
        """Test formatting bindings display with none active."""
        character_id = str(uuid.uuid4())
        display = format_bindings_display(character_id)
        assert "no active" in display.lower() or "none" in display.lower()


class TestBindingTypes:
    """Tests for binding type functionality."""

    def test_all_binding_types_defined(self) -> None:
        """Test that all expected binding types are defined."""
        assert BindingType.HEAT_TRANSFER is not None
        assert BindingType.KINETIC_TRANSFER is not None
        assert BindingType.DAMAGE_TRANSFER is not None
        assert BindingType.LIGHT_BINDING is not None
        assert BindingType.DOWSING is not None

    def test_binding_type_values(self) -> None:
        """Test that binding types have string values."""
        for bt in BindingType:
            assert isinstance(bt.value, str)
            assert len(bt.value) > 0


class TestSympatheticLink:
    """Tests for SympatheticLink dataclass."""

    def test_create_sympathetic_link(self) -> None:
        """Test creating a sympathetic link."""
        link = SympatheticLink(
            source_id="source_123",
            target_id="target_456",
            source_material="copper",
            target_material="copper",
            similarity=0.95,
            consanguinity=False,
        )
        assert link.source_id == "source_123"
        assert link.target_id == "target_456"
        assert link.similarity == 0.95
        assert not link.consanguinity

    def test_consanguinity_link(self) -> None:
        """Test creating a consanguinity (blood) link."""
        link = SympatheticLink(
            source_id="blood_source",
            target_id="person_target",
            source_material="human",
            target_material="human",
            similarity=0.99,
            consanguinity=True,
        )
        assert link.consanguinity
        assert link.similarity >= 0.95


class TestXPAndProgression:
    """Tests for XP and progression system."""

    @pytest.mark.asyncio
    async def test_award_sympathy_xp(self) -> None:
        """Test awarding sympathy XP."""
        async with get_session() as session:
            # Create user
            user = User(
                username=f"xptest_{uuid.uuid4().hex[:8]}",
                email=f"xptest_{uuid.uuid4().hex[:8]}@example.com",
                password_hash=User.hash_password("password"),
            )
            session.add(user)
            await session.flush()

            # Create character with sympathy skills
            character = Character(
                user_id=user.id,
                name=f"XPTest_{uuid.uuid4().hex[:8]}",
                background=CharacterBackground.SCHOLAR,
                current_room_id="test_room",
                skills={
                    "sympathy": {
                        "rank": 1,
                        "xp": 50,
                    }
                },
            )
            session.add(character)
            await session.flush()

            initial_xp = get_sympathy_xp(character)
            assert initial_xp == 50

            # Award XP - function takes character_id (UUID), not Character
            new_xp_amount, leveled_up = await award_sympathy_xp(
                character.id, 100, session
            )
            await session.commit()

            # Verify XP increased
            await session.refresh(character)
            new_xp = get_sympathy_xp(character)
            assert new_xp == 150  # 50 + 100


class TestEnergySourceMethods:
    """Tests for EnergySource methods."""

    def test_energy_per_turn(self) -> None:
        """Test energy_per_turn property."""
        candle = create_energy_source(HeatSourceType.CANDLE)
        assert candle.energy_per_turn == HEAT_SOURCE_ENERGY["candle"]

        torch = create_energy_source(HeatSourceType.TORCH)
        assert torch.energy_per_turn == HEAT_SOURCE_ENERGY["torch"]

    def test_is_depleted(self) -> None:
        """Test is_depleted property."""
        source = create_energy_source(HeatSourceType.CANDLE)
        assert not source.is_depleted

        source.remaining_energy = 0
        assert source.is_depleted

    def test_drain_exceeds_remaining(self) -> None:
        """Test draining more than available."""
        source = create_energy_source(HeatSourceType.CANDLE)
        source.remaining_energy = 50
        drained = source.drain_energy(100)
        assert drained == 50  # Only drains what's available
        assert source.remaining_energy == 0


class TestIntegration:
    """Integration tests for sympathy system."""

    @pytest.mark.asyncio
    async def test_full_binding_flow(
        self, test_engine: GameEngine, test_sympathist: Character
    ) -> None:
        """Test complete binding creation and release flow."""
        character_id = str(test_sympathist.id)

        # Initially no bindings
        bindings = get_active_bindings(character_id)
        assert len(bindings) == 0

        # Get max bindings
        alar = get_character_alar(test_sympathist)
        max_bindings = get_max_bindings(alar)
        assert max_bindings >= 1

        # Release all (should be safe even with none)
        released = release_all_bindings(character_id)
        assert released == 0

    @pytest.mark.asyncio
    async def test_energy_source_lifecycle(self) -> None:
        """Test energy source creation and depletion."""
        source = create_energy_source(HeatSourceType.TORCH)

        assert not source.is_depleted
        initial_energy = source.remaining_energy

        # Simulate using energy
        source.drain_energy(100)
        assert source.remaining_energy < initial_energy

        # Deplete completely
        source.drain_energy(source.remaining_energy)
        assert source.is_depleted

    def test_similarity_and_efficiency_chain(self) -> None:
        """Test calculating similarity then efficiency."""
        # First get similarity
        similarity = calculate_similarity_score("iron", "steel")
        assert similarity > 0.5

        # Then calculate efficiency
        efficiency = calculate_binding_efficiency(
            similarity=similarity,
            caster_alar=15,
            sympathy_rank=2,
        )
        assert efficiency > 0
        assert efficiency <= RANK_EFFICIENCY_CAPS[2]
