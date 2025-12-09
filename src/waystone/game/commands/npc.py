"""NPC interaction commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class ConsiderCommand(Command):
    """
    Compare your character with an NPC to gauge combat difficulty.

    Shows level difference, attribute comparison, and difficulty assessment.
    """

    name = "consider"
    aliases = ["con"]
    help_text = "consider <npc> (con) - Assess an NPC's difficulty level"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the consider command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        npc_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

            # Get NPCs in current room
            room_id = character.current_room_id
            room_npc_ids = ctx.engine.room_npcs.get(room_id, [])

            if not room_npc_ids:
                await ctx.connection.send_line(colorize("There are no NPCs here.", "YELLOW"))
                return

            # Find matching NPC
            matching_npc = None
            for npc_id in room_npc_ids:
                npc_template = ctx.engine.npc_templates.get(npc_id)
                if npc_template and npc_name in npc_template.name.lower():
                    matching_npc = npc_template
                    break

            if not matching_npc:
                await ctx.connection.send_line(
                    colorize(f"You don't see '{npc_name}' here.", "YELLOW")
                )
                return

            # Compare character and NPC
            level_diff = matching_npc.level - character.level

            # Determine difficulty description
            if level_diff <= -5:
                difficulty = colorize("trivial", "DIM")
            elif level_diff <= -3:
                difficulty = colorize("easy", "GREEN")
            elif level_diff <= -1:
                difficulty = colorize("reasonable", "CYAN")
            elif level_diff == 0:
                difficulty = colorize("fair match", "YELLOW")
            elif level_diff <= 2:
                difficulty = colorize("challenging", "YELLOW")
            elif level_diff <= 4:
                difficulty = colorize("dangerous", "ORANGE")
            else:
                difficulty = colorize("suicidal", "RED")

            # Display consideration
            await ctx.connection.send_line("")
            await ctx.connection.send_line(f"You consider {colorize(matching_npc.name, 'CYAN')}...")
            await ctx.connection.send_line("")
            await ctx.connection.send_line(
                f"  Level: {colorize(str(matching_npc.level), 'WHITE')} "
                f"(You: {colorize(str(character.level), 'WHITE')})"
            )
            await ctx.connection.send_line(
                f"  Health: {colorize(str(matching_npc.max_hp), 'WHITE')} HP "
                f"(You: {colorize(str(character.max_hp), 'WHITE')} HP)"
            )

            # Show attribute comparisons if NPC has attributes
            if matching_npc.attributes:
                await ctx.connection.send_line("")
                await ctx.connection.send_line("  Attributes:")
                for attr_name in ["strength", "dexterity", "constitution"]:
                    if attr_name in matching_npc.attributes:
                        npc_val = matching_npc.attributes[attr_name]
                        char_val = getattr(character, attr_name)
                        comparison = (
                            "≈"
                            if abs(npc_val - char_val) <= 2
                            else (">" if npc_val > char_val else "<")
                        )
                        await ctx.connection.send_line(
                            f"    {attr_name.capitalize()}: "
                            f"{colorize(str(npc_val), 'WHITE')} {comparison} "
                            f"{colorize(str(char_val), 'CYAN')}"
                        )

            await ctx.connection.send_line("")
            await ctx.connection.send_line(f"  Assessment: This would be a {difficulty} fight.")

            logger.debug(
                "npc_considered",
                character_id=ctx.session.character_id,
                npc_id=matching_npc.id,
                level_diff=level_diff,
            )

        except Exception as e:
            logger.error("consider_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to consider NPC. Please try again.", "RED")
            )


class ExamineNPCCommand(Command):
    """
    Examine an NPC in detail.

    Shows full description, behavior, and dialogue options if available.
    """

    name = "examine_npc"
    aliases = []
    help_text = "Internal command - use 'examine <npc>' instead"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the examine NPC command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        npc_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

            # Get NPCs in current room
            room_id = character.current_room_id
            room_npc_ids = ctx.engine.room_npcs.get(room_id, [])

            if not room_npc_ids:
                return  # No NPCs, let examine command handle items

            # Find matching NPC
            matching_npc = None
            for npc_id in room_npc_ids:
                npc_template = ctx.engine.npc_templates.get(npc_id)
                if npc_template and npc_name in npc_template.name.lower():
                    matching_npc = npc_template
                    break

            if not matching_npc:
                return  # Not an NPC, let examine command handle items

            # Display NPC examination
            await ctx.connection.send_line("")
            await ctx.connection.send_line(colorize(matching_npc.name.title(), "CYAN"))
            await ctx.connection.send_line("-" * len(matching_npc.name))
            await ctx.connection.send_line(matching_npc.description.strip())
            await ctx.connection.send_line("")

            # Show behavior
            behavior_colors = {
                "aggressive": "RED",
                "passive": "GREEN",
                "merchant": "YELLOW",
                "stationary": "CYAN",
                "wander": "BLUE",
            }
            behavior_color = behavior_colors.get(matching_npc.behavior, "WHITE")
            await ctx.connection.send_line(
                f"Behavior: {colorize(matching_npc.behavior.capitalize(), behavior_color)}"
            )

            # Show level and health for combat assessment
            await ctx.connection.send_line(
                f"Level: {colorize(str(matching_npc.level), 'WHITE')} | "
                f"Health: {colorize(str(matching_npc.max_hp), 'WHITE')} HP"
            )

            # Show dialogue availability
            if matching_npc.dialogue:
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    colorize("This NPC appears willing to talk.", "CYAN")
                )
                if "greeting" in matching_npc.dialogue:
                    await ctx.connection.send_line(f'  "{matching_npc.dialogue["greeting"]}"')

            logger.debug(
                "npc_examined",
                character_id=ctx.session.character_id,
                npc_id=matching_npc.id,
            )

        except Exception as e:
            logger.error("examine_npc_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to examine NPC. Please try again.", "RED")
            )
