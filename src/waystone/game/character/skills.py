"""Skills system for Waystone MUD.

Implements character skill progression with ranks, XP, and bonuses.
Based on the Kingkiller Chronicle universe.
"""

import pathlib
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models.character import Character

# Skill rank definitions
RANK_NAMES = {
    0: "Untrained",
    1: "Novice",
    2: "Novice",
    3: "Apprentice",
    4: "Apprentice",
    5: "Journeyman",
    6: "Journeyman",
    7: "Expert",
    8: "Expert",
    9: "Master",
    10: "Grandmaster",
}

# Maximum skill rank
MAX_RANK = 10


def get_skill_rank_name(rank: int) -> str:
    """Get the name for a skill rank.

    Args:
        rank: Skill rank (0-10)

    Returns:
        Name of the rank (e.g., "Apprentice", "Master")
    """
    if rank < 0:
        return "Untrained"
    if rank > MAX_RANK:
        return "Grandmaster"
    return RANK_NAMES.get(rank, "Unknown")


def xp_for_rank(rank: int) -> int:
    """Calculate XP required to reach a given rank.

    Args:
        rank: Target rank (1-10)

    Returns:
        XP required to reach this rank from the previous rank
    """
    if rank <= 0:
        return 0
    return rank * 100


def get_skill_bonus(rank: int) -> int:
    """Calculate skill bonus/modifier for checks.

    Args:
        rank: Skill rank (0-10)

    Returns:
        Bonus modifier for skill checks
    """
    if rank <= 0:
        return 0
    # +1 per rank, so rank 5 = +5, rank 10 = +10
    return rank


async def gain_skill_xp(
    character: Character,
    skill_name: str,
    amount: int,
    session: AsyncSession,
) -> tuple[int, bool]:
    """Grant skill XP to a character and handle rank-ups.

    Args:
        character: Character gaining XP
        skill_name: Name of the skill
        amount: Amount of XP to grant
        session: Database session

    Returns:
        Tuple of (new_xp, ranked_up)
        - new_xp: Total XP in the skill after gain
        - ranked_up: Whether the character gained a rank
    """
    # Initialize skill if not present
    if skill_name not in character.skills:
        character.skills[skill_name] = {"rank": 0, "xp": 0}

    skill_data = character.skills[skill_name]
    current_rank = skill_data["rank"]
    current_xp = skill_data["xp"]

    # Add XP
    new_xp = current_xp + amount
    skill_data["xp"] = new_xp

    # Check for rank-up (possibly multiple ranks)
    ranked_up = False
    new_rank = current_rank
    while new_rank < MAX_RANK:
        xp_needed = xp_for_rank(new_rank + 1)
        if new_xp >= xp_needed:
            new_rank += 1
            ranked_up = True
        else:
            break

    if ranked_up:
        skill_data["rank"] = new_rank

    # Update character skills (need to reassign for SQLAlchemy change tracking)
    character.skills = dict(character.skills)

    # Commit changes
    session.add(character)
    await session.commit()

    return new_xp, ranked_up


def load_skill_definitions() -> dict[str, Any]:
    """Load skill definitions from YAML configuration.

    Returns:
        Dictionary of skill definitions organized by category
    """
    # Find skills.yaml in data/config
    config_path = (
        pathlib.Path(__file__).parent.parent.parent.parent.parent
        / "data"
        / "config"
        / "skills.yaml"
    )

    if not config_path.exists():
        return {}

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_all_skills() -> list[str]:
    """Get list of all available skill names.

    Returns:
        List of skill names
    """
    definitions = load_skill_definitions()
    skills = []

    for category in definitions.values():
        if isinstance(category, dict):
            skills.extend(category.keys())

    return sorted(skills)


def get_skill_info(skill_name: str) -> dict[str, Any] | None:
    """Get information about a specific skill.

    Args:
        skill_name: Name of the skill

    Returns:
        Skill information dict or None if not found
    """
    definitions = load_skill_definitions()

    for category in definitions.values():
        if isinstance(category, dict) and skill_name in category:
            return category[skill_name]

    return None


def get_xp_progress(current_xp: int, current_rank: int) -> tuple[int, int]:
    """Calculate XP progress for current rank.

    Args:
        current_xp: Total XP in the skill
        current_rank: Current skill rank

    Returns:
        Tuple of (current_progress, xp_needed) for next rank
    """
    if current_rank >= MAX_RANK:
        return current_xp, current_xp  # Max rank reached

    xp_needed = xp_for_rank(current_rank + 1)
    return current_xp, xp_needed


def format_skill_bar(current_xp: int, xp_needed: int, width: int = 10) -> str:
    """Format a progress bar for skill XP.

    Args:
        current_xp: Current XP
        xp_needed: XP needed for next rank
        width: Width of the bar in characters

    Returns:
        Progress bar string (e.g., "████░░░░░░")
    """
    if xp_needed == 0:
        return "█" * width

    progress = min(1.0, current_xp / xp_needed)
    filled = int(progress * width)
    empty = width - filled

    return ("█" * filled) + ("░" * empty)
