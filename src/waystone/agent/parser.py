"""Game state parser for extracting structured data from MUD output."""

import re
from dataclasses import dataclass, field
from enum import Enum


class Direction(Enum):
    """Movement directions."""

    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"
    UP = "up"
    DOWN = "down"
    NORTHEAST = "northeast"
    NORTHWEST = "northwest"
    SOUTHEAST = "southeast"
    SOUTHWEST = "southwest"

    @classmethod
    def from_string(cls, s: str) -> "Direction | None":
        """Parse direction from string (handles aliases)."""
        aliases = {
            "n": "north",
            "s": "south",
            "e": "east",
            "w": "west",
            "u": "up",
            "d": "down",
            "ne": "northeast",
            "nw": "northwest",
            "se": "southeast",
            "sw": "southwest",
        }
        s = s.lower().strip()
        s = aliases.get(s, s)
        try:
            return cls(s)
        except ValueError:
            return None


@dataclass
class RoomInfo:
    """Parsed room information."""

    name: str = ""
    description: str = ""
    exits: list[Direction] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    npcs: list[str] = field(default_factory=list)
    players: list[str] = field(default_factory=list)


@dataclass
class CharacterStatus:
    """Parsed character status information."""

    name: str = ""
    health: int = 100
    max_health: int = 100
    mana: int = 100
    max_mana: int = 100
    level: int = 1
    experience: int = 0
    gold: int = 0
    inventory: list[str] = field(default_factory=list)


@dataclass
class GameState:
    """Current parsed game state."""

    room: RoomInfo = field(default_factory=RoomInfo)
    character: CharacterStatus = field(default_factory=CharacterStatus)
    last_action_result: str = ""
    in_combat: bool = False
    raw_output: str = ""


