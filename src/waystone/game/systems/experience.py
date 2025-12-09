"""Experience and leveling system for Waystone MUD."""

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# XP Source Constants
XP_EXPLORATION_NEW_ROOM = 25
XP_FIRST_LOGIN = 100
XP_COMBAT_KILL_BASE = 50  # Multiplied by enemy level
XP_QUEST_COMPLETE_BASE = 100


def xp_for_level(level: int) -> int:
    """
    Calculate total XP required to reach a specific level.

    Uses quadratic scaling formula where XP to go from level N to N+1 is N * 100 * N.

    Args:
        level: The target level (1-based)

    Returns:
        Total XP required to reach that level from level 1

    Examples:
        Level 1: 0 XP (starting level)
        Level 2: 100 XP total (1*100*1)
        Level 3: 400 XP total (100 + 2*100*2 = 100 + 300 = 400, wait...)

    The formula is: sum of (n * 100 * n) for n from 1 to level-1
    Level 1→2: 1*100*1 = 100
    Level 2→3: 2*100*2 = 400? No, that doesn't match spec...

    Spec says:
    - Level 1→2: 100 XP
    - Level 2→3: 300 XP (400 total)
    - Level 3→4: 600 XP (1000 total)

    So the progression is: 100, 300, 600, 1000, 1500...
    Differences: 100, 200, 300, 400, 500...

    Actually reading the spec more carefully:
    "Formula: level * 100 * level (quadratic scaling)"
    This means XP from level N to N+1 is: N * 100 * N
    But examples show: 1→2 is 100, 2→3 is 300, 3→4 is 600

    Wait: 1*100*1=100 ✓, 2*100*2=400 ✗, 3*100*3=900 ✗

    Let me re-interpret: maybe it's (N-1) * 100 * N?
    0*100*1=0, 1*100*2=200, 2*100*3=600... still doesn't match

    Or maybe: N * 100?
    1*100=100 ✓, 2*100=200 ✗

    Looking at the pattern: 100, 300, 600
    Differences: 200, 300
    Second differences: 100 (constant!)

    This is: 100*n*(n+1)/2... no

    Actually: 100, 300, 600, 1000, 1500
    = 100*1, 100*3, 100*6, 100*10, 100*15
    = 100*(1, 3, 6, 10, 15)
    = 100 * triangular numbers * something...

    Let me try: XP(n→n+1) = n * 100
    1→2: 1*100 = 100 ✓
    2→3: 2*100 = 200 ✗ (need 300)

    Try: XP(n→n+1) = n * 100 + 100*triangular...

    Actually, let me look at cumulative:
    100, 400, 1000
    Differences: 300, 600

    So: 100, 100+300=400, 400+600=1000
    Pattern for increments: 100, 300, 600
    = 100*(1, 3, 6)
    = 100*(1, 1+2, 1+2+3)

    So XP from level n to n+1 = 100 * (1+2+...+n) = 100 * n*(n+1)/2

    Let's verify:
    1→2: 100*1*2/2 = 100 ✓
    2→3: 100*2*3/2 = 300 ✓
    3→4: 100*3*4/2 = 600 ✓
    """
    if level <= 1:
        return 0

    # Sum XP required for each level up to target level
    # XP from level n to n+1 is: 100 * n * (n+1) / 2
    total_xp = 0
    for n in range(1, level):
        total_xp += 100 * n * (n + 1) // 2

    return total_xp


def xp_for_next_level(level: int) -> int:
    """
    Calculate XP needed to go from current level to next level.

    Args:
        level: Current character level

    Returns:
        XP needed to reach the next level

    Examples:
        Level 1→2: 100 XP
        Level 2→3: 300 XP
        Level 3→4: 600 XP
    """
    # XP from level n to n+1 is: 100 * n * (n+1) / 2
    return 100 * level * (level + 1) // 2


def xp_progress(character: Character) -> tuple[int, int]:
    """
    Calculate character's XP progress toward next level.

    Args:
        character: The character to check

    Returns:
        Tuple of (current XP toward next level, XP needed for next level)

    Example:
        Character at level 2 with 250 XP total:
        - Needs 400 total XP for level 3
        - Has 250 XP, needs 400, so progress is (250, 400)
        - Actually needs to show progress within the level...
        - XP for level 2 is 100, so current progress is 250-100=150
        - XP needed for level 3 from level 2 is 300
        - Returns (150, 300)
    """
    current_level = character.level
    xp_for_current = xp_for_level(current_level)
    xp_for_next = xp_for_level(current_level + 1)

    # Current progress within this level
    current_progress = character.experience - xp_for_current
    # XP needed to complete this level
    needed_for_level = xp_for_next - xp_for_current

    return (current_progress, needed_for_level)


