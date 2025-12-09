"""Tests for the game state parser."""

import pytest

from waystone.agent.parser import (
    Direction,
    GameStateParser,
    RoomInfo,
)


class TestDirection:
    """Test direction parsing."""

    def test_parse_full_name(self):
        """Test parsing full direction names."""
        assert Direction.from_string("north") == Direction.NORTH
        assert Direction.from_string("south") == Direction.SOUTH
        assert Direction.from_string("northeast") == Direction.NORTHEAST

    def test_parse_alias(self):
        """Test parsing direction aliases."""
        assert Direction.from_string("n") == Direction.NORTH
        assert Direction.from_string("s") == Direction.SOUTH
        assert Direction.from_string("ne") == Direction.NORTHEAST
        assert Direction.from_string("sw") == Direction.SOUTHWEST

    def test_parse_case_insensitive(self):
        """Test case insensitive parsing."""
        assert Direction.from_string("NORTH") == Direction.NORTH
        assert Direction.from_string("North") == Direction.NORTH
        assert Direction.from_string("N") == Direction.NORTH

    def test_parse_invalid(self):
        """Test invalid direction returns None."""
        assert Direction.from_string("invalid") is None
        assert Direction.from_string("") is None
        assert Direction.from_string("diagonal") is None


class TestGameStateParser:
    """Test game state parser."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return GameStateParser()

    def test_strip_ansi(self, parser):
        """Test ANSI code stripping."""
        text = "\x1b[31mRed text\x1b[0m"
        assert parser.strip_ansi(text) == "Red text"

        text2 = "\x1b[1;32mBright green\x1b[0m normal"
        assert parser.strip_ansi(text2) == "Bright green normal"

    def test_parse_room_name(self, parser):
        """Test parsing room name from output."""
        output = """University Main Gates
A grand archway marks the entrance to the renowned University.
[Exits: north, east, west]"""

        state = parser.parse(output)
        assert state.room.name == "University Main Gates"

    def test_parse_exits_bracket_format(self, parser):
        """Test parsing exits in bracket format."""
        output = """Market Square
A bustling marketplace full of merchants.
[Exits: north, south, east]"""

        state = parser.parse(output)
        assert Direction.NORTH in state.room.exits
        assert Direction.SOUTH in state.room.exits
        assert Direction.EAST in state.room.exits
        assert len(state.room.exits) == 3

    def test_parse_exits_obvious_format(self, parser):
        """Test parsing exits in 'Obvious exits' format."""
        output = """Dark Alley
A narrow passage between buildings.
Obvious exits: north, west"""

        state = parser.parse(output)
        assert Direction.NORTH in state.room.exits
        assert Direction.WEST in state.room.exits

    def test_parse_hp(self, parser):
        """Test parsing HP values."""
        output = """HP: 45/100 | MP: 30/50"""

        state = parser.parse(output)
        assert state.character.health == 45
        assert state.character.max_health == 100

    def test_parse_mana(self, parser):
        """Test parsing mana values."""
        output = """HP: 100/100 | Mana: 75/100"""

        state = parser.parse(output)
        assert state.character.mana == 75
        assert state.character.max_mana == 100

    def test_detect_combat(self, parser):
        """Test combat detection."""
        output = """The goblin attacks you with its club!
You take 5 damage."""

        state = parser.parse(output)
        assert state.in_combat is True

    def test_no_combat(self, parser):
        """Test non-combat state."""
        output = """Town Square
A peaceful plaza with a fountain.
[Exits: north, south]"""

        state = parser.parse(output)
        assert state.in_combat is False

    def test_parse_action_success(self, parser):
        """Test parsing successful actions."""
        output = "You get a rusty sword from the ground."
        state = parser.parse(output)
        assert state.last_action_result == "success"

        output2 = "You go north."
        state2 = parser.parse(output2)
        assert state2.last_action_result == "success"

    def test_parse_action_failure(self, parser):
        """Test parsing failed actions."""
        output = "You can't go that way."
        state = parser.parse(output)
        assert state.last_action_result == "failure"

        output2 = "Item not found."
        state2 = parser.parse(output2)
        assert state2.last_action_result == "failure"

    def test_to_context_string(self, parser):
        """Test context string generation."""
        output = """University Main Gates
A grand archway marks the entrance.
[Exits: north, east]"""

        parser.parse(output)
        context = parser.to_context_string()

        assert "Location: University Main Gates" in context
        assert "Exits:" in context
        assert "north" in context
        assert "east" in context

    def test_get_available_actions(self, parser):
        """Test available actions extraction."""
        output = """Marketplace
Busy market with vendors.
[Exits: north, south]"""

        parser.parse(output)
        actions = parser.get_available_actions()

        assert "north" in actions
        assert "south" in actions
        assert "look" in actions
        assert "inventory" in actions


class TestRoomInfo:
    """Test RoomInfo dataclass."""

    def test_default_values(self):
        """Test default RoomInfo values."""
        room = RoomInfo()
        assert room.name == ""
        assert room.description == ""
        assert room.exits == []
        assert room.items == []
        assert room.npcs == []
        assert room.players == []

    def test_with_data(self):
        """Test RoomInfo with data."""
        room = RoomInfo(
            name="Test Room",
            exits=[Direction.NORTH, Direction.SOUTH],
            npcs=["Guard Captain"],
        )
        assert room.name == "Test Room"
        assert len(room.exits) == 2
        assert "Guard Captain" in room.npcs