class GameStateParser:
    """
    Parser for extracting structured game state from MUD output.

    Uses regex patterns to identify room descriptions, exits, NPCs,
    items, and other game elements from the text output.
    """

    # ANSI escape code pattern
    ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

    # Room patterns
    ROOM_NAME_PATTERN = re.compile(r"^([A-Z][^\n]+)$", re.MULTILINE)
    EXITS_PATTERN = re.compile(r"\[Exits?:\s*([^\]]+)\]", re.IGNORECASE)
    EXITS_LIST_PATTERN = re.compile(r"Obvious exits?:\s*(.+?)(?:\n|$)", re.IGNORECASE)

    # Direction patterns for exit parsing
    DIRECTION_WORDS = [
        "north",
        "south",
        "east",
        "west",
        "up",
        "down",
        "northeast",
        "northwest",
        "southeast",
        "southwest",
        "n",
        "s",
        "e",
        "w",
        "u",
        "d",
        "ne",
        "nw",
        "se",
        "sw",
    ]

    # Character status patterns
    HP_PATTERN = re.compile(r"(?:HP|Health|Hit Points?):\s*(\d+)/(\d+)", re.IGNORECASE)
    MANA_PATTERN = re.compile(r"(?:MP|Mana|Magic):\s*(\d+)/(\d+)", re.IGNORECASE)
    LEVEL_PATTERN = re.compile(r"Level:\s*(\d+)", re.IGNORECASE)
    XP_PATTERN = re.compile(r"(?:XP|Experience):\s*(\d+)", re.IGNORECASE)
    GOLD_PATTERN = re.compile(r"(?:Gold|Money|Coins?):\s*(\d+)", re.IGNORECASE)

    # Money patterns (Cealdish currency)
    MONEY_PATTERN = re.compile(
        r"(\d+)\s*(?:gold\s*)?marks?|(\d+)\s*(?:silver\s*)?talents?|"
        r"(\d+)\s*(?:copper\s*)?jots?|(\d+)\s*(?:iron\s*)?drabs?",
        re.IGNORECASE,
    )

    # NPC/Player patterns - these appear in "You see:" sections
    SEE_PATTERN = re.compile(r"You see:\s*(.+?)(?:\n\n|\n[A-Z]|\Z)", re.IGNORECASE | re.DOTALL)
    ALSO_HERE_PATTERN = re.compile(r"Also here:\s*(.+?)(?:\n|$)", re.IGNORECASE)
    # NPC "is here" pattern used by look command (e.g., "a giant sewer rat is here")
    IS_HERE_PATTERN = re.compile(r"^(.+?)\s+is here\.", re.IGNORECASE | re.MULTILINE)

    # Item patterns
    ITEM_ON_GROUND_PATTERN = re.compile(
        r"(?:On the ground|Items?):\s*(.+?)(?:\n\n|\n[A-Z]|\Z)", re.IGNORECASE | re.DOTALL
    )

    # Combat patterns
    COMBAT_PATTERNS = [
        re.compile(r"attacks?\s+you", re.IGNORECASE),
        re.compile(r"you\s+attack", re.IGNORECASE),
        re.compile(r"damage", re.IGNORECASE),
        re.compile(r"combat", re.IGNORECASE),
        re.compile(r"fighting", re.IGNORECASE),
    ]

    # Action result patterns
    SUCCESS_PATTERNS = [
        re.compile(r"you\s+(?:get|take|pick\s+up)", re.IGNORECASE),
        re.compile(r"you\s+(?:drop|put|place)", re.IGNORECASE),
        re.compile(r"you\s+(?:go|move|walk|travel)", re.IGNORECASE),
        re.compile(r"you\s+(?:buy|sell|purchase)", re.IGNORECASE),
        re.compile(r"you\s+(?:say|tell|whisper)", re.IGNORECASE),
    ]

    FAILURE_PATTERNS = [
        re.compile(r"can'?t|cannot|unable", re.IGNORECASE),
        re.compile(r"no\s+exit", re.IGNORECASE),
        re.compile(r"not\s+found", re.IGNORECASE),
        re.compile(r"don'?t\s+have", re.IGNORECASE),
        re.compile(r"invalid|unknown", re.IGNORECASE),
    ]

    def __init__(self) -> None:
        """Initialize the parser."""
        self._current_state = GameState()

    @property
    def state(self) -> GameState:
        """Get current game state."""
        return self._current_state

    def strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes."""
        return self.ANSI_PATTERN.sub("", text)

    def parse(self, text: str) -> GameState:
        """
        Parse MUD output and update game state.

        Args:
            text: Raw MUD output text

        Returns:
            Updated GameState
        """
        clean = self.strip_ansi(text)
        self._current_state.raw_output = clean

        # Parse room information
        self._parse_room(clean)

        # Parse character status
        self._parse_status(clean)

        # Check combat state
        self._parse_combat(clean)

        # Parse action results
        self._parse_action_result(clean)

        return self._current_state

    def _parse_room(self, text: str) -> None:
        """Parse room information from text."""
        lines = text.strip().split("\n")
        if not lines:
            return

        # First non-empty line is often the room name
        for line in lines:
            line = line.strip()
            if line and line[0].isupper() and len(line) < 80:
                # Likely a room name
                self._current_state.room.name = line
                break

        # Parse exits
        exits = []
        exit_match = self.EXITS_PATTERN.search(text)
        if exit_match:
            exit_str = exit_match.group(1)
            exits = self._parse_exit_string(exit_str)
        else:
            exit_match = self.EXITS_LIST_PATTERN.search(text)
            if exit_match:
                exit_str = exit_match.group(1)
                exits = self._parse_exit_string(exit_str)

        if exits:
            self._current_state.room.exits = exits

        # Parse NPCs/players in room
        also_here = self.ALSO_HERE_PATTERN.search(text)
        if also_here:
            names = [n.strip() for n in also_here.group(1).split(",")]
            # Simple heuristic: NPCs usually have titles, players are just names
            for name in names:
                if any(word in name.lower() for word in ["guard", "merchant", "keeper", "master"]):
                    if name not in self._current_state.room.npcs:
                        self._current_state.room.npcs.append(name)
                else:
                    if name not in self._current_state.room.players:
                        self._current_state.room.players.append(name)

        # Parse "X is here" NPCs (used by look command for creatures)
        is_here_matches = self.IS_HERE_PATTERN.findall(text)
        for match in is_here_matches:
            name = match.strip()
            # Skip if it's a player-like name (capital first letter only, no articles)
            if name.startswith(("a ", "an ", "the ", "A ", "An ", "The ")):
                # This is likely an NPC/creature
                if name not in self._current_state.room.npcs:
                    self._current_state.room.npcs.append(name)

        # Parse items
        item_match = self.ITEM_ON_GROUND_PATTERN.search(text)
        if item_match:
            items = [i.strip() for i in item_match.group(1).split(",")]
            self._current_state.room.items = [i for i in items if i]

        # Extract description (text between name and exits)
        if self._current_state.room.name:
            name_end = text.find(self._current_state.room.name) + len(self._current_state.room.name)
            desc_text = text[name_end:].strip()

            # Find where description ends (usually at exits or "You see")
            desc_end = len(desc_text)
            for marker in ["[Exit", "Obvious exit", "You see:", "Also here:"]:
                pos = desc_text.find(marker)
                if pos > 0:
                    desc_end = min(desc_end, pos)

            if desc_end > 0:
                self._current_state.room.description = desc_text[:desc_end].strip()

    def _parse_exit_string(self, exit_str: str) -> list[Direction]:
        """Parse exits from an exit string."""
        exits = []
        # Split by common delimiters
        parts = re.split(r"[,\s]+", exit_str.lower())

        for part in parts:
            part = part.strip()
            if part in self.DIRECTION_WORDS:
                direction = Direction.from_string(part)
                if direction and direction not in exits:
                    exits.append(direction)

        return exits

    def _parse_status(self, text: str) -> None:
        """Parse character status from text."""
        # HP
        hp_match = self.HP_PATTERN.search(text)
        if hp_match:
            self._current_state.character.health = int(hp_match.group(1))
            self._current_state.character.max_health = int(hp_match.group(2))

        # Mana
        mana_match = self.MANA_PATTERN.search(text)
        if mana_match:
            self._current_state.character.mana = int(mana_match.group(1))
            self._current_state.character.max_mana = int(mana_match.group(2))

        # Level
        level_match = self.LEVEL_PATTERN.search(text)
        if level_match:
            self._current_state.character.level = int(level_match.group(1))

        # Experience/XP
        xp_match = self.XP_PATTERN.search(text)
        if xp_match:
            self._current_state.character.experience = int(xp_match.group(1))

        # Gold/Money
        gold_match = self.GOLD_PATTERN.search(text)
        if gold_match:
            self._current_state.character.gold = int(gold_match.group(1))

    def _parse_combat(self, text: str) -> None:
        """Detect if in combat."""
        for pattern in self.COMBAT_PATTERNS:
            if pattern.search(text):
                self._current_state.in_combat = True
                return
        self._current_state.in_combat = False

    def _parse_action_result(self, text: str) -> None:
        """Parse the result of the last action."""
        # Check for success
        for pattern in self.SUCCESS_PATTERNS:
            if pattern.search(text):
                self._current_state.last_action_result = "success"
                return

        # Check for failure
        for pattern in self.FAILURE_PATTERNS:
            if pattern.search(text):
                self._current_state.last_action_result = "failure"
                return

        self._current_state.last_action_result = "unknown"

    def to_context_string(self) -> str:
        """
        Generate a concise context string for the AI.

        Returns:
            String summary of current game state
        """
        state = self._current_state
        lines = []

        # Location
        if state.room.name:
            lines.append(f"Location: {state.room.name}")
            if state.room.description:
                lines.append(f"Description: {state.room.description[:200]}")

        # Exits
        if state.room.exits:
            exit_names = [e.value for e in state.room.exits]
            lines.append(f"Exits: {', '.join(exit_names)}")

        # NPCs/Players
        if state.room.npcs:
            lines.append(f"NPCs here: {', '.join(state.room.npcs)}")
        if state.room.players:
            lines.append(f"Players here: {', '.join(state.room.players)}")

        # Items
        if state.room.items:
            lines.append(f"Items here: {', '.join(state.room.items)}")

        # Character status
        lines.append(f"HP: {state.character.health}/{state.character.max_health}")
        if state.in_combat:
            lines.append("STATUS: IN COMBAT")

        # Last action
        if state.last_action_result and state.last_action_result != "unknown":
            lines.append(f"Last action: {state.last_action_result}")

        return "\n".join(lines)

    def get_available_actions(self) -> list[str]:
        """
        Get list of obviously available actions.

        Returns:
            List of action strings
        """
        actions = []

        # Movement
        for exit_dir in self._current_state.room.exits:
            actions.append(exit_dir.value)

        # Basic actions
        actions.extend(["look", "inventory", "score", "who", "help"])

        # Contextual
        if self._current_state.room.items:
            for item in self._current_state.room.items[:3]:
                actions.append(f"get {item}")

        if self._current_state.room.npcs:
            for npc in self._current_state.room.npcs[:2]:
                actions.append(f"look {npc}")

        return actions
