"""NPC display utilities for Waystone MUD.

Provides functions for displaying NPCs in rooms and examinations, including:
- Health condition descriptors
- Equipment display formatting
- NPC keyword matching
- Room presence formatting
"""

from typing import TYPE_CHECKING

from waystone.game.systems.npc_combat import NPCInstance, get_npcs_in_room
from waystone.network import colorize

if TYPE_CHECKING:
    from waystone.game.commands.base import CommandContext


# Equipment slot definitions
EQUIPMENT_SLOTS = {
    "head": "worn on head",
    "body": "worn on body",
    "hands": "worn on hands",
    "legs": "worn on legs",
    "feet": "worn on feet",
    "main_hand": "wielded",
    "off_hand": "worn on off-hand",
    "accessory": "worn as accessory",
}

SLOT_ORDER = [
    "head",
    "body",
    "hands",
    "legs",
    "feet",
    "main_hand",
    "off_hand",
    "accessory",
]


def get_health_condition(npc: NPCInstance) -> str:
    """
    Generate descriptive health condition text based on HP percentage.

    Args:
        npc: NPC instance to check

    Returns:
        Formatted health condition string with appropriate color

    Health Condition Scale:
    - 100%: "in perfect health"
    - 75-99%: "slightly wounded"
    - 50-74%: "wounded"
    - 25-49%: "badly wounded"
    - 10-24%: "near death"
    - <10%: "mortally wounded"
    """
    if npc.max_hp <= 0:
        return colorize("Health unknown.", "DIM")

    hp_percent = (npc.current_hp / npc.max_hp) * 100

    if hp_percent >= 100:
        condition = "in perfect health"
        color = "GREEN"
    elif hp_percent >= 75:
        condition = "slightly wounded"
        color = "GREEN"
    elif hp_percent >= 50:
        condition = "wounded"
        color = "YELLOW"
    elif hp_percent >= 25:
        condition = "badly wounded"
        color = "ORANGE"
    elif hp_percent >= 10:
        condition = "near death"
        color = "RED"
    else:
        condition = "mortally wounded"
        color = "RED"

    # Use third-person for NPCs
    pronoun = _get_npc_pronoun(npc)

    return f"{pronoun.capitalize()} {_get_verb_form(pronoun)} {colorize(condition, color)}."


def _get_npc_pronoun(npc: NPCInstance) -> str:
    """Determine appropriate pronoun for NPC."""
    # Check if NPC is humanoid (simple heuristic)
    humanoid_keywords = ["merchant", "bandit", "guard", "scholar", "person", "human"]

    for keyword in humanoid_keywords:
        if keyword in npc.template_id.lower():
            return "they"  # Gender-neutral for humanoids

    # Animals/creatures use "it"
    return "it"


def _get_verb_form(pronoun: str) -> str:
    """Get proper verb form for pronoun."""
    if pronoun in ("he", "she", "it"):
        return "is"
    else:  # they
        return "are"


def get_short_health_status(npc: NPCInstance) -> str:
    """
    Get short health status for room descriptions.

    Returns simple text like "looks healthy", "has some wounds", etc.
    Used in look command when showing NPCs in room.
    """
    if npc.max_hp <= 0:
        return "looks strange"

    hp_percent = (npc.current_hp / npc.max_hp) * 100

    if hp_percent >= 75:
        return "looks healthy"
    elif hp_percent >= 50:
        return "has some wounds"
    elif hp_percent >= 25:
        return "is badly wounded"
    else:
        return "is near death"


async def display_npc_equipment(ctx: "CommandContext", npc: NPCInstance) -> None:
    """
    Display NPC equipment in formatted slot layout.

    Format:
    <worn on body..........> grey robes of the Archives
    <worn on head..........> a small silver pin
    <wielded...............> rusty shortsword
    <off-hand..............> nothing

    Args:
        ctx: Command context for output
        npc: NPC instance to display equipment for
    """
    if not npc.equipment:
        await ctx.connection.send_line("  Nothing equipped.")
        return

    # Display equipped items in standard slot order
    for slot in SLOT_ORDER:
        slot_label = EQUIPMENT_SLOTS.get(slot, slot)
        item_id = npc.equipment.get(slot)

        if item_id:
            # Get item display name from template
            item_name = get_item_display_name(item_id)

            # Format: <slot label> padded to 20 chars, then item name
            await ctx.connection.send_line(
                f"  <{slot_label:.<18}> {colorize(item_name, 'YELLOW')}"
            )
        else:
            # Show "nothing" for key slots (weapon, body armor)
            if slot in ("main_hand", "off_hand", "body"):
                await ctx.connection.send_line(
                    f"  <{slot_label:.<18}> {colorize('nothing', 'DIM')}"
                )


