"""Character attributes and derived stats for Waystone MUD.

This module provides attribute management, modifier calculations, and derived stats
that are themed around the Kingkiller Chronicle universe while using D&D-style mechanics.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waystone.database.models.character import Character, CharacterBackground


class AttributeName(StrEnum):
    """Core character attributes."""

    STRENGTH = "strength"
    DEXTERITY = "dexterity"
    CONSTITUTION = "constitution"
    INTELLIGENCE = "intelligence"
    WISDOM = "wisdom"
    CHARISMA = "charisma"


# Constant attribute names for easy import
ATTRIBUTE_NAMES = [attr.value for attr in AttributeName]


@dataclass(frozen=True)
class AttributeModifiers:
    """Container for all attribute modifiers."""

    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


@dataclass(frozen=True)
class DerivedStats:
    """Container for all derived character statistics."""

    max_hp: int
    max_mp: int  # Alar/mental energy
    attack_bonus: int  # Melee attack bonus
    ranged_attack_bonus: int  # Ranged attack bonus
    defense: int
    carry_capacity: int  # In pounds


def get_modifier(value: int) -> int:
    """Calculate D&D-style attribute modifier.

    Args:
        value: The attribute value (typically 1-20+)

    Returns:
        The modifier: (value - 10) // 2

    Examples:
        >>> get_modifier(10)
        0
        >>> get_modifier(18)
        4
        >>> get_modifier(8)
        -1
    """
    return (value - 10) // 2


def get_background_bonuses(background: "CharacterBackground") -> dict[str, int]:
    """Get attribute bonuses based on character background.

    Each background provides thematic bonuses representing the character's past.

    Args:
        background: The CharacterBackground enum value

    Returns:
        Dictionary mapping attribute names to bonus values

    Background bonuses:
        - SCHOLAR: +2 INT (years of study at the University)
        - MERCHANT: +1 CHA, +1 WIS (negotiation and street smarts)
        - PERFORMER: +2 CHA (captivating audiences and social grace)
        - WAYFARER: +1 DEX, +1 CON (travel-hardened survivor)
        - NOBLE: +1 INT, +1 CHA (education and breeding)
        - COMMONER: +1 CON, +1 STR (hard physical labor)
    """
    from waystone.database.models.character import CharacterBackground

    bonuses: dict[CharacterBackground, dict[str, int]] = {
        CharacterBackground.SCHOLAR: {"intelligence": 2},
        CharacterBackground.MERCHANT: {"charisma": 1, "wisdom": 1},
        CharacterBackground.PERFORMER: {"charisma": 2},
        CharacterBackground.WAYFARER: {"dexterity": 1, "constitution": 1},
        CharacterBackground.NOBLE: {"intelligence": 1, "charisma": 1},
        CharacterBackground.COMMONER: {"constitution": 1, "strength": 1},
    }

    return bonuses.get(background, {})


def calculate_modifiers(character: "Character") -> AttributeModifiers:
    """Calculate all attribute modifiers for a character.

    Args:
        character: The Character model instance

    Returns:
        AttributeModifiers with all calculated modifiers
    """
    return AttributeModifiers(
        strength=get_modifier(character.strength),
        dexterity=get_modifier(character.dexterity),
        constitution=get_modifier(character.constitution),
        intelligence=get_modifier(character.intelligence),
        wisdom=get_modifier(character.wisdom),
        charisma=get_modifier(character.charisma),
    )


def calculate_derived_stats(character: "Character") -> dict[str, int]:
    """Calculate all derived stats for a character.

    Formulas are themed around the Kingkiller Chronicle universe:
    - HP: Physical endurance (constitution-based)
    - MP (Alar): Mental energy for sympathy (intelligence + wisdom)
    - Attack: Melee (strength) and ranged (dexterity) combat ability
    - Defense: Agility-based damage avoidance
    - Carry capacity: Physical strength determines encumbrance

    Args:
        character: The Character model instance

    Returns:
        Dictionary with derived stat names and calculated values:
        - max_hp: 10 + (CON modifier * level) + level
        - max_mp: 5 + (INT modifier * level) + (WIS modifier * level // 2)
        - attack_bonus: STR modifier (melee)
        - ranged_attack_bonus: DEX modifier (ranged)
        - defense: 10 + DEX modifier
        - carry_capacity: 10 + (STR * 5) pounds
    """
    mods = calculate_modifiers(character)
    level = character.level

    # Maximum hit points: base 10 + CON bonus per level + level bonus
    max_hp = 10 + (mods.constitution * level) + level

    # Maximum mental energy (Alar): base 5 + INT bonus per level + half WIS bonus
    max_mp = 5 + (mods.intelligence * level) + (mods.wisdom * level // 2)

    # Attack bonuses: STR for melee, DEX for ranged
    attack_bonus = mods.strength
    ranged_attack_bonus = mods.dexterity

    # Defense: base 10 + agility modifier
    defense = 10 + mods.dexterity

    # Carry capacity in pounds: base 10 + 5 per point of strength
    carry_capacity = 10 + (character.strength * 5)

    return {
        "max_hp": max_hp,
        "max_mp": max_mp,
        "attack_bonus": attack_bonus,
        "ranged_attack_bonus": ranged_attack_bonus,
        "defense": defense,
        "carry_capacity": carry_capacity,
    }


def apply_attribute_bonuses(
    character: "Character", equipment_bonuses: dict[str, int]
) -> dict[str, int]:
    """Calculate total attributes including equipment bonuses.

    Args:
        character: The Character model instance
        equipment_bonuses: Dictionary mapping attribute names to bonus values
            Example: {"strength": 2, "dexterity": 1}

    Returns:
        Dictionary with attribute names mapped to total values (base + bonuses)
    """
    base_attributes = {
        "strength": character.strength,
        "dexterity": character.dexterity,
        "constitution": character.constitution,
        "intelligence": character.intelligence,
        "wisdom": character.wisdom,
        "charisma": character.charisma,
    }

    # Apply equipment bonuses to base attributes
    total_attributes = {}
    for attr_name, base_value in base_attributes.items():
        bonus = equipment_bonuses.get(attr_name, 0)
        total_attributes[attr_name] = base_value + bonus

    return total_attributes


def get_total_attributes_with_equipment(
    character: "Character", equipment_bonuses: dict[str, int] | None = None
) -> dict[str, int]:
    """Get total attribute values including all bonuses.

    This is a convenience function that combines base attributes with
    equipment bonuses.

    Args:
        character: The Character model instance
        equipment_bonuses: Optional dictionary of equipment bonuses

    Returns:
        Dictionary with final attribute values including all bonuses
    """
    if equipment_bonuses is None:
        equipment_bonuses = {}

    return apply_attribute_bonuses(character, equipment_bonuses)
