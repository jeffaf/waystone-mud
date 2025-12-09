"""Information commands for Waystone MUD."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.network import SessionState, colorize

from .base import Command, CommandContext, get_registry

logger = structlog.get_logger(__name__)


class HelpCommand(Command):
    """Display help information for commands."""

    name = "help"
    aliases = ["?"]
    help_text = "help [command] - Show help for a command or list all commands"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the help command."""
        registry = get_registry()

        # Specific command help
        if len(ctx.args) >= 1:
            command_name = ctx.args[0].lower()
            command = registry.get(command_name)

            if not command:
                await ctx.connection.send_line(colorize(f"Unknown command: {command_name}", "RED"))
                return

            await ctx.connection.send_line(colorize(f"\n{command.name.upper()}", "CYAN"))
            await ctx.connection.send_line(f"  {command.help_text}")

            if command.aliases:
                aliases_str = ", ".join(command.aliases)
                await ctx.connection.send_line(f"  Aliases: {colorize(aliases_str, 'YELLOW')}")

            return

        # General help - show all commands
        await ctx.connection.send_line(colorize("\n╔═══ Available Commands ═══╗", "CYAN"))

        # Determine which commands to show based on state
        if ctx.session.state == SessionState.PLAYING:
            # Show all commands
            await ctx.connection.send_line(colorize("\n Movement:", "YELLOW"))
            await ctx.connection.send_line(
                "  north (n), south (s), east (e), west (w), up (u), down (d)"
            )
            await ctx.connection.send_line("  look (l), exits, go <direction>")

            await ctx.connection.send_line(colorize("\n Communication:", "YELLOW"))
            await ctx.connection.send_line("  say '<message>, emote :<action>")
            await ctx.connection.send_line("  chat <message>, tell <player> <message>")

            await ctx.connection.send_line(colorize("\n Information:", "YELLOW"))
            await ctx.connection.send_line("  score, who, time, help [command]")

            await ctx.connection.send_line(colorize("\n Character:", "YELLOW"))
            await ctx.connection.send_line("  characters, logout")

            await ctx.connection.send_line(colorize("\n System:", "YELLOW"))
            await ctx.connection.send_line("  quit")

        elif ctx.session.state == SessionState.AUTHENTICATING:
            # Show character management commands
            await ctx.connection.send_line(colorize("\n Character Management:", "YELLOW"))
            await ctx.connection.send_line("  characters - List your characters")
            await ctx.connection.send_line("  create <name> - Create a new character")
            await ctx.connection.send_line("  play <name> - Enter the game")
            await ctx.connection.send_line("  delete <name> - Delete a character")

            await ctx.connection.send_line(colorize("\n System:", "YELLOW"))
            await ctx.connection.send_line("  logout - Log out")
            await ctx.connection.send_line("  quit - Disconnect")
            await ctx.connection.send_line("  help [command] - Show help")

        else:
            # Show auth commands
            await ctx.connection.send_line(colorize("\n Authentication:", "YELLOW"))
            await ctx.connection.send_line(
                "  register <username> <password> <email> - Create account"
            )
            await ctx.connection.send_line("  login <username> <password> - Log in")

            await ctx.connection.send_line(colorize("\n System:", "YELLOW"))
            await ctx.connection.send_line("  quit - Disconnect")
            await ctx.connection.send_line("  help [command] - Show help")

        await ctx.connection.send_line(colorize("╚══════════════════════════╝", "CYAN"))
        await ctx.connection.send_line(
            "\nType "
            + colorize("help <command>", "GREEN")
            + " for detailed help on a specific command."
        )