def get_item_display_name(item_id: str) -> str:
    """
    Get display name for an item from its template ID.

    Args:
        item_id: Item template identifier

    Returns:
        Human-readable item name

    Examples:
        "rusty_shortsword" -> "a rusty shortsword"
        "leather_armor_worn" -> "worn leather armor"
    """
    # TODO: Load from item templates when implemented
    # For now, use simple conversion

    # Remove underscores, convert to words
    words = item_id.replace('_', ' ')

    # Add article if not present
    if not words.startswith(('a ', 'an ', 'the ')):
        # Simple article logic (can be enhanced)
        if words[0].lower() in 'aeiou':
            words = f"an {words}"
        else:
            words = f"a {words}"

    return words


def find_npc_by_keywords(room_id: str, search_term: str) -> NPCInstance | None:
    """
    Find NPC in room by matching keywords.

    Uses fuzzy matching against NPC keywords field.
    More flexible than exact name matching.

    Args:
        room_id: Room to search
        search_term: Player's search input

    Returns:
        Matching NPC or None
    """
    search_lower = search_term.lower()

    for npc in get_npcs_in_room(room_id):
        # Check keywords first (best match)
        if npc.keywords:
            for keyword in npc.keywords:
                if keyword.lower() == search_lower:
                    return npc  # Exact keyword match

        # Fall back to name matching
        if search_lower in npc.name.lower():
            return npc

        # Check short description
        if search_lower in npc.short_description.lower():
            return npc

    return None


def group_npcs_by_template(npcs: list[NPCInstance]) -> dict[str, list[NPCInstance]]:
    """Group NPCs by template for count display."""
    groups: dict[str, list[NPCInstance]] = {}
    for npc in npcs:
        if npc.template_id not in groups:
            groups[npc.template_id] = []
        groups[npc.template_id].append(npc)
    return groups


def get_npc_color(npc: NPCInstance) -> str:
    """Determine display color based on NPC behavior."""
    if npc.behavior == "aggressive":
        return "RED"
    elif npc.behavior == "training_dummy":
        return "YELLOW"
    elif npc.behavior == "merchant":
        return "CYAN"
    elif npc.behavior in ("passive", "stationary"):
        return "GREEN"
    else:
        return "WHITE"


def format_npc_room_presence(npc: NPCInstance, count: int) -> str:
    """
    Format NPC presence line with count pluralization.

    Args:
        npc: NPC instance to format
        count: Number of identical NPCs

    Returns:
        Formatted presence string
    """
    if count == 1:
        return npc.long_description
    elif count == 2:
        # Simple pluralization
        return npc.long_description.replace(" is here", " are here (x2)")
    else:
        # Numeric count with pluralized name
        name_plural = _pluralize_npc_name(npc.short_description)
        return f"{_number_to_word(count).capitalize()} {name_plural} are here."


def _pluralize_npc_name(name: str) -> str:
    """Simple pluralization for NPC names."""
    # Remove article (a, an, the) before pluralizing
    words = name.split()
    if words and words[0].lower() in ('a', 'an', 'the'):
        words = words[1:]  # Remove article

    name_without_article = ' '.join(words)

    # Basic rules (can be enhanced)
    if name_without_article.endswith('s'):
        return name_without_article
    elif name_without_article.endswith('y'):
        return name_without_article[:-1] + 'ies'
    elif name_without_article.endswith(('sh', 'ch')):
        return name_without_article + 'es'
    else:
        return name_without_article + 's'


def _number_to_word(num: int) -> str:
    """Convert small numbers to words."""
    number_words = {
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten"
    }
    return number_words.get(num, str(num))