async def award_xp(
    character_id: "UUID",
    amount: int,
    source: str,
    session: "AsyncSession | None" = None,
) -> tuple[int, bool]:
    """
    Award experience points to a character and handle level-ups.

    Args:
        character_id: UUID of the character
        amount: Amount of XP to award
        source: Source description for logging (e.g., "combat_kill", "quest_complete")
        session: Optional existing database session (creates new if None)

    Returns:
        Tuple of (new total XP, did_level_up: bool)

    Raises:
        ValueError: If character not found
    """
    if session is not None:
        # Use the provided session
        return await _award_xp_with_session(character_id, amount, source, session)
    else:
        # Create a new session
        async with get_session() as new_session:
            return await _award_xp_with_session(character_id, amount, source, new_session)


async def _award_xp_with_session(
    character_id: "UUID",
    amount: int,
    source: str,
    session: "AsyncSession",
) -> tuple[int, bool]:
    """Internal implementation of award_xp with a session."""
    # Get character
    result = await session.execute(select(Character).where(Character.id == character_id))
    character = result.scalar_one_or_none()

    if not character:
        raise ValueError(f"Character with ID {character_id} not found")

    _old_level = character.level  # noqa: F841 - kept for potential logging
    old_xp = character.experience

    # Award XP
    character.experience += amount
    new_xp = character.experience

    logger.info(
        "xp_awarded",
        character_id=str(character_id),
        character_name=character.name,
        amount=amount,
        source=source,
        old_xp=old_xp,
        new_xp=new_xp,
    )

    # Check for level-up(s)
    leveled_up = False
    while character.experience >= xp_for_level(character.level + 1):
        level_up_result = await handle_level_up(character, session)
        leveled_up = True

        logger.info(
            "character_leveled_up",
            character_id=str(character_id),
            character_name=character.name,
            old_level=level_up_result["old_level"],
            new_level=level_up_result["new_level"],
            attribute_points_gained=level_up_result["attribute_points_gained"],
        )

    await session.commit()

    return (new_xp, leveled_up)


async def handle_level_up(character: Character, session: "AsyncSession") -> dict[str, int]:
    """
    Handle a character leveling up.

    Updates character stats:
    - Increments level
    - Grants 1 attribute point
    - Recalculates max_hp and max_mp based on new level and constitution
    - Heals character to full HP

    Args:
        character: The character leveling up
        session: Database session for updates

    Returns:
        Dictionary with level-up information:
        {
            "old_level": int,
            "new_level": int,
            "attribute_points_gained": int,
            "old_max_hp": int,
            "new_max_hp": int,
            "hp_restored": int,
        }
    """
    old_level = character.level
    old_max_hp = character.max_hp

    # Increment level
    character.level += 1

    # Grant 1 attribute point
    character.attribute_points = getattr(character, "attribute_points", 0) + 1

    # Recalculate max HP: 20 base + (level * constitution modifier)
    # Constitution modifier = (constitution - 10) // 2
    con_modifier = (character.constitution - 10) // 2
    # Each level grants additional HP: 5 + con_modifier (minimum 1)
    hp_per_level = max(1, 5 + con_modifier)
    character.max_hp = 20 + (character.level - 1) * hp_per_level

    # Store old HP to calculate restoration
    old_hp = character.current_hp

    # Heal to full on level-up
    character.current_hp = character.max_hp

    hp_restored = character.current_hp - old_hp

    logger.info(
        "level_up_processed",
        character_id=str(character.id),
        character_name=character.name,
        old_level=old_level,
        new_level=character.level,
        old_max_hp=old_max_hp,
        new_max_hp=character.max_hp,
        hp_restored=hp_restored,
    )

    return {
        "old_level": old_level,
        "new_level": character.level,
        "attribute_points_gained": 1,
        "old_max_hp": old_max_hp,
        "new_max_hp": character.max_hp,
        "hp_restored": hp_restored,
    }