class WhoCommand(Command):
    """List all online players."""

    name = "who"
    aliases = []
    help_text = "who - List all online players"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the who command."""
        sessions = ctx.engine.session_manager.get_all_sessions()
        playing_chars = []

        try:
            async with get_session() as session:
                # Get all characters that are playing
                for sess in sessions:
                    if sess.character_id and sess.state == SessionState.PLAYING:
                        result = await session.execute(
                            select(Character).where(Character.id == UUID(sess.character_id))
                        )
                        character = result.scalar_one_or_none()
                        if character:
                            playing_chars.append(character)

                total_online = len(sessions)
                total_playing = len(playing_chars)

                await ctx.connection.send_line(
                    colorize(f"\n╔═══ Players Online: {total_playing} ═══╗", "CYAN")
                )

                if not playing_chars:
                    await ctx.connection.send_line(
                        colorize("  No players currently in the world.", "YELLOW")
                    )
                else:
                    for char in playing_chars:
                        level_str = colorize(f"Level {char.level}", "GREEN")
                        bg_str = colorize(char.background.value, "YELLOW")
                        await ctx.connection.send_line(
                            f"  {colorize(char.name, 'BOLD')} - {level_str} {bg_str}"
                        )

                await ctx.connection.send_line(colorize("╚═════════════════════════╝", "CYAN"))

                if total_online > total_playing:
                    idle = total_online - total_playing
                    await ctx.connection.send_line(
                        colorize(f"({idle} connection(s) at login screen)", "DIM")
                    )

        except Exception as e:
            logger.error("who_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to retrieve player list.", "RED"))


class ScoreCommand(Command):
    """Display character stats and information."""

    name = "score"
    aliases = ["stats"]
    help_text = "score - Display your character's stats"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the score command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to view stats.", "RED")
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

                # Display character sheet
                await ctx.connection.send_line(colorize(f"\n╔═══ {character.name} ═══╗", "CYAN"))
                await ctx.connection.send_line(
                    f"Background: {colorize(character.background.value, 'YELLOW')}"
                )
                await ctx.connection.send_line(
                    f"Level: {colorize(str(character.level), 'GREEN')} (XP: {character.experience})"
                )

                await ctx.connection.send_line(colorize("\nAttributes:", "YELLOW"))
                attrs = [
                    ("Strength", character.strength),
                    ("Dexterity", character.dexterity),
                    ("Constitution", character.constitution),
                    ("Intelligence", character.intelligence),
                    ("Wisdom", character.wisdom),
                    ("Charisma", character.charisma),
                ]

                for attr_name, attr_value in attrs:
                    # Calculate modifier
                    modifier = (attr_value - 10) // 2
                    mod_str = f"+{modifier}" if modifier >= 0 else str(modifier)
                    await ctx.connection.send_line(
                        f"  {attr_name:13} {colorize(str(attr_value), 'BOLD')} "
                        f"({colorize(mod_str, 'GREEN')})"
                    )

                # Get room name
                room = ctx.engine.world.get(character.current_room_id)
                room_name = room.name if room else "Unknown"

                await ctx.connection.send_line(colorize("\nLocation:", "YELLOW"))
                await ctx.connection.send_line(f"  {room_name}")

                await ctx.connection.send_line(colorize("╚═════════════════════════╝", "CYAN"))

        except Exception as e:
            logger.error("score_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to display character stats.", "RED"))


class TimeCommand(Command):
    """Display current server time and game time."""

    name = "time"
    aliases = []
    help_text = "time - Display current time"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the time command."""
        now = datetime.now(UTC)

        await ctx.connection.send_line(colorize("\n╔═══ Current Time ═══╗", "CYAN"))
        await ctx.connection.send_line(
            f"Server Time: {colorize(now.strftime('%Y-%m-%d %H:%M:%S UTC'), 'YELLOW')}"
        )

        # Calculate game time (could be customized)
        # For now, just use server time
        await ctx.connection.send_line(
            f"Game Time:   {colorize(now.strftime('%Y-%m-%d %H:%M:%S'), 'YELLOW')}"
        )

        await ctx.connection.send_line(colorize("╚════════════════════╝", "CYAN"))
