"""
Room module for Waystone MUD.

Defines the Room class representing a location in the game world.
"""

from pydantic import BaseModel, Field


class Room(BaseModel):
    """
    Represents a room (location) in the game world.

    Attributes:
        id: Unique identifier for the room (e.g., "university_main_gates")
        name: Display name shown to players (e.g., "The University Main Gates")
        area: The area/zone this room belongs to (e.g., "university", "imre")
        description: Full text description shown when players look at the room
        exits: Dictionary mapping direction to destination room_id
        properties: Boolean flags for room attributes (outdoor, lit, safe_zone, etc.)
        players: Set of character IDs currently in this room
    """

    id: str = Field(..., description="Unique room identifier")
    name: str = Field(..., description="Display name of the room")
    area: str = Field(..., description="Area/zone this room belongs to")
    description: str = Field(..., description="Full room description")
    exits: dict[str, str] = Field(
        default_factory=dict, description="Maps direction (e.g., 'north') to room_id"
    )
    properties: dict[str, bool | str] = Field(
        default_factory=dict,
        description="Room properties (outdoor, lit, safe_zone, requires_rank, etc.)",
    )
    players: set[str] = Field(
        default_factory=set, description="Character IDs of players currently in this room"
    )

    class Config:
        """Pydantic configuration."""

        # Allow sets to be serialized properly
        json_encoders = {set: list}

    def get_exit(self, direction: str) -> str | None:
        """
        Get the room_id for a given direction.

        Args:
            direction: The direction to check (e.g., "north", "south")

        Returns:
            The room_id if the exit exists, None otherwise
        """
        return self.exits.get(direction.lower())

    def add_player(self, character_id: str) -> None:
        """
        Add a player to this room.

        Args:
            character_id: The unique ID of the character entering the room
        """
        self.players.add(character_id)

    def remove_player(self, character_id: str) -> None:
        """
        Remove a player from this room.

        Args:
            character_id: The unique ID of the character leaving the room
        """
        self.players.discard(character_id)

    def is_outdoor(self) -> bool:
        """Check if this room is outdoors."""
        return bool(self.properties.get("outdoor", False))

    def is_lit(self) -> bool:
        """Check if this room is lit."""
        return bool(self.properties.get("lit", True))

    def is_safe_zone(self) -> bool:
        """Check if this room is a safe zone (no combat)."""
        return bool(self.properties.get("safe_zone", False))

    def get_required_rank(self) -> str | None:
        """Get the University rank required to enter this room, if any."""
        rank = self.properties.get("requires_rank")
        return str(rank) if rank else None

    def get_player_count(self) -> int:
        """Get the number of players currently in this room."""
        return len(self.players)

    def get_available_exits(self) -> list[str]:
        """
        Get a sorted list of available exit directions.

        Returns:
            List of direction strings (e.g., ["north", "south", "west"])
        """
        return sorted(self.exits.keys())

    def format_description(self) -> str:
        """
        Format the full room description for display to players.

        Returns:
            Formatted string with room name, description, and exits
        """
        lines = [
            f"\n{self.name}",
            "-" * len(self.name),
            self.description.strip(),
        ]

        if self.exits:
            exit_list = ", ".join(self.get_available_exits())
            lines.append(f"\n[Exits: {exit_list}]")
        else:
            lines.append("\n[Exits: none]")

        return "\n".join(lines)
