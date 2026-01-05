"""Position commands for Waystone MUD - rest, stand, recall."""

from uuid import UUID

import structlog
from sqlalchemy import select, update

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.death import PLAYER_RESPAWN_ROOM
from waystone.game.systems.unified_combat import (
    get_combat_cooldown_remaining,
    get_combat_for_entity,
    is_in_combat_cooldown,
)
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Position constants
POSITION_STANDING = "standing"
POSITION_RESTING = "resting"
POSITION_SLEEPING = "sleeping"


class RestCommand(Command):
    """Rest to heal faster but be vulnerable to attack."""

    name = "rest"
    aliases = []
    help_text = "rest - Sit down and rest to heal faster (2x regeneration)"
    extended_help = """
Rest allows you to heal at double the normal rate, but at a cost:
- You cannot move while resting
- You are more vulnerable to attacks (+2 to hit against you)
- Use 'stand' to stop resting

Type 'rest' to begin resting. Type 'stand' to stop.
"""
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the rest command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to rest.", "RED")
            )
            return

        # Check if in combat
        combat = get_combat_for_entity(ctx.session.character_id)
        if combat:
            await ctx.connection.send_line(colorize("You cannot rest while in combat!", "RED"))
            return

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

                # Check if already resting
                if character.position == POSITION_RESTING:
                    await ctx.connection.send_line(colorize("You are already resting.", "YELLOW"))
                    return

                # Check if sleeping
                if character.position == POSITION_SLEEPING:
                    await ctx.connection.send_line(
                        colorize("You are sleeping. Type 'wake' or 'stand' first.", "YELLOW")
                    )
                    return

                # Set position to resting
                await session.execute(
                    update(Character)
                    .where(Character.id == character.id)
                    .values(position=POSITION_RESTING)
                )
                await session.commit()

                await ctx.connection.send_line(colorize("You sit down and begin resting.", "GREEN"))
                await ctx.connection.send_line(
                    "You will regenerate health twice as fast, but are vulnerable to attack."
                )
                await ctx.connection.send_line("Type 'stand' to stop resting.")

                # Notify room
                current_room = ctx.engine.world.get(character.current_room_id)
                if current_room:
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(f"{character.name} sits down and rests.", "CYAN"),
                        exclude=ctx.session.id,
                    )

                logger.info(
                    "character_resting",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                )

        except Exception as e:
            logger.error("rest_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to rest. Please try again.", "RED"))


class StandCommand(Command):
    """Stand up from resting or sleeping."""

    name = "stand"
    aliases = ["wake"]
    help_text = "stand - Stand up from resting or sleeping"
    extended_help = """
Stand up from a resting or sleeping position. This allows you to move
and fight normally again, but you will no longer receive the bonus
regeneration from resting/sleeping.
"""
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the stand command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to stand.", "RED")
            )
            return

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

                # Check if already standing
                if character.position == POSITION_STANDING:
                    await ctx.connection.send_line(colorize("You are already standing.", "YELLOW"))
                    return

                old_position = character.position

                # Set position to standing
                await session.execute(
                    update(Character)
                    .where(Character.id == character.id)
                    .values(position=POSITION_STANDING)
                )
                await session.commit()

                if old_position == POSITION_SLEEPING:
                    await ctx.connection.send_line(colorize("You wake up and stand.", "GREEN"))
                    room_msg = f"{character.name} wakes up and stands."
                else:
                    await ctx.connection.send_line(colorize("You stand up.", "GREEN"))
                    room_msg = f"{character.name} stands up."

                # Notify room
                current_room = ctx.engine.world.get(character.current_room_id)
                if current_room:
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(room_msg, "CYAN"),
                        exclude=ctx.session.id,
                    )

                logger.info(
                    "character_standing",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    old_position=old_position,
                )

        except Exception as e:
            logger.error("stand_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to stand. Please try again.", "RED"))


class RecallCommand(Command):
    """Teleport back to the respawn point (University Courtyard)."""

    name = "recall"
    aliases = []
    help_text = "recall - Teleport back to the University Courtyard"
    extended_help = """
Recall teleports you instantly back to the University Courtyard, the
safe respawn location. This is useful when you're lost or need to
return to safety quickly.

Restrictions:
- Cannot recall while in combat
- Must wait 30 seconds after combat ends before recalling
- Works from anywhere in the world
"""
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the recall command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to recall.", "RED")
            )
            return

        # Check if in combat
        combat = get_combat_for_entity(ctx.session.character_id)
        if combat:
            await ctx.connection.send_line(colorize("You cannot recall while in combat!", "RED"))
            return

        # Check combat cooldown
        if is_in_combat_cooldown(ctx.session.character_id):
            remaining = get_combat_cooldown_remaining(ctx.session.character_id)
            await ctx.connection.send_line(
                colorize(
                    f"You must wait {remaining} seconds after combat before recalling.",
                    "YELLOW",
                )
            )
            return

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

                old_room_id = character.current_room_id

                # Check if already at recall location
                if old_room_id == PLAYER_RESPAWN_ROOM:
                    await ctx.connection.send_line(
                        colorize("You are already at the University Courtyard.", "YELLOW")
                    )
                    return

                # Get destination room
                destination_room = ctx.engine.world.get(PLAYER_RESPAWN_ROOM)
                if not destination_room:
                    await ctx.connection.send_line(
                        colorize("The recall location doesn't exist!", "RED")
                    )
                    logger.error(
                        "recall_destination_not_found",
                        room_id=PLAYER_RESPAWN_ROOM,
                    )
                    return

                # Remove from old room
                old_room = ctx.engine.world.get(old_room_id)
                if old_room:
                    old_room.remove_player(ctx.session.character_id)

                # Notify old room
                ctx.engine.broadcast_to_room(
                    old_room_id,
                    colorize(f"{character.name} fades away in a shimmer of light.", "CYAN"),
                    exclude=ctx.session.id,
                )

                # Update character location and set to standing
                await session.execute(
                    update(Character)
                    .where(Character.id == character.id)
                    .values(
                        current_room_id=PLAYER_RESPAWN_ROOM,
                        position=POSITION_STANDING,
                    )
                )
                await session.commit()

                # Add to new room
                destination_room.add_player(ctx.session.character_id)

                # Notify new room
                ctx.engine.broadcast_to_room(
                    PLAYER_RESPAWN_ROOM,
                    colorize(f"{character.name} appears in a shimmer of light.", "CYAN"),
                    exclude=ctx.session.id,
                )

                # Show player the recall message and new room
                await ctx.connection.send_line(
                    colorize("\nYou focus your mind and recall home...", "GREEN")
                )
                await ctx.connection.send_line(
                    colorize("The world blurs and you find yourself at the University.\n", "GREEN")
                )
                await ctx.connection.send_line(destination_room.format_description())

                logger.info(
                    "character_recalled",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    from_room=old_room_id,
                    to_room=PLAYER_RESPAWN_ROOM,
                )

        except Exception as e:
            logger.error("recall_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to recall. Please try again.", "RED"))
