"""Sympathy magic system for Waystone MUD.

The art of creating sympathetic links between objects to transfer energy and force.
Based on the Kingkiller Chronicle's magic system by Patrick Rothfuss.

Key Concepts:
- Alar: Mental strength/willpower that maintains bindings
- Similarity: How alike two objects are (affects binding efficiency)
- Consanguinity: Having once been part of the same whole (maximum efficiency)
- Heat Sources: Provide energy for sympathetic transfers
- Backlash: Danger from failed or overpowered bindings
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from waystone.database.models import Character
from waystone.network import colorize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Sympathy rank efficiency caps (what percentage of energy transfer is possible)
RANK_EFFICIENCY_CAPS = {
    0: 0.30,  # Untrained: 30%
    1: 0.50,  # E'lir: 50%
    2: 0.65,  # Re'lar: 65%
    3: 0.80,  # El'the: 80%
    4: 0.90,  # Master: 90%
    5: 0.95,  # Legendary: 95%
}

# Sympathy rank names
RANK_NAMES = {
    0: "Untrained",
    1: "E'lir",
    2: "Re'lar",
    3: "El'the",
    4: "Master",
    5: "Arcane Master",
}

# XP required for each rank
RANK_XP_REQUIREMENTS = {
    0: 0,
    1: 100,
    2: 300,
    3: 700,
    4: 1500,
    5: 3000,
}

# Maximum number of simultaneous bindings by Alar strength
MAX_BINDINGS_BY_ALAR = {
    range(0, 10): 1,
    range(10, 14): 2,
    range(14, 18): 3,
    range(18, 22): 4,
    range(22, 100): 5,
}

# Backlash risk thresholds
BACKLASH_RISK_THRESHOLD = 0.7  # Above 70% energy draw = backlash risk
BODY_HEAT_BACKLASH_MULTIPLIER = 2.5  # Body heat is much more dangerous

# Energy per turn for different heat sources
HEAT_SOURCE_ENERGY = {
    "candle": 50,
    "torch": 150,
    "brazier": 500,
    "bonfire": 1500,
    "body": 100,  # Body heat - dangerous!
    "sun": 2000,  # If outdoors during day
}


# ============================================================================
# Enums
# ============================================================================


class BindingType(Enum):
    """Types of sympathetic bindings."""

    HEAT_TRANSFER = "heat_transfer"  # Move heat between objects
    KINETIC_TRANSFER = "kinetic_transfer"  # Move force/motion
    DAMAGE_TRANSFER = "damage_transfer"  # Combat use - transfer damage
    LIGHT_BINDING = "light_binding"  # Create/move light
    DOWSING = "dowsing"  # Locate similar objects


class HeatSourceType(Enum):
    """Types of heat sources for sympathy."""

    CANDLE = "candle"
    TORCH = "torch"
    BRAZIER = "brazier"
    BONFIRE = "bonfire"
    BODY = "body"  # Using your own body heat - dangerous!
    SUN = "sun"  # Ambient solar energy


class BacklashSeverity(Enum):
    """Severity levels of sympathetic backlash."""

    MINOR = "minor"  # Headache, slight energy loss
    MODERATE = "moderate"  # Unconsciousness, Alar reduction
    SEVERE = "severe"  # Temporary stat loss, injury
    CRITICAL = "critical"  # Potential death


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class EnergySource:
    """Represents a heat/energy source for sympathetic bindings."""

    source_type: HeatSourceType
    remaining_energy: int
    max_energy: int
    item_id: str | None = None  # UUID of the item if applicable

    @property
    def energy_per_turn(self) -> int:
        """Get energy output per turn."""
        return HEAT_SOURCE_ENERGY.get(self.source_type.value, 0)

    @property
    def is_depleted(self) -> bool:
        """Check if source is depleted."""
        return self.remaining_energy <= 0

    def drain_energy(self, amount: int) -> int:
        """
        Drain energy from the source.

        Args:
            amount: Amount of energy to drain

        Returns:
            Actual amount drained (may be less if source runs low)
        """
        actual_drain = min(amount, self.remaining_energy)
        self.remaining_energy -= actual_drain
        return actual_drain


@dataclass
class MaterialProperties:
    """Properties of a material for similarity calculations."""

    category: str  # metal, wood, stone, organic, etc.
    sub_category: str  # iron, oak, granite, human, etc.
    heat_conductivity: float  # 0.0 - 1.0
    hardness: float  # 0.0 - 1.0


@dataclass
class SympatheticLink:
    """Represents a sympathetic link between two objects."""

    source_id: str  # Item or character ID
    target_id: str  # Item or character ID
    source_material: str
    target_material: str
    similarity: float  # 0.0 - 1.0
    consanguinity: bool  # Were they once the same object?


@dataclass
class Binding:
    """An active sympathetic binding."""

    binding_id: str
    caster_id: str
    binding_type: BindingType
    link: SympatheticLink
    energy_source: EnergySource
    efficiency: float  # Final efficiency after all modifiers
    strength: int  # Current strength of binding
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True


@dataclass
class SympatheticBacklash:
    """Result of a backlash event."""

    severity: BacklashSeverity
    damage: int  # HP damage
    mp_loss: int  # Alar points lost
    stat_penalty: dict[str, int] | None = None  # Temporary stat reductions
    duration_seconds: int = 0  # How long penalties last
    message: str = ""


# ============================================================================
# Material Database for Similarity Calculations
# ============================================================================

MATERIAL_DATABASE: dict[str, MaterialProperties] = {
    # Metals
    "iron": MaterialProperties("metal", "iron", 0.8, 0.7),
    "steel": MaterialProperties("metal", "iron", 0.75, 0.85),
    "copper": MaterialProperties("metal", "copper", 0.95, 0.4),
    "bronze": MaterialProperties("metal", "copper", 0.85, 0.5),
    "silver": MaterialProperties("metal", "silver", 0.98, 0.3),
    "gold": MaterialProperties("metal", "gold", 0.9, 0.2),
    # Woods
    "oak": MaterialProperties("wood", "oak", 0.2, 0.6),
    "pine": MaterialProperties("wood", "pine", 0.15, 0.4),
    "ash": MaterialProperties("wood", "ash", 0.18, 0.55),
    "rowan": MaterialProperties("wood", "rowan", 0.2, 0.5),
    # Stone
    "granite": MaterialProperties("stone", "granite", 0.5, 0.9),
    "marble": MaterialProperties("stone", "marble", 0.55, 0.7),
    "limestone": MaterialProperties("stone", "calcium", 0.4, 0.5),
    # Organic
    "leather": MaterialProperties("organic", "animal", 0.3, 0.3),
    "cloth": MaterialProperties("organic", "plant", 0.1, 0.1),
    "bone": MaterialProperties("organic", "bone", 0.4, 0.6),
    "human": MaterialProperties("organic", "human", 0.35, 0.4),
    # Special
    "glass": MaterialProperties("mineral", "silica", 0.6, 0.5),
    "wax": MaterialProperties("organic", "wax", 0.05, 0.05),
}


# ============================================================================
# Active Bindings Tracking (per session)
# ============================================================================

# Global tracking of active bindings: character_id -> list of Bindings
_active_bindings: dict[str, list[Binding]] = {}


# ============================================================================
# Core Functions
# ============================================================================


def calculate_similarity_score(
    source_material: str,
    target_material: str,
    consanguinity: bool = False,
) -> float:
    """
    Calculate similarity between two materials for binding efficiency.

    Args:
        source_material: Material type of the source object
        target_material: Material type of the target object
        consanguinity: Whether objects were once part of the same whole

    Returns:
        Similarity score from 0.0 to 1.0
    """
    # Consanguinity (once the same object) gives perfect similarity
    if consanguinity:
        return 1.0

    # Identical materials are highly similar
    if source_material == target_material:
        return 0.95

    # Look up materials in database
    source_props = MATERIAL_DATABASE.get(source_material.lower())
    target_props = MATERIAL_DATABASE.get(target_material.lower())

    if not source_props or not target_props:
        # Unknown materials - poor similarity
        return 0.1

    # Same category gives base similarity
    if source_props.category == target_props.category:
        base_similarity = 0.5
        # Same sub-category gives better similarity
        if source_props.sub_category == target_props.sub_category:
            base_similarity = 0.8
    else:
        base_similarity = 0.1

    # Adjust for conductivity similarity (for heat transfer)
    conductivity_diff = abs(source_props.heat_conductivity - target_props.heat_conductivity)
    conductivity_bonus = (1.0 - conductivity_diff) * 0.2

    final_similarity = min(0.95, base_similarity + conductivity_bonus)

    logger.debug(
        "similarity_calculated",
        source=source_material,
        target=target_material,
        base=base_similarity,
        final=final_similarity,
    )

    return final_similarity


def calculate_binding_efficiency(
    similarity: float,
    caster_alar: int,
    sympathy_rank: int,
    distance_modifier: float = 1.0,
) -> float:
    """
    Calculate the overall efficiency of a sympathetic binding.

    Args:
        similarity: Material similarity (0.0-1.0)
        caster_alar: Caster's Alar attribute (INT + WIS) / 2
        sympathy_rank: Character's sympathy skill rank
        distance_modifier: Modifier for distance (1.0 = close, decreases with distance)

    Returns:
        Efficiency from 0.0 to 1.0
    """
    # Get rank cap
    rank_cap = RANK_EFFICIENCY_CAPS.get(sympathy_rank, 0.3)

    # Base efficiency from similarity
    base_efficiency = similarity

    # Alar modifier: +2% per point above 10
    alar_modifier = 1.0 + max(0, (caster_alar - 10) * 0.02)

    # Calculate raw efficiency
    raw_efficiency = base_efficiency * alar_modifier * distance_modifier

    # Apply rank cap
    final_efficiency = min(raw_efficiency, rank_cap)

    logger.debug(
        "efficiency_calculated",
        similarity=similarity,
        alar=caster_alar,
        rank=sympathy_rank,
        distance_mod=distance_modifier,
        raw=raw_efficiency,
        capped=final_efficiency,
    )

    return final_efficiency


def get_max_bindings(alar: int) -> int:
    """
    Get maximum number of simultaneous bindings based on Alar.

    Args:
        alar: Character's Alar attribute

    Returns:
        Maximum number of bindings
    """
    for alar_range, max_bindings in MAX_BINDINGS_BY_ALAR.items():
        if alar in alar_range:
            return max_bindings
    return 1


def get_character_alar(character: Character) -> int:
    """
    Calculate a character's Alar from INT and WIS.

    Args:
        character: The character

    Returns:
        Alar value
    """
    return (character.intelligence + character.wisdom) // 2


def get_sympathy_rank(character: Character) -> int:
    """
    Get a character's sympathy skill rank.

    Args:
        character: The character

    Returns:
        Sympathy rank (0-5)
    """
    skills = character.skills or {}
    sympathy_data = skills.get("sympathy", {})
    rank = sympathy_data.get("rank", 0) if isinstance(sympathy_data, dict) else 0
    return int(rank) if rank else 0


def get_sympathy_xp(character: Character) -> int:
    """
    Get a character's sympathy XP.

    Args:
        character: The character

    Returns:
        Sympathy XP
    """
    skills = character.skills or {}
    sympathy_data = skills.get("sympathy", {})
    xp = sympathy_data.get("xp", 0) if isinstance(sympathy_data, dict) else 0
    return int(xp) if xp else 0


async def award_sympathy_xp(
    character_id: UUID,
    amount: int,
    session: "AsyncSession",
) -> tuple[int, bool]:
    """
    Award sympathy XP to a character and check for rank-up.

    Args:
        character_id: Character UUID
        amount: XP amount to award
        session: Database session

    Returns:
        Tuple of (new_xp, ranked_up)
    """
    from sqlalchemy import select

    result = await session.execute(select(Character).where(Character.id == character_id))
    character = result.scalar_one_or_none()

    if not character:
        raise ValueError(f"Character {character_id} not found")

    # Get current sympathy data
    skills = dict(character.skills or {})
    sympathy_data = dict(skills.get("sympathy", {"rank": 0, "xp": 0}))

    old_rank = sympathy_data.get("rank", 0)
    old_xp = sympathy_data.get("xp", 0)
    new_xp = old_xp + amount

    # Check for rank up
    ranked_up = False
    new_rank = old_rank
    for rank, required_xp in sorted(RANK_XP_REQUIREMENTS.items()):
        if new_xp >= required_xp and rank > new_rank:
            new_rank = rank
            ranked_up = True

    # Update skill data
    sympathy_data["xp"] = new_xp
    sympathy_data["rank"] = new_rank
    skills["sympathy"] = sympathy_data
    character.skills = skills

    logger.info(
        "sympathy_xp_awarded",
        character_id=str(character_id),
        amount=amount,
        new_xp=new_xp,
        old_rank=old_rank,
        new_rank=new_rank,
    )

    return new_xp, ranked_up


# ============================================================================
# Binding Management
# ============================================================================


def get_active_bindings(character_id: str) -> list[Binding]:
    """Get all active bindings for a character."""
    return _active_bindings.get(character_id, [])


async def create_binding(
    caster: Character,
    binding_type: BindingType,
    source_id: str,
    target_id: str,
    source_material: str,
    target_material: str,
    energy_source: EnergySource,
    consanguinity: bool = False,
    engine: "GameEngine | None" = None,
) -> tuple[Binding | None, str]:
    """
    Create a new sympathetic binding.

    Args:
        caster: Character creating the binding
        binding_type: Type of binding to create
        source_id: ID of source object
        target_id: ID of target object
        source_material: Material of source
        target_material: Material of target
        energy_source: Energy source for the binding
        consanguinity: Whether objects share origin
        engine: Game engine for notifications

    Returns:
        Tuple of (Binding if successful, message)
    """
    character_id = str(caster.id)

    # Check if character has capacity for another binding
    alar = get_character_alar(caster)
    max_bindings = get_max_bindings(alar)
    current_bindings = get_active_bindings(character_id)

    if len(current_bindings) >= max_bindings:
        return None, f"Your Alar can only maintain {max_bindings} binding(s) at once."

    # Check if character has enough MP
    binding_mp_cost = 5  # Base MP cost to create binding
    if caster.current_mp < binding_mp_cost:
        return None, "You don't have enough mental energy to create a binding."

    # Calculate similarity and efficiency
    similarity = calculate_similarity_score(source_material, target_material, consanguinity)
    sympathy_rank = get_sympathy_rank(caster)
    efficiency = calculate_binding_efficiency(similarity, alar, sympathy_rank)

    if efficiency < 0.1:
        return None, "The materials are too dissimilar for an effective binding."

    # Create the link
    link = SympatheticLink(
        source_id=source_id,
        target_id=target_id,
        source_material=source_material,
        target_material=target_material,
        similarity=similarity,
        consanguinity=consanguinity,
    )

    # Create the binding
    import uuid

    binding = Binding(
        binding_id=str(uuid.uuid4()),
        caster_id=character_id,
        binding_type=binding_type,
        link=link,
        energy_source=energy_source,
        efficiency=efficiency,
        strength=int(efficiency * 100),
    )

    # Add to active bindings
    if character_id not in _active_bindings:
        _active_bindings[character_id] = []
    _active_bindings[character_id].append(binding)

    # Consume MP
    caster.current_mp -= binding_mp_cost

    logger.info(
        "binding_created",
        caster_id=character_id,
        caster_name=caster.name,
        binding_type=binding_type.value,
        efficiency=efficiency,
        similarity=similarity,
    )

    efficiency_pct = int(efficiency * 100)
    return binding, f"You create a {binding_type.value} binding at {efficiency_pct}% efficiency."


def release_binding(character_id: str, binding_id: str) -> tuple[bool, str]:
    """
    Release an active binding.

    Args:
        character_id: Character releasing the binding
        binding_id: ID of binding to release

    Returns:
        Tuple of (success, message)
    """
    bindings = get_active_bindings(character_id)

    for i, binding in enumerate(bindings):
        if binding.binding_id == binding_id:
            binding.is_active = False
            _active_bindings[character_id].pop(i)

            logger.info(
                "binding_released",
                character_id=character_id,
                binding_id=binding_id,
            )

            return True, "You release the binding."

    return False, "Binding not found."


def release_all_bindings(character_id: str) -> int:
    """
    Release all bindings for a character.

    Args:
        character_id: Character ID

    Returns:
        Number of bindings released
    """
    if character_id not in _active_bindings:
        return 0

    count = len(_active_bindings[character_id])
    _active_bindings[character_id] = []

    logger.info(
        "all_bindings_released",
        character_id=character_id,
        count=count,
    )

    return count


# ============================================================================
# Binding Actions
# ============================================================================


async def execute_heat_transfer(
    binding: Binding,
    energy_amount: int,
    caster: Character,
    session: "AsyncSession",
) -> tuple[bool, int, str]:
    """
    Execute a heat transfer through a binding.

    Args:
        binding: The active binding
        energy_amount: Amount of energy to transfer
        caster: The character performing the transfer
        session: Database session

    Returns:
        Tuple of (success, actual_transfer, message)
    """
    # Drain energy from source
    actual_drain = binding.energy_source.drain_energy(energy_amount)

    if actual_drain == 0:
        return False, 0, "Your heat source is depleted!"

    # Apply efficiency
    actual_transfer = int(actual_drain * binding.efficiency)

    # Award sympathy XP (1 XP per 10 energy transferred)
    xp_gain = max(1, actual_transfer // 10)
    await award_sympathy_xp(caster.id, xp_gain, session)

    logger.info(
        "heat_transfer_executed",
        binding_id=binding.binding_id,
        energy_requested=energy_amount,
        energy_drained=actual_drain,
        energy_transferred=actual_transfer,
    )

    return True, actual_transfer, f"You transfer {actual_transfer} units of heat energy."


async def execute_kinetic_transfer(
    binding: Binding,
    force_amount: int,
    caster: Character,
    session: "AsyncSession",
) -> tuple[bool, int, str]:
    """
    Execute a kinetic (force/motion) transfer through a binding.

    Args:
        binding: The active binding
        force_amount: Amount of force to transfer
        caster: The character performing the transfer
        session: Database session

    Returns:
        Tuple of (success, actual_force, message)
    """
    # Calculate energy cost (kinetic transfers cost more)
    energy_cost = force_amount * 2
    actual_drain = binding.energy_source.drain_energy(energy_cost)

    if actual_drain == 0:
        return False, 0, "Your heat source is depleted!"

    # Apply efficiency
    actual_force = int((actual_drain / 2) * binding.efficiency)

    # Cost MP for kinetic transfers
    mp_cost = max(1, force_amount // 10)
    caster.current_mp = max(0, caster.current_mp - mp_cost)

    # Award sympathy XP
    xp_gain = max(1, actual_force // 5)
    await award_sympathy_xp(caster.id, xp_gain, session)

    logger.info(
        "kinetic_transfer_executed",
        binding_id=binding.binding_id,
        force_requested=force_amount,
        force_applied=actual_force,
    )

    return True, actual_force, f"You apply {actual_force} units of force through the link."


async def execute_damage_transfer(
    binding: Binding,
    damage_amount: int,
    caster: Character,
    target: Character,
    session: "AsyncSession",
) -> tuple[bool, int, str]:
    """
    Execute a damage transfer through a binding (combat use).

    Args:
        binding: The active binding
        damage_amount: Base damage to attempt
        caster: The character performing the transfer
        target: The target character
        session: Database session

    Returns:
        Tuple of (success, actual_damage, message)
    """
    # Calculate energy cost
    energy_cost = damage_amount * 3
    actual_drain = binding.energy_source.drain_energy(energy_cost)

    if actual_drain == 0:
        return False, 0, "Your heat source is depleted!"

    # Apply efficiency to damage
    actual_damage = int((actual_drain / 3) * binding.efficiency)

    # MP cost for combat sympathy
    mp_cost = max(2, damage_amount // 5)
    if caster.current_mp < mp_cost:
        return False, 0, "You don't have enough mental energy to maintain the attack."

    caster.current_mp -= mp_cost

    # Apply damage to target (bypasses armor!)
    target.current_hp = max(0, target.current_hp - actual_damage)

    # Award combat sympathy XP
    xp_gain = max(2, actual_damage // 2)
    await award_sympathy_xp(caster.id, xp_gain, session)

    logger.info(
        "damage_transfer_executed",
        binding_id=binding.binding_id,
        caster_id=str(caster.id),
        target_id=str(target.id),
        damage=actual_damage,
    )

    return True, actual_damage, f"Your sympathetic attack deals {actual_damage} damage!"


# ============================================================================
# Backlash System
# ============================================================================


def calculate_backlash_risk(
    energy_percentage: float,
    using_body_heat: bool,
    sympathy_rank: int,
) -> float:
    """
    Calculate risk of sympathetic backlash.

    Args:
        energy_percentage: Percentage of max energy being used (0.0-1.0)
        using_body_heat: Whether body heat is the energy source
        sympathy_rank: Character's sympathy rank

    Returns:
        Backlash risk (0.0-1.0)
    """
    # Base risk from energy usage
    if energy_percentage < BACKLASH_RISK_THRESHOLD:
        base_risk = 0.0
    else:
        # Risk increases sharply above threshold
        excess = energy_percentage - BACKLASH_RISK_THRESHOLD
        base_risk = min(0.9, excess * 3)  # Cap at 90% risk

    # Body heat is much more dangerous
    if using_body_heat:
        base_risk *= BODY_HEAT_BACKLASH_MULTIPLIER
        base_risk = min(0.95, base_risk)  # Cap at 95%

    # Higher ranks reduce risk
    rank_reduction = sympathy_rank * 0.05  # 5% reduction per rank
    final_risk = max(0.0, base_risk - rank_reduction)

    return final_risk


def check_for_backlash(
    energy_percentage: float,
    using_body_heat: bool,
    sympathy_rank: int,
) -> SympatheticBacklash | None:
    """
    Check if backlash occurs and calculate effects.

    Args:
        energy_percentage: Percentage of max energy being used
        using_body_heat: Whether body heat is the energy source
        sympathy_rank: Character's sympathy rank

    Returns:
        SympatheticBacklash if backlash occurs, None otherwise
    """
    risk = calculate_backlash_risk(energy_percentage, using_body_heat, sympathy_rank)

    # Roll for backlash
    roll = random.random()
    if roll > risk:
        return None

    # Backlash occurs - determine severity
    severity_roll = random.random()

    if severity_roll < 0.5:
        severity = BacklashSeverity.MINOR
        damage = random.randint(1, 5)
        mp_loss = random.randint(5, 10)
        duration = 300  # 5 minutes
        message = "A sharp pain lances through your head as the binding snaps back!"
    elif severity_roll < 0.8:
        severity = BacklashSeverity.MODERATE
        damage = random.randint(5, 15)
        mp_loss = random.randint(10, 20)
        duration = 600  # 10 minutes
        message = "The binding shatters! Your mind reels from the backlash!"
    elif severity_roll < 0.95:
        severity = BacklashSeverity.SEVERE
        damage = random.randint(15, 30)
        mp_loss = random.randint(20, 40)
        duration = 1800  # 30 minutes
        stat_penalty = {"intelligence": -2, "wisdom": -2}
        message = "CRITICAL BACKLASH! The sympathetic link tears through your mind!"
        return SympatheticBacklash(
            severity=severity,
            damage=damage,
            mp_loss=mp_loss,
            stat_penalty=stat_penalty,
            duration_seconds=duration,
            message=message,
        )
    else:
        severity = BacklashSeverity.CRITICAL
        damage = random.randint(30, 60)
        mp_loss = 9999  # All MP
        duration = 3600  # 1 hour
        stat_penalty = {"intelligence": -4, "wisdom": -4, "constitution": -2}
        message = "CATASTROPHIC BACKLASH! Your Alar shatters under the strain!"
        return SympatheticBacklash(
            severity=severity,
            damage=damage,
            mp_loss=mp_loss,
            stat_penalty=stat_penalty,
            duration_seconds=duration,
            message=message,
        )

    return SympatheticBacklash(
        severity=severity,
        damage=damage,
        mp_loss=mp_loss,
        duration_seconds=duration,
        message=message,
    )


async def apply_backlash(
    backlash: SympatheticBacklash,
    character: Character,
    session: "AsyncSession",
    engine: "GameEngine | None" = None,
) -> None:
    """
    Apply backlash effects to a character.

    Args:
        backlash: The backlash event
        character: The affected character
        session: Database session
        engine: Game engine for notifications
    """
    # Apply damage
    character.current_hp = max(0, character.current_hp - backlash.damage)

    # Apply MP loss
    character.current_mp = max(0, character.current_mp - backlash.mp_loss)

    # Release all bindings
    release_all_bindings(str(character.id))

    logger.warning(
        "backlash_applied",
        character_id=str(character.id),
        character_name=character.name,
        severity=backlash.severity.value,
        damage=backlash.damage,
        mp_loss=backlash.mp_loss,
    )

    # Notify player if engine available
    if engine:
        char_session = engine.character_to_session.get(str(character.id))
        if char_session:
            await char_session.connection.send_line(colorize(f"\n{backlash.message}", "RED"))
            await char_session.connection.send_line(
                colorize(
                    f"You take {backlash.damage} damage and lose {backlash.mp_loss} mental energy!",
                    "RED",
                )
            )


# ============================================================================
# Energy Source Creation
# ============================================================================


def create_energy_source(
    source_type: HeatSourceType,
    item_id: str | None = None,
) -> EnergySource:
    """
    Create a new energy source.

    Args:
        source_type: Type of heat source
        item_id: Optional item UUID

    Returns:
        New EnergySource instance
    """
    # Calculate max energy based on type
    energy_per_turn = HEAT_SOURCE_ENERGY.get(source_type.value, 50)

    # Different sources have different durations
    duration_multipliers = {
        HeatSourceType.CANDLE: 20,  # Burns out relatively quickly
        HeatSourceType.TORCH: 30,
        HeatSourceType.BRAZIER: 50,
        HeatSourceType.BONFIRE: 100,
        HeatSourceType.BODY: 10,  # Can only safely draw so much
        HeatSourceType.SUN: 1000,  # Effectively unlimited during day
    }

    multiplier = duration_multipliers.get(source_type, 20)
    max_energy = energy_per_turn * multiplier

    return EnergySource(
        source_type=source_type,
        remaining_energy=max_energy,
        max_energy=max_energy,
        item_id=item_id,
    )


# ============================================================================
# Utility Functions
# ============================================================================


def format_bindings_display(character_id: str) -> str:
    """
    Format active bindings for display.

    Args:
        character_id: Character to show bindings for

    Returns:
        Formatted string of bindings
    """
    bindings = get_active_bindings(character_id)

    if not bindings:
        return colorize("You have no active bindings.", "DIM")

    lines = [colorize("=== Active Bindings ===", "CYAN")]

    for i, binding in enumerate(bindings, 1):
        efficiency_pct = int(binding.efficiency * 100)
        energy_remaining = binding.energy_source.remaining_energy
        energy_max = binding.energy_source.max_energy
        energy_pct = int((energy_remaining / max(1, energy_max)) * 100)

        lines.append(
            f"  {i}. {colorize(binding.binding_type.value.title(), 'YELLOW')} "
            f"({efficiency_pct}% efficiency)"
        )
        lines.append(
            f"     Energy: {colorize(f'{energy_remaining}/{energy_max}', 'GREEN')} ({energy_pct}%)"
        )
        lines.append(f"     Source: {binding.energy_source.source_type.value}")

    return "\n".join(lines)


def format_sympathy_status(character: Character) -> str:
    """
    Format sympathy skill status for display.

    Args:
        character: Character to show status for

    Returns:
        Formatted status string
    """
    rank = get_sympathy_rank(character)
    xp = get_sympathy_xp(character)
    alar = get_character_alar(character)
    max_bindings = get_max_bindings(alar)

    rank_name = RANK_NAMES.get(rank, "Unknown")
    efficiency_cap = int(RANK_EFFICIENCY_CAPS.get(rank, 0.3) * 100)

    # XP to next rank
    next_rank = rank + 1
    next_rank_xp = RANK_XP_REQUIREMENTS.get(next_rank, float("inf"))
    xp_to_next = max(0, next_rank_xp - xp) if next_rank <= 5 else "MAX"

    lines = [
        colorize("=== Sympathy ===", "CYAN"),
        f"  Rank: {colorize(rank_name, 'YELLOW')} ({rank})",
        f"  XP: {xp} (Next: {xp_to_next})",
        f"  Alar: {alar} (Max bindings: {max_bindings})",
        f"  Efficiency Cap: {efficiency_cap}%",
        f"  Mental Energy: {character.current_mp}/{character.max_mp}",
    ]

    return "\n".join(lines)
