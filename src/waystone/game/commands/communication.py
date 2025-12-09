"""Communication commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class SayCommand(Command):
    """Speak to everyone in the current room."""

    name = "say"
    aliases = ["'"]
    help_text = "say <message> or '<message> - Speak to the room"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the say command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to speak.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Say what?", "YELLOW"))
            return

        message = " ".join(ctx.args)

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

                # Send to self
                await ctx.connection.send_line(colorize(f'You say, "{message}"', "YELLOW"))

                # Broadcast to room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f'{character.name} says, "{message}"', "YELLOW"),
                    exclude=ctx.session.id,
                )

                logger.debug(
                    "say_command",
                    character_name=character.name,
                    room_id=character.current_room_id,
                    message=message,
                )

        except Exception as e:
            logger.error("say_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to speak. Please try again.", "RED"))


class EmoteCommand(Command):
    """Perform a roleplay action."""

    name = "emote"
    aliases = [":"]
    help_text = "emote <action> or :<action> - Perform a roleplay action"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the emote command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to emote.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Emote what?", "YELLOW"))
            return

        action = " ".join(ctx.args)

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

                # Format emote message
                emote_msg = colorize(f"{character.name} {action}", "MAGENTA")

                # Send to self
                await ctx.connection.send_line(emote_msg)

                # Broadcast to room
                ctx.engine.broadcast_to_room(
                    character.current_room_id, emote_msg, exclude=ctx.session.id
                )

                logger.debug(
                    "emote_command",
                    character_name=character.name,
                    room_id=character.current_room_id,
                    action=action,
                )

        except Exception as e:
            logger.error("emote_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to emote. Please try again.", "RED"))


class ChatCommand(Command):
    """Send a message to the global OOC (out-of-character) channel."""

    name = "chat"
    aliases = ["ooc"]
    help_text = "chat <message> - Send a global OOC message"
    min_args = 1
    requires_character = False  # Can chat without a character

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the chat command."""
        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Chat what?", "YELLOW"))
            return

        message = " ".join(ctx.args)

        # Get sender name
        sender_name = "Anonymous"
        if ctx.session.character_id:
            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(Character).where(Character.id == UUID(ctx.session.character_id))
                    )
                    character = result.scalar_one_or_none()
                    if character:
                        sender_name = character.name
            except Exception as e:
                logger.error("chat_character_lookup_failed", error=str(e))
        elif ctx.session.user_id:
            try:
                async with get_session() as session:
                    from waystone.database.models import User

                    user_result = await session.execute(
                        select(User).where(User.id == UUID(ctx.session.user_id))
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        sender_name = user.username
            except Exception as e:
                logger.error("chat_user_lookup_failed", error=str(e))

        # Format message
        chat_msg = (
            colorize("[CHAT] ", "CYAN")
            + colorize(sender_name, "BOLD")
            + colorize(": ", "CYAN")
            + message
        )

        # Send to self
        await ctx.connection.send_line(chat_msg)

        # Broadcast to all sessions
        for player_session in ctx.engine.session_manager.get_all_sessions():
            if player_session.id != ctx.session.id and player_session.connection:
                try:
                    await player_session.connection.send_line(chat_msg)
                except Exception as e:
                    logger.error(
                        "chat_broadcast_failed",
                        target_session=str(player_session.id),
                        error=str(e),
                    )

        logger.debug(
            "chat_command",
            sender=sender_name,
            message=message,
        )


class TellCommand(Command):
    """Send a private message to another player."""

    name = "tell"
    aliases = ["whisper", "t"]
    help_text = "tell <player> <message> - Send a private message"
    min_args = 2

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the tell command."""
        if len(ctx.args) < 2:
            await ctx.connection.send_line(colorize("Usage: tell <player> <message>", "YELLOW"))
            return

        target_name = ctx.args[0]
        message = " ".join(ctx.args[1:])

        # Get sender name
        sender_name = "Someone"
        if ctx.session.character_id:
            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(Character).where(Character.id == UUID(ctx.session.character_id))
                    )
                    character = result.scalar_one_or_none()
                    if character:
                        sender_name = character.name
            except Exception as e:
                logger.error("tell_sender_lookup_failed", error=str(e))

        # Find target character
        try:
            async with get_session() as db_session:
                result = await db_session.execute(
                    select(Character).where(Character.name == target_name)
                )
                target_char = result.scalar_one_or_none()

                if not target_char:
                    await ctx.connection.send_line(
                        colorize(f"No player named '{target_name}' found.", "RED")
                    )
                    return

                # Find target session
                target_session = ctx.engine.character_to_session.get(str(target_char.id))

                if not target_session:
                    await ctx.connection.send_line(
                        colorize(f"{target_name} is not currently online.", "YELLOW")
                    )
                    return

                # Send to target
                await target_session.connection.send_line(
                    colorize(f"{sender_name} tells you, ", "MAGENTA")
                    + colorize(f'"{message}"', "WHITE")
                )

                # Confirm to sender
                await ctx.connection.send_line(
                    colorize(f"You tell {target_name}, ", "MAGENTA")
                    + colorize(f'"{message}"', "WHITE")
                )

                logger.debug(
                    "tell_command",
                    sender=sender_name,
                    target=target_name,
                    message=message,
                )

        except Exception as e:
            logger.error("tell_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to send message. Please try again.", "RED")
            )
