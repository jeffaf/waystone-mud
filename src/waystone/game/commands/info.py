"""Information commands for Waystone MUD."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.experience import xp_progress
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

                # Show level and XP with progress bar
                current_xp, needed_xp = xp_progress(character)
                xp_percent = (current_xp / needed_xp * 100) if needed_xp > 0 else 0

                # Create XP progress bar (20 chars wide)
                bar_width = 20
                filled = int(bar_width * current_xp / needed_xp) if needed_xp > 0 else 0
                bar = "█" * filled + "░" * (bar_width - filled)

                await ctx.connection.send_line(
                    f"Level: {colorize(str(character.level), 'GREEN')} (XP: {character.experience})"
                )
                await ctx.connection.send_line(
                    f"XP Progress: [{colorize(bar, 'CYAN')}] "
                    f"{current_xp}/{needed_xp} ({xp_percent:.1f}%)"
                )

                # Show attribute points if any
                if character.attribute_points > 0:
                    await ctx.connection.send_line(
                        colorize(
                            f"Attribute Points Available: {character.attribute_points} "
                            f"(use 'increase <attribute>' to spend)",
                            "YELLOW",
                        )
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


class IncreaseCommand(Command):
    """Spend attribute points to increase character attributes."""

    name = "increase"
    aliases = ["inc"]
    help_text = "increase <attribute> - Spend 1 attribute point to increase an attribute"
    min_args = 1

    # Valid attribute names and their shortcuts
    ATTRIBUTES = {
        "strength": "strength",
        "str": "strength",
        "s": "strength",
        "dexterity": "dexterity",
        "dex": "dexterity",
        "d": "dexterity",
        "constitution": "constitution",
        "con": "constitution",
        "c": "constitution",
        "intelligence": "intelligence",
        "int": "intelligence",
        "i": "intelligence",
        "wisdom": "wisdom",
        "wis": "wisdom",
        "w": "wisdom",
        "charisma": "charisma",
        "cha": "charisma",
        "ch": "charisma",
    }

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the increase command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use this command.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: increase <attribute>", "YELLOW"))
            await ctx.connection.send_line(
                "Valid attributes: strength, dexterity, constitution, intelligence, wisdom, charisma"
            )
            await ctx.connection.send_line("Shortcuts: str, dex, con, int, wis, cha")
            return

        # Get attribute name (resolve shortcuts)
        attr_input = ctx.args[0].lower()
        if attr_input not in self.ATTRIBUTES:
            await ctx.connection.send_line(colorize(f"Invalid attribute: {attr_input}", "RED"))
            await ctx.connection.send_line(
                "Valid attributes: strength, dexterity, constitution, intelligence, wisdom, charisma"
            )
            return

        attribute_name = self.ATTRIBUTES[attr_input]

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check if player has attribute points
                if character.attribute_points <= 0:
                    await ctx.connection.send_line(
                        colorize("You don't have any attribute points to spend.", "YELLOW")
                    )
                    await ctx.connection.send_line("You gain attribute points by leveling up.")
                    return

                # Get current attribute value
                old_value = getattr(character, attribute_name)

                # Increase attribute and spend point
                setattr(character, attribute_name, old_value + 1)
                character.attribute_points -= 1

                # Recalculate derived stats if constitution was increased
                if attribute_name == "constitution":
                    # Recalculate max HP
                    con_modifier = (character.constitution - 10) // 2
                    hp_per_level = max(1, 5 + con_modifier)
                    old_max_hp = character.max_hp
                    character.max_hp = 20 + (character.level - 1) * hp_per_level

                    # Increase current HP by the same amount max HP increased
                    hp_increase = character.max_hp - old_max_hp
                    character.current_hp += hp_increase

                await session.commit()

                # Success message
                await ctx.connection.send_line(
                    colorize(
                        f"✨ {attribute_name.capitalize()} increased from {old_value} to {old_value + 1}!",
                        "GREEN",
                    )
                )

                # Show modifier change
                old_modifier = (old_value - 10) // 2
                new_modifier = (old_value + 1 - 10) // 2
                old_mod_str = f"+{old_modifier}" if old_modifier >= 0 else str(old_modifier)
                new_mod_str = f"+{new_modifier}" if new_modifier >= 0 else str(new_modifier)

                await ctx.connection.send_line(
                    f"Modifier: {old_mod_str} → {colorize(new_mod_str, 'CYAN')}"
                )

                # Show special effects
                if attribute_name == "constitution":
                    await ctx.connection.send_line(
                        colorize(
                            f"Max HP increased to {character.max_hp} (+{hp_increase} HP)!", "GREEN"
                        )
                    )

                # Show remaining points
                if character.attribute_points > 0:
                    await ctx.connection.send_line(
                        colorize(
                            f"Attribute points remaining: {character.attribute_points}", "YELLOW"
                        )
                    )
                else:
                    await ctx.connection.send_line(
                        colorize("No attribute points remaining.", "DIM")
                    )

                logger.info(
                    "attribute_increased",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    attribute=attribute_name,
                    old_value=old_value,
                    new_value=old_value + 1,
                    points_remaining=character.attribute_points,
                )

        except Exception as e:
            logger.error("increase_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to increase attribute. Please try again.", "RED")
            )
