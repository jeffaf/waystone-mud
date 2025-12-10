"""Quest commands for Waystone MUD."""

import structlog

from waystone.game.systems.quest import (
    QUEST_TEMPLATES,
    abandon_quest,
    format_quest_objectives,
    get_active_quests,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class QuestLogCommand(Command):
    """Display active quests."""

    name = "quest"
    aliases = ["quests", "questlog"]
    help_text = "quest - Display your active quests"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the quest command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to view quests.", "RED")
            )
            return

        try:
            active_quests = await get_active_quests(ctx.session.character_id)

            if not active_quests:
                await ctx.connection.send_line(colorize("\nYou have no active quests.", "YELLOW"))
                await ctx.connection.send_line(
                    "Speak with NPCs marked with [!] to find quests."
                )
                return

            await ctx.connection.send_line(colorize("\n╔═══ Active Quests ═══╗", "CYAN"))

            for quest in active_quests:
                template = QUEST_TEMPLATES.get(quest.quest_template_id)
                if not template:
                    continue

                # Quest header
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize(f"[{template.title}]", "BOLD")
                )
                await ctx.connection.send_line(
                    colorize(f"Level {template.level_requirement} Quest", "DIM")
                )
                await ctx.connection.send_line("")

                # Objectives
                objective_lines = format_quest_objectives(template, quest.progress)
                for line in objective_lines:
                    # Color completed objectives green, incomplete yellow
                    if "[✓]" in line:
                        await ctx.connection.send_line(colorize(line, "GREEN"))
                    else:
                        await ctx.connection.send_line(colorize(line, "YELLOW"))

                await ctx.connection.send_line("")

            await ctx.connection.send_line(colorize("╚═════════════════════╝", "CYAN"))
            await ctx.connection.send_line(
                f"\nType {colorize('questinfo <quest name>', 'GREEN')} for more details."
            )
            await ctx.connection.send_line(
                f"Type {colorize('abandon <quest name>', 'RED')} to abandon a quest."
            )

        except Exception as e:
            logger.error("questlog_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to display quest log.", "RED")
            )


class QuestInfoCommand(Command):
    """Display detailed information about a quest."""

    name = "questinfo"
    aliases = ["qinfo"]
    help_text = "questinfo <quest name> - Display detailed quest information"
    min_args = 1
    extended_help = """
Shows detailed information about an active quest including:
  - Full description
  - All objectives and progress
  - Rewards (XP, money, items)
  - Level requirement

Examples:
  questinfo welcome
  questinfo rat problem
  qinfo sympathy
    """

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the questinfo command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to view quests.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(
                colorize("Usage: questinfo <quest name>", "YELLOW")
            )
            return

        # Get quest name from args
        quest_name_search = " ".join(ctx.args).lower()

        try:
            active_quests = await get_active_quests(ctx.session.character_id)

            # Find matching quest
            matching_quest = None
            matching_template = None

            for quest in active_quests:
                template = QUEST_TEMPLATES.get(quest.quest_template_id)
                if template and quest_name_search in template.title.lower():
                    matching_quest = quest
                    matching_template = template
                    break

            if not matching_quest or not matching_template:
                await ctx.connection.send_line(
                    colorize(f"No active quest found matching '{quest_name_search}'.", "YELLOW")
                )
                await ctx.connection.send_line(
                    f"Type {colorize('quest', 'GREEN')} to see your active quests."
                )
                return

            # Display detailed quest info
            await ctx.connection.send_line(
                colorize(f"\n╔═══ {matching_template.title} ═══╗", "CYAN")
            )
            await ctx.connection.send_line(
                colorize(f"Level {matching_template.level_requirement} Quest", "DIM")
            )
            await ctx.connection.send_line("")

            # Description
            await ctx.connection.send_line(colorize("Description:", "YELLOW"))
            for line in matching_template.description.split("\n"):
                await ctx.connection.send_line(f"  {line.strip()}")
            await ctx.connection.send_line("")

            # Objectives
            await ctx.connection.send_line(colorize("Objectives:", "YELLOW"))
            objective_lines = format_quest_objectives(matching_template, matching_quest.progress)
            for line in objective_lines:
                if "[✓]" in line:
                    await ctx.connection.send_line(colorize(line, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(line, "YELLOW"))
            await ctx.connection.send_line("")

            # Rewards
            await ctx.connection.send_line(colorize("Rewards:", "YELLOW"))
            if matching_template.rewards.xp > 0:
                await ctx.connection.send_line(
                    f"  {colorize(f'{matching_template.rewards.xp} XP', 'GREEN')}"
                )
            if matching_template.rewards.money > 0:
                await ctx.connection.send_line(
                    f"  {colorize(f'{matching_template.rewards.money} drabs', 'GREEN')}"
                )
            if matching_template.rewards.items:
                for item_id in matching_template.rewards.items:
                    await ctx.connection.send_line(
                        f"  {colorize(f'Item: {item_id}', 'GREEN')}"
                    )

            # Check if completable
            if matching_template.all_objectives_complete(matching_quest.progress):
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("✓ All objectives complete! Return to quest giver.", "GREEN")
                )

            await ctx.connection.send_line(colorize("\n╚═════════════════════════╝", "CYAN"))

        except Exception as e:
            logger.error("questinfo_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to display quest information.", "RED")
            )


class QuestAbandonCommand(Command):
    """Abandon an active quest."""

    name = "abandon"
    aliases = []
    help_text = "abandon <quest name> - Abandon an active quest"
    min_args = 1
    extended_help = """
Abandons an active quest. You can re-accept abandoned quests later
(unless they were one-time quests).

WARNING: Your progress will be lost when you abandon a quest.

Examples:
  abandon welcome
  abandon rat problem
    """

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the abandon command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to abandon quests.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(
                colorize("Usage: abandon <quest name>", "YELLOW")
            )
            return

        # Get quest name from args
        quest_name_search = " ".join(ctx.args).lower()

        try:
            active_quests = await get_active_quests(ctx.session.character_id)

            # Find matching quest
            matching_quest = None
            matching_template = None

            for quest in active_quests:
                template = QUEST_TEMPLATES.get(quest.quest_template_id)
                if template and quest_name_search in template.title.lower():
                    matching_quest = quest
                    matching_template = template
                    break

            if not matching_quest or not matching_template:
                await ctx.connection.send_line(
                    colorize(f"No active quest found matching '{quest_name_search}'.", "YELLOW")
                )
                await ctx.connection.send_line(
                    f"Type {colorize('quest', 'GREEN')} to see your active quests."
                )
                return

            # Confirm abandonment
            success, message = await abandon_quest(ctx.session.character_id, matching_quest)

            if success:
                await ctx.connection.send_line(colorize(f"\n{message}", "YELLOW"))
                await ctx.connection.send_line(
                    "Your progress on this quest has been lost."
                )

                # Check if repeatable
                if matching_template.repeatable:
                    await ctx.connection.send_line(
                        "You can re-accept this quest at any time."
                    )
                else:
                    await ctx.connection.send_line(
                        "You can re-accept this quest, but you'll start from the beginning."
                    )
            else:
                await ctx.connection.send_line(colorize(f"\n{message}", "RED"))

        except Exception as e:
            logger.error("abandon_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to abandon quest.", "RED")
            )
