"""Quest system for Waystone MUD.

Handles:
- Quest template definitions
- Quest acceptance and tracking
- Objective progress updates
- Quest completion and rewards
- Quest abandonment
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.database.models.quest import Quest, QuestStatus

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


@dataclass
class QuestObjective:
    """Quest objective definition."""

    type: str  # kill, gather, explore, talk, deliver
    target_id: str  # NPC template ID, item ID, room ID, etc.
    target_name: str  # Display name for the target
    target_count: int  # Number required (1 for talk/explore)
    current_count: int = 0  # Current progress

    def is_complete(self) -> bool:
        """Check if objective is complete."""
        return self.current_count >= self.target_count

    def progress_percent(self) -> float:
        """Calculate progress as percentage."""
        if self.target_count == 0:
            return 100.0
        return min(100.0, (self.current_count / self.target_count) * 100.0)


@dataclass
class QuestReward:
    """Quest reward definition."""

    xp: int = 0
    money: int = 0  # In drabs
    items: list[str] = field(default_factory=list)  # Item template IDs


@dataclass
class QuestTemplate:
    """Quest template definition."""

    id: str
    title: str
    description: str
    level_requirement: int
    objectives: list[QuestObjective]
    rewards: QuestReward
    repeatable: bool = False
    prerequisite_quests: list[str] = field(default_factory=list)

    def can_accept(self, character: Character, completed_quest_ids: list[str]) -> tuple[bool, str]:
        """Check if character can accept this quest.

        Returns:
            Tuple of (can_accept, reason_message)
        """
        # Check level requirement
        if character.level < self.level_requirement:
            return (
                False,
                f"You must be at least level {self.level_requirement} to accept this quest.",
            )

        # Check prerequisites
        for prereq_id in self.prerequisite_quests:
            if prereq_id not in completed_quest_ids:
                prereq_template = QUEST_TEMPLATES.get(prereq_id)
                prereq_name = prereq_template.title if prereq_template else "Unknown Quest"
                return (
                    False,
                    f"You must complete '{prereq_name}' before accepting this quest.",
                )

        return (True, "")

    def all_objectives_complete(self, progress: dict[str, Any]) -> bool:
        """Check if all objectives are complete based on progress data."""
        for obj in self.objectives:
            obj_key = f"{obj.type}_{obj.target_id}"
            obj_progress = progress.get(obj_key, {})
            current = obj_progress.get("current", 0)
            if current < obj.target_count:
                return False
        return True


# Quest template definitions
QUEST_TEMPLATES: dict[str, QuestTemplate] = {
    "welcome_to_imre": QuestTemplate(
        id="welcome_to_imre",
        title="Welcome to Imre",
        description=(
            "You've just arrived in Imre, the great city across the river from the University. "
            "Explore the city and speak with the locals to get your bearings. "
            "Visit the Eolian tavern to hear some music and meet fellow travelers."
        ),
        level_requirement=1,
        objectives=[
            QuestObjective(
                type="explore",
                target_id="imre_eolian",
                target_name="the Eolian tavern",
                target_count=1,
            ),
            QuestObjective(
                type="talk",
                target_id="deoch_bartender",
                target_name="Deoch the bartender",
                target_count=1,
            ),
        ],
        rewards=QuestReward(
            xp=50,
            money=25,  # 25 drabs
        ),
        repeatable=False,
    ),
    "rat_problem": QuestTemplate(
        id="rat_problem",
        title="The Rat Problem",
        description=(
            "The sewers beneath Imre are infested with rats. The city guard is offering "
            "a bounty for anyone brave enough to venture below and thin their numbers. "
            "Kill 5 sewer rats to earn your reward."
        ),
        level_requirement=1,
        objectives=[
            QuestObjective(
                type="kill",
                target_id="sewer_rat",
                target_name="sewer rats",
                target_count=5,
            ),
        ],
        rewards=QuestReward(
            xp=75,
            money=50,
        ),
        repeatable=True,  # Daily quest
    ),
    "sympathy_lessons": QuestTemplate(
        id="sympathy_lessons",
        title="Sympathy Lessons",
        description=(
            "Master Hemme at the University is willing to teach you the basics of sympathy. "
            "Gather the materials he needs: 2 candles for heat sources and 1 iron rod "
            "to practice kinetic bindings. Return to him when you have everything."
        ),
        level_requirement=2,
        objectives=[
            QuestObjective(
                type="gather",
                target_id="candle",
                target_name="candles",
                target_count=2,
            ),
            QuestObjective(
                type="gather",
                target_id="iron_rod",
                target_name="iron rod",
                target_count=1,
            ),
            QuestObjective(
                type="talk",
                target_id="master_hemme",
                target_name="Master Hemme",
                target_count=1,
            ),
        ],
        rewards=QuestReward(
            xp=100,
            money=75,
            items=["student_robes"],
        ),
        repeatable=False,
        prerequisite_quests=["welcome_to_imre"],
    ),
}


async def get_active_quests(character_id: UUID | str) -> list[Quest]:
    """Get all active quests for a character.

    Args:
        character_id: Character UUID

    Returns:
        List of active Quest instances
    """
    try:
        character_uuid = UUID(str(character_id))
        async with get_session() as session:
            result = await session.execute(
                select(Quest)
                .where(Quest.character_id == character_uuid)
                .where(Quest.status == QuestStatus.ACTIVE)
                .order_by(Quest.started_at)
            )
            return list(result.scalars().all())
    except Exception as e:
        logger.error(
            "get_active_quests_failed",
            character_id=str(character_id),
            error=str(e),
            exc_info=True,
        )
        return []


async def get_completed_quest_ids(character_id: UUID | str) -> list[str]:
    """Get list of completed quest template IDs for a character.

    Args:
        character_id: Character UUID

    Returns:
        List of quest template IDs
    """
    try:
        character_uuid = UUID(str(character_id))
        async with get_session() as session:
            result = await session.execute(
                select(Quest.quest_template_id)
                .where(Quest.character_id == character_uuid)
                .where(Quest.status == QuestStatus.COMPLETED)
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.error(
            "get_completed_quest_ids_failed",
            character_id=str(character_id),
            error=str(e),
            exc_info=True,
        )
        return []


async def has_active_quest(character_id: UUID | str, quest_template_id: str) -> bool:
    """Check if character has an active quest with given template ID.

    Args:
        character_id: Character UUID
        quest_template_id: Quest template identifier

    Returns:
        True if quest is active
    """
    try:
        character_uuid = UUID(str(character_id))
        async with get_session() as session:
            result = await session.execute(
                select(Quest)
                .where(Quest.character_id == character_uuid)
                .where(Quest.quest_template_id == quest_template_id)
                .where(Quest.status == QuestStatus.ACTIVE)
            )
            return result.scalar_one_or_none() is not None
    except Exception as e:
        logger.error(
            "has_active_quest_failed",
            character_id=str(character_id),
            quest_template_id=quest_template_id,
            error=str(e),
            exc_info=True,
        )
        return False


async def accept_quest(
    character: Character,
    quest_template_id: str,
) -> tuple[bool, str, Quest | None]:
    """Accept a new quest.

    Args:
        character: Character accepting the quest
        quest_template_id: Quest template identifier

    Returns:
        Tuple of (success, message, quest_instance)
    """
    template = QUEST_TEMPLATES.get(quest_template_id)
    if not template:
        return (False, "Quest not found.", None)

    # Check if already active
    if await has_active_quest(character.id, quest_template_id):
        return (False, "You already have this quest active.", None)

    # Check if already completed (and not repeatable)
    completed_quest_ids = await get_completed_quest_ids(character.id)
    if not template.repeatable and quest_template_id in completed_quest_ids:
        return (False, "You have already completed this quest.", None)

    # Check requirements
    can_accept, reason = template.can_accept(character, completed_quest_ids)
    if not can_accept:
        return (False, reason, None)

    # Initialize progress tracking
    progress: dict[str, Any] = {}
    for obj in template.objectives:
        obj_key = f"{obj.type}_{obj.target_id}"
        progress[obj_key] = {
            "current": 0,
            "required": obj.target_count,
        }

    # Create quest instance
    try:
        async with get_session() as session:
            quest = Quest(
                character_id=character.id,
                quest_template_id=quest_template_id,
                status=QuestStatus.ACTIVE,
                started_at=datetime.now(UTC),
                progress=progress,
            )
            session.add(quest)
            await session.commit()
            await session.refresh(quest)

            logger.info(
                "quest_accepted",
                character_id=str(character.id),
                character_name=character.name,
                quest_id=quest_template_id,
                quest_title=template.title,
            )

            return (True, f"Quest accepted: {template.title}", quest)

    except Exception as e:
        logger.error(
            "accept_quest_failed",
            character_id=str(character.id),
            quest_template_id=quest_template_id,
            error=str(e),
            exc_info=True,
        )
        return (False, "Failed to accept quest. Please try again.", None)


async def update_quest_progress(
    character_id: UUID | str,
    objective_type: str,
    target_id: str,
    increment: int = 1,
) -> list[tuple[Quest, QuestTemplate]]:
    """Update progress for matching quest objectives.

    Args:
        character_id: Character UUID
        objective_type: Objective type (kill, gather, explore, talk)
        target_id: Target identifier
        increment: Amount to increment progress by

    Returns:
        List of (quest, template) tuples for quests that were updated
    """
    updated_quests: list[tuple[Quest, QuestTemplate]] = []
    character_uuid = UUID(str(character_id))

    try:
        async with get_session() as session:
            # Get all active quests
            result = await session.execute(
                select(Quest)
                .where(Quest.character_id == character_uuid)
                .where(Quest.status == QuestStatus.ACTIVE)
            )
            active_quests = list(result.scalars().all())

            for quest in active_quests:
                template = QUEST_TEMPLATES.get(quest.quest_template_id)
                if not template:
                    continue

                # Check if this quest has a matching objective
                obj_key = f"{objective_type}_{target_id}"
                if obj_key not in quest.progress:
                    continue

                # Update progress
                current = quest.progress[obj_key].get("current", 0)
                required = quest.progress[obj_key].get("required", 0)
                new_count = min(current + increment, required)

                if new_count > current:
                    quest.progress[obj_key]["current"] = new_count
                    flag_modified(quest, "progress")
                    updated_quests.append((quest, template))

                    logger.info(
                        "quest_progress_updated",
                        character_id=str(character_id),
                        quest_id=quest.quest_template_id,
                        objective_key=obj_key,
                        progress=f"{new_count}/{required}",
                    )

            await session.commit()

    except Exception as e:
        logger.error(
            "update_quest_progress_failed",
            character_id=str(character_id),
            objective_type=objective_type,
            target_id=target_id,
            error=str(e),
            exc_info=True,
        )

    return updated_quests


async def complete_quest(
    character: Character,
    quest: Quest,
) -> tuple[bool, str]:
    """Complete a quest and grant rewards.

    Args:
        character: Character completing the quest
        quest: Quest instance to complete

    Returns:
        Tuple of (success, message)
    """
    template = QUEST_TEMPLATES.get(quest.quest_template_id)
    if not template:
        return (False, "Quest template not found.")

    # Check if all objectives are complete
    if not template.all_objectives_complete(quest.progress):
        return (False, "Not all quest objectives are complete.")

    try:
        async with get_session() as session:
            # Refresh character and quest from database
            await session.merge(character)
            await session.merge(quest)

            # Grant rewards
            character.experience += template.rewards.xp
            character.money += template.rewards.money

            # Mark quest as complete
            quest.status = QuestStatus.COMPLETED
            quest.completed_at = datetime.now(UTC)

            await session.commit()

            logger.info(
                "quest_completed",
                character_id=str(character.id),
                character_name=character.name,
                quest_id=quest.quest_template_id,
                quest_title=template.title,
                xp_reward=template.rewards.xp,
                money_reward=template.rewards.money,
            )

            reward_parts = []
            if template.rewards.xp > 0:
                reward_parts.append(f"{template.rewards.xp} XP")
            if template.rewards.money > 0:
                reward_parts.append(f"{template.rewards.money} drabs")
            if template.rewards.items:
                reward_parts.append(f"{len(template.rewards.items)} item(s)")

            reward_str = ", ".join(reward_parts) if reward_parts else "no rewards"
            message = f"Quest completed: {template.title}! Rewards: {reward_str}"

            return (True, message)

    except Exception as e:
        logger.error(
            "complete_quest_failed",
            character_id=str(character.id),
            quest_id=quest.quest_template_id,
            error=str(e),
            exc_info=True,
        )
        return (False, "Failed to complete quest. Please try again.")


async def abandon_quest(
    character_id: UUID | str,
    quest: Quest,
) -> tuple[bool, str]:
    """Abandon an active quest.

    Args:
        character_id: Character UUID
        quest: Quest instance to abandon

    Returns:
        Tuple of (success, message)
    """
    template = QUEST_TEMPLATES.get(quest.quest_template_id)
    quest_title = template.title if template else "Unknown Quest"

    try:
        async with get_session() as session:
            await session.merge(quest)

            quest.status = QuestStatus.ABANDONED
            quest.completed_at = datetime.now(UTC)

            await session.commit()

            logger.info(
                "quest_abandoned",
                character_id=str(character_id),
                quest_id=quest.quest_template_id,
                quest_title=quest_title,
            )

            return (True, f"Quest abandoned: {quest_title}")

    except Exception as e:
        logger.error(
            "abandon_quest_failed",
            character_id=str(character_id),
            quest_id=quest.quest_template_id,
            error=str(e),
            exc_info=True,
        )
        return (False, "Failed to abandon quest. Please try again.")


def format_quest_objectives(template: QuestTemplate, progress: dict[str, Any]) -> list[str]:
    """Format quest objectives for display.

    Args:
        template: Quest template
        progress: Progress data from Quest instance

    Returns:
        List of formatted objective strings
    """
    lines = []
    for obj in template.objectives:
        obj_key = f"{obj.type}_{obj.target_id}"
        obj_progress = progress.get(obj_key, {})
        current = obj_progress.get("current", 0)
        required = obj.target_count

        # Format objective type
        type_str = obj.type.capitalize()
        if obj.type == "kill":
            type_str = "Slay"
        elif obj.type == "gather":
            type_str = "Gather"
        elif obj.type == "explore":
            type_str = "Visit"
        elif obj.type == "talk":
            type_str = "Speak with"

        # Check completion
        complete_marker = "[✓]" if current >= required else "[ ]"

        if obj.type in ["talk", "explore"]:
            # Single objective, no count
            lines.append(f"  {complete_marker} {type_str} {obj.target_name}")
        else:
            # Counted objective
            lines.append(
                f"  {complete_marker} {type_str} {obj.target_name}: {current}/{required}"
            )

    return lines
