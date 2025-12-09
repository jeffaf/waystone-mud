"""
NPC loader module for Waystone MUD.

Handles loading and validating NPC data from YAML files.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class NPCLoadError(Exception):
    """Raised when there's an error loading NPC data."""

    pass


class NPCValidationError(Exception):
    """Raised when NPC validation fails."""

    pass


class NPCTemplate(BaseModel):
    """
    NPC template loaded from YAML data.

    Attributes:
        id: Unique identifier for the NPC template (e.g., "bandit", "merchant_imre")
        name: Display name shown to players (e.g., "a scrappy bandit")
        description: Full text description shown when examining the NPC
        level: NPC level (affects combat difficulty)
        max_hp: Maximum hit points for this NPC type
        attributes: D&D style attributes (strength, dexterity, etc.)
        behavior: NPC behavior type (aggressive, passive, merchant, stationary, wander)
        loot_table_id: Optional reference to loot table for drops
        dialogue: Optional dialogue data for interactive NPCs
        respawn_time: Respawn time in seconds (0 = no respawn)
        keywords: Keywords for player commands (e.g., ['rat', 'giant', 'sewer'])
        short_description: Used in action messages (e.g., 'a giant sewer rat')
        long_description: Shown in room when present (e.g., 'A giant sewer rat is here.')
        equipment: Equipped items by slot (e.g., {'weapon': 'rusty_shortsword'})
        inventory: Item template IDs this NPC carries
    """

    id: str = Field(..., description="Unique NPC template identifier")
    name: str = Field(..., description="Display name of the NPC")
    description: str = Field(..., description="Full NPC description")
    level: int = Field(default=1, description="NPC level")
    max_hp: int = Field(default=20, description="Maximum hit points")
    attributes: dict[str, int] = Field(default_factory=dict, description="D&D style attributes")
    behavior: str = Field(
        default="passive",
        description="NPC behavior: aggressive, passive, merchant, stationary, wander",
    )
    loot_table_id: str | None = Field(default=None, description="Reference to loot table")
    dialogue: dict[str, Any] | None = Field(
        default=None, description="Dialogue data for interactive NPCs"
    )
    respawn_time: int = Field(default=300, description="Respawn time in seconds (0 = no respawn)")
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for player commands (e.g., ['rat', 'giant', 'sewer'])",
    )
    short_description: str = Field(
        default="", description="Used in action messages (e.g., 'a giant sewer rat')"
    )
    long_description: str = Field(
        default="", description="Shown in room when present (e.g., 'A giant sewer rat is here.')"
    )
    equipment: dict[str, str] = Field(
        default_factory=dict,
        description="Equipped items by slot: {'main_hand': 'rusty_shortsword', 'body': 'leather_armor'}",
    )
    inventory: list[str] = Field(
        default_factory=list, description="Item template IDs this NPC carries"
    )

    class Config:
        """Pydantic configuration."""

        # Allow for future extensibility
        extra = "allow"


class NPCSpawn(BaseModel):
    """
    Defines where an NPC should spawn in the game world.

    Attributes:
        template_id: ID of the NPCTemplate to spawn
        room_id: Room where this NPC should spawn
        count: Number of instances to spawn (default: 1)
    """

    template_id: str = Field(..., description="NPC template ID to spawn")
    room_id: str = Field(..., description="Room ID where NPC spawns")
    count: int = Field(default=1, ge=1, description="Number of NPCs to spawn")


def load_yaml_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Load a YAML file containing NPC definitions.

    Args:
        file_path: Path to the YAML file

    Returns:
        List of NPC dictionaries

    Raises:
        NPCLoadError: If the file cannot be loaded or parsed
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise NPCLoadError(f"Empty YAML file: {file_path}")

        if "npcs" not in data:
            raise NPCLoadError(f"Missing 'npcs' key in {file_path}")

        npcs = data["npcs"]
        if not isinstance(npcs, list):
            raise NPCLoadError(f"'npcs' must be a list in {file_path}")

        return npcs

    except yaml.YAMLError as e:
        raise NPCLoadError(f"YAML parsing error in {file_path}: {e}")
    except FileNotFoundError:
        raise NPCLoadError(f"File not found: {file_path}")
    except Exception as e:
        raise NPCLoadError(f"Error loading {file_path}: {e}")


