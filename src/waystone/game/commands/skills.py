"""Skill commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.character.skills import (
    format_skill_bar,
    gain_skill_xp,
    get_all_skills,
    get_skill_bonus,
    get_skill_info,
    get_skill_rank_name,
    get_xp_progress,
    xp_for_rank,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class SkillsCommand(Command):
    """Display character skills with ranks and XP progress."""

    name = "skills"
    aliases = []
    help_text = "skills - Show all your skills with ranks and progress"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the skills command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to view skills.", "RED")
            )
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Get all available skills
                all_skills = get_all_skills()

                if not all_skills:
                    await ctx.connection.send_line(
                        colorize("No skills are available in the system.", "RED")
                    )
                    return

                # Display skills header
                await ctx.connection.send_line(
                    colorize(f"\n╔═══ {character.name}'s Skills ═══╗", "CYAN")
                )

                # Group skills by category
                categories = {
                    "Combat": ["swordplay", "archery", "unarmed"],
                    "Magic": ["sympathy", "sygaldry", "alchemy", "naming"],
                    "Practical": [
                        "medicine",
                        "music",
                        "rhetoric",
                        "survival",
                        "lore",
                        "lockpicking",
                        "stealth",
                    ],
                }

                for category_name, skill_names in categories.items():
                    # Check if character has any skills in this category
                    category_skills = [s for s in skill_names if s in all_skills]
                    if not category_skills:
                        continue

                    await ctx.connection.send_line(colorize(f"\n{category_name} Skills:", "YELLOW"))

                    for skill_name in category_skills:
                        # Get skill data from character
                        skill_data = character.skills.get(skill_name, {"rank": 0, "xp": 0})
                        rank = skill_data["rank"]
                        xp = skill_data["xp"]

                        # Get skill info
                        skill_info = get_skill_info(skill_name)
                        display_name = skill_info["name"] if skill_info else skill_name.title()

                        # Get rank name and bonus
                        rank_name = get_skill_rank_name(rank)
                        bonus = get_skill_bonus(rank)

                        # Calculate XP progress
                        current_xp, xp_needed = get_xp_progress(xp, rank)
                        progress_bar = format_skill_bar(current_xp, xp_needed)

                        # Format output
                        # Swordplay [Apprentice] ████░░░░░░ 350/400 (+3)
                        rank_display = colorize(f"[{rank_name}]", "GREEN")
                        bonus_display = colorize(f"(+{bonus})", "CYAN")
                        xp_display = f"{current_xp}/{xp_needed}"

                        # Special formatting for max rank
                        if rank >= 10:
                            rank_display = colorize("[Grandmaster]", "MAGENTA")
                            xp_display = colorize("MAX", "MAGENTA")

                        await ctx.connection.send_line(
                            f"  {display_name:16} {rank_display:20} "
                            f"{progress_bar} {xp_display:12} {bonus_display}"
                        )

                await ctx.connection.send_line(colorize("\n╚═════════════════════════╝", "CYAN"))
                await ctx.connection.send_line(
                    colorize(
                        f"Tip: Use '{colorize('train <skill>', 'GREEN')}' to practice and gain XP.",
                        "DIM",
                    )
                )

        except Exception as e:
            logger.error("skills_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to display skills.", "RED"))


class TrainCommand(Command):
    """Practice a skill to gain XP."""

    name = "train"
    aliases = []
    help_text = "train <skill> - Practice a skill to gain XP (costs money)"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the train command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to train skills.", "RED")
            )
            return

        skill_name = ctx.args[0].lower()

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Validate skill exists
                all_skills = get_all_skills()
                if skill_name not in all_skills:
                    await ctx.connection.send_line(colorize(f"Unknown skill: {skill_name}", "RED"))
                    await ctx.connection.send_line(
                        f"Available skills: {', '.join(sorted(all_skills))}"
                    )
                    return

                # Get skill info
                skill_info = get_skill_info(skill_name)
                display_name = skill_info["name"] if skill_info else skill_name.title()

                # Get current skill data
                skill_data = character.skills.get(skill_name, {"rank": 0, "xp": 0})
                current_rank = skill_data["rank"]

                # Check if skill is at max rank
                if current_rank >= 10:
                    await ctx.connection.send_line(
                        colorize(
                            f"You have already mastered {display_name} at Grandmaster rank!",
                            "YELLOW",
                        )
                    )
                    return

                # Calculate training cost (10 * target_rank talents)
                # For rank 0->1, cost is 10. For rank 5->6, cost is 60
                target_rank = current_rank + 1
                training_cost = 10 * target_rank

                # TODO: Implement currency system and deduct cost
                # For now, we'll just grant XP without cost

                # Grant XP (random amount between 25-50)
                import random

                xp_gain = random.randint(25, 50)

                new_xp, ranked_up = await gain_skill_xp(character, skill_name, xp_gain, session)

                # Notify player
                await ctx.connection.send_line(
                    colorize(f"\nYou practice {display_name}...", "CYAN")
                )
                await ctx.connection.send_line(
                    colorize(f"You gain {xp_gain} XP in {display_name}!", "GREEN")
                )

                if ranked_up:
                    new_rank = current_rank + 1
                    new_rank_name = get_skill_rank_name(new_rank)
                    new_bonus = get_skill_bonus(new_rank)

                    await ctx.connection.send_line(
                        colorize(
                            f"\n🎉 Congratulations! You've improved to {new_rank_name} "
                            f"rank in {display_name}! (Bonus: +{new_bonus})",
                            "MAGENTA",
                        )
                    )
                else:
                    # Show progress to next rank
                    next_rank_xp = xp_for_rank(current_rank + 1)
                    remaining = next_rank_xp - new_xp
                    await ctx.connection.send_line(
                        colorize(
                            f"Progress: {new_xp}/{next_rank_xp} XP "
                            f"({remaining} XP until next rank)",
                            "YELLOW",
                        )
                    )

                # TODO: Show cost when currency system is implemented
                # await ctx.connection.send_line(
                #     colorize(f"Training cost: {training_cost} talents", "DIM")
                # )

        except Exception as e:
            logger.error("train_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to train skill.", "RED"))
