"""
World loader module for Waystone MUD.

Handles loading and validating room data from YAML files.
"""

from pathlib import Path
from typing import Any

import yaml

from .room import Room


class WorldLoadError(Exception):
    """Raised when there's an error loading world data."""

    pass


class RoomValidationError(Exception):
    """Raised when room validation fails."""

    pass


def load_yaml_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Load a YAML file containing room definitions.

    Args:
        file_path: Path to the YAML file

    Returns:
        List of room dictionaries

    Raises:
        WorldLoadError: If the file cannot be loaded or parsed
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise WorldLoadError(f"Empty YAML file: {file_path}")

        if "rooms" not in data:
            raise WorldLoadError(f"Missing 'rooms' key in {file_path}")

        rooms = data["rooms"]
        if not isinstance(rooms, list):
            raise WorldLoadError(f"'rooms' must be a list in {file_path}")

        return rooms

    except yaml.YAMLError as e:
        raise WorldLoadError(f"YAML parsing error in {file_path}: {e}")
    except FileNotFoundError:
        raise WorldLoadError(f"File not found: {file_path}")
    except Exception as e:
        raise WorldLoadError(f"Error loading {file_path}: {e}")


def validate_room_data(room_data: dict[str, Any], file_path: Path) -> None:
    """
    Validate that a room dictionary has all required fields.

    Args:
        room_data: Dictionary containing room data
        file_path: Path to the source file (for error messages)

    Raises:
        RoomValidationError: If required fields are missing
    """
    required_fields = ["id", "name", "area", "description"]

    for field in required_fields:
        if field not in room_data:
            room_id = room_data.get("id", "unknown")
            raise RoomValidationError(
                f"Room '{room_id}' in {file_path} missing required field: {field}"
            )

    # Validate exits is a dictionary if present
    if "exits" in room_data and not isinstance(room_data["exits"], dict):
        raise RoomValidationError(
            f"Room '{room_data['id']}' in {file_path} has invalid exits (must be a dict)"
        )

    # Validate properties is a dictionary if present
    if "properties" in room_data and not isinstance(room_data["properties"], dict):
        raise RoomValidationError(
            f"Room '{room_data['id']}' in {file_path} has invalid properties (must be a dict)"
        )


def create_room_from_data(room_data: dict[str, Any]) -> Room:
    """
    Create a Room instance from dictionary data.

    Args:
        room_data: Dictionary containing room data

    Returns:
        Room instance

    Raises:
        RoomValidationError: If Pydantic validation fails
    """
    try:
        return Room(**room_data)
    except Exception as e:
        raise RoomValidationError(f"Failed to create room '{room_data.get('id', 'unknown')}': {e}")


def load_rooms_from_directory(directory: Path) -> dict[str, Room]:
    """
    Load all room YAML files from a directory.

    Args:
        directory: Path to the directory containing YAML files

    Returns:
        Dictionary mapping room_id to Room instances

    Raises:
        WorldLoadError: If directory doesn't exist or files can't be loaded
        RoomValidationError: If room validation fails
    """
    if not directory.exists():
        raise WorldLoadError(f"Directory does not exist: {directory}")

    if not directory.is_dir():
        raise WorldLoadError(f"Not a directory: {directory}")

    rooms: dict[str, Room] = {}
    yaml_files = list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))

    if not yaml_files:
        raise WorldLoadError(f"No YAML files found in {directory}")

    for yaml_file in yaml_files:
        room_list = load_yaml_file(yaml_file)

        for room_data in room_list:
            validate_room_data(room_data, yaml_file)
            room = create_room_from_data(room_data)

            # Check for duplicate room IDs
            if room.id in rooms:
                raise RoomValidationError(f"Duplicate room ID '{room.id}' found in {yaml_file}")

            rooms[room.id] = room

    return rooms


def validate_exits(rooms: dict[str, Room]) -> list[str]:
    """
    Validate that all room exits are bidirectional and point to existing rooms.

    Args:
        rooms: Dictionary of room_id to Room instances

    Returns:
        List of warning messages (non-critical issues)

    Raises:
        RoomValidationError: If critical exit validation fails
    """
    warnings: list[str] = []
    all_room_ids = set(rooms.keys())

    for room_id, room in rooms.items():
        for direction, target_room_id in room.exits.items():
            # Check if target room exists
            if target_room_id not in all_room_ids:
                raise RoomValidationError(
                    f"Room '{room_id}' has exit '{direction}' to non-existent room '{target_room_id}'"
                )

            # Check for bidirectional exits
            target_room = rooms[target_room_id]
            reverse_direction = get_reverse_direction(direction)

            if reverse_direction and reverse_direction not in target_room.exits:
                warnings.append(
                    f"Non-bidirectional exit: '{room_id}' -> '{direction}' -> '{target_room_id}', "
                    f"but '{target_room_id}' has no '{reverse_direction}' exit back"
                )
            elif reverse_direction and target_room.exits.get(reverse_direction) != room_id:
                warnings.append(
                    f"Mismatched bidirectional exit: '{room_id}' -> '{direction}' -> '{target_room_id}', "
                    f"but '{target_room_id}' '{reverse_direction}' points to '{target_room.exits[reverse_direction]}'"
                )

    return warnings


def get_reverse_direction(direction: str) -> str | None:
    """
    Get the reverse of a direction.

    Args:
        direction: The original direction (e.g., "north")

    Returns:
        The reverse direction (e.g., "south"), or None if not found
    """
    reverse_map = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "northeast": "southwest",
        "northwest": "southeast",
        "southeast": "northwest",
        "southwest": "northeast",
        "up": "down",
        "down": "up",
        "in": "out",
        "out": "in",
    }
    return reverse_map.get(direction.lower())


def load_all_rooms(data_dir: Path | None = None) -> dict[str, Room]:
    """
    Load all rooms from the data directory and validate them.

    This is the main entry point for loading the game world.

    Args:
        data_dir: Path to the data directory. If None, uses default location.

    Returns:
        Dictionary mapping room_id to Room instances

    Raises:
        WorldLoadError: If loading fails
        RoomValidationError: If validation fails
    """
    if data_dir is None:
        # Default to data/world/rooms/ relative to project root
        # This assumes we're running from the project root
        data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "world" / "rooms"

    rooms = load_rooms_from_directory(data_dir)

    # Validate exits
    warnings = validate_exits(rooms)

    if warnings:
        print("⚠️  Exit validation warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    print(f"✅ Successfully loaded {len(rooms)} rooms")

    return rooms


def get_room_by_id(rooms: dict[str, Room], room_id: str) -> Room | None:
    """
    Get a room by its ID.

    Args:
        rooms: Dictionary of all rooms
        room_id: The ID of the room to retrieve

    Returns:
        The Room instance, or None if not found
    """
    return rooms.get(room_id)


def get_rooms_by_area(rooms: dict[str, Room], area: str) -> list[Room]:
    """
    Get all rooms in a specific area.

    Args:
        rooms: Dictionary of all rooms
        area: The area name (e.g., "university", "imre")

    Returns:
        List of Room instances in that area
    """
    return [room for room in rooms.values() if room.area == area]