def validate_npc_data(npc_data: dict[str, Any], file_path: Path) -> None:
    """
    Validate that an NPC dictionary has all required fields.

    Args:
        npc_data: Dictionary containing NPC data
        file_path: Path to the source file (for error messages)

    Raises:
        NPCValidationError: If required fields are missing or invalid
    """
    required_fields = ["id", "name", "description"]

    for field in required_fields:
        if field not in npc_data:
            npc_id = npc_data.get("id", "unknown")
            raise NPCValidationError(
                f"NPC '{npc_id}' in {file_path} missing required field: {field}"
            )

    # Validate level is positive
    if "level" in npc_data and npc_data["level"] < 1:
        raise NPCValidationError(
            f"NPC '{npc_data['id']}' in {file_path} has invalid level (must be >= 1)"
        )

    # Validate max_hp is positive
    if "max_hp" in npc_data and npc_data["max_hp"] < 1:
        raise NPCValidationError(
            f"NPC '{npc_data['id']}' in {file_path} has invalid max_hp (must be >= 1)"
        )

    # Validate behavior is recognized
    valid_behaviors = [
        "aggressive",
        "passive",
        "merchant",
        "stationary",
        "wander",
        "training_dummy",
    ]
    if "behavior" in npc_data and npc_data["behavior"] not in valid_behaviors:
        raise NPCValidationError(
            f"NPC '{npc_data['id']}' in {file_path} has invalid behavior "
            f"(must be one of: {', '.join(valid_behaviors)})"
        )

    # Validate attributes is a dictionary if present
    if "attributes" in npc_data and not isinstance(npc_data["attributes"], dict):
        raise NPCValidationError(
            f"NPC '{npc_data['id']}' in {file_path} has invalid attributes (must be a dict)"
        )

    # Validate dialogue is a dictionary if present
    if "dialogue" in npc_data:
        if npc_data["dialogue"] is not None and not isinstance(npc_data["dialogue"], dict):
            raise NPCValidationError(
                f"NPC '{npc_data['id']}' in {file_path} has invalid dialogue (must be a dict or null)"
            )


def create_npc_from_data(npc_data: dict[str, Any]) -> NPCTemplate:
    """
    Create an NPCTemplate instance from dictionary data.

    Args:
        npc_data: Dictionary containing NPC data

    Returns:
        NPCTemplate instance

    Raises:
        NPCValidationError: If Pydantic validation fails
    """
    try:
        return NPCTemplate(**npc_data)
    except Exception as e:
        raise NPCValidationError(
            f"Failed to create NPC template '{npc_data.get('id', 'unknown')}': {e}"
        )


def load_npcs_from_directory(directory: Path) -> dict[str, NPCTemplate]:
    """
    Load all NPC YAML files from a directory.

    Args:
        directory: Path to the directory containing YAML files

    Returns:
        Dictionary mapping npc_id to NPCTemplate instances

    Raises:
        NPCLoadError: If directory doesn't exist or files can't be loaded
        NPCValidationError: If NPC validation fails
    """
    if not directory.exists():
        raise NPCLoadError(f"Directory does not exist: {directory}")

    if not directory.is_dir():
        raise NPCLoadError(f"Not a directory: {directory}")

    npcs: dict[str, NPCTemplate] = {}
    yaml_files = list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))

    if not yaml_files:
        raise NPCLoadError(f"No YAML files found in {directory}")

    for yaml_file in yaml_files:
        npc_list = load_yaml_file(yaml_file)

        for npc_data in npc_list:
            validate_npc_data(npc_data, yaml_file)
            npc = create_npc_from_data(npc_data)

            # Check for duplicate NPC IDs
            if npc.id in npcs:
                raise NPCValidationError(f"Duplicate NPC ID '{npc.id}' found in {yaml_file}")

            npcs[npc.id] = npc

    return npcs


def load_all_npcs(data_dir: Path | None = None) -> dict[str, NPCTemplate]:
    """
    Load all NPC templates from the data directory and validate them.

    This is the main entry point for loading NPC templates.

    Args:
        data_dir: Path to the data directory. If None, uses default location.

    Returns:
        Dictionary mapping npc_id to NPCTemplate instances

    Raises:
        NPCLoadError: If loading fails
        NPCValidationError: If validation fails
    """
    if data_dir is None:
        # Default to data/world/npcs/ relative to project root
        data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "world" / "npcs"

    npcs = load_npcs_from_directory(data_dir)

    print(f"✅ Successfully loaded {len(npcs)} NPC templates")

    return npcs


def get_npc_by_id(npcs: dict[str, NPCTemplate], npc_id: str) -> NPCTemplate | None:
    """
    Get an NPC template by its ID.

    Args:
        npcs: Dictionary of all NPC templates
        npc_id: The ID of the NPC template to retrieve

    Returns:
        The NPCTemplate instance, or None if not found
    """
    return npcs.get(npc_id)


def get_npcs_by_behavior(npcs: dict[str, NPCTemplate], behavior: str) -> list[NPCTemplate]:
    """
    Get all NPC templates with a specific behavior.

    Args:
        npcs: Dictionary of all NPC templates
        behavior: The behavior type (e.g., "aggressive", "merchant")

    Returns:
        List of NPCTemplate instances with that behavior
    """
    return [npc for npc in npcs.values() if npc.behavior == behavior]
