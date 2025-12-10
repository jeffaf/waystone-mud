"""Information commands for Waystone MUD."""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.economy import format_money
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

            # Show extended help if available
            if command.extended_help:
                await ctx.connection.send_line("")
                for line in command.extended_help.strip().split("\n"):
                    await ctx.connection.send_line(f"  {line}")

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
            await ctx.connection.send_line("  emotes - List social emotes (laugh, fart, dance, etc.)")

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
    aliases = ["stats", "sc"]
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


class WealthCommand(Command):
    """Display character's current wealth."""

    name = "wealth"
    aliases = ["worth", "money", "gold"]
    help_text = "wealth - Display your current money"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the wealth command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
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

                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("═══ Your Wealth ═══", "YELLOW"))
                await ctx.connection.send_line("")

                # Format money with proper currency breakdown
                money_str = format_money(character.money)
                await ctx.connection.send_line(f"  You have {colorize(money_str, 'GREEN')}.")
                await ctx.connection.send_line("")

                # Show compact format too
                compact_str = format_money(character.money, compact=True)
                await ctx.connection.send_line(f"  ({colorize(compact_str, 'DIM')})")
                await ctx.connection.send_line("")

        except Exception as e:
            logger.error("wealth_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to display wealth.", "RED"))


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


class SaveCommand(Command):
    """Manually save character data to the database."""

    name = "save"
    aliases = []
    help_text = "save - Save your character's current state"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the save command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to save.", "RED")
            )
            return

        try:
            async with get_session() as session:
                # Get character to ensure it exists
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Commit any pending changes to the database
                await session.commit()

                # Success message
                await ctx.connection.send_line(
                    colorize(f"✓ {character.name}'s data has been saved.", "GREEN")
                )

                logger.info(
                    "character_saved",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                )

        except Exception as e:
            logger.error("save_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to save character. Please try again.", "RED")
            )


class GuideCommand(Command):
    """Display the player guide."""

    name = "guide"
    aliases = ["manual", "tutorial"]
    help_text = "guide [topic] - View the player guide"
    min_args = 0
    requires_character = False

    # Guide sections for in-game display
    GUIDE_SECTIONS = {
        "start": """
╔═══ Getting Started ═══╗

1. Register: register <username> <password> <email>
2. Login: login <username> <password>
3. Create character: create <name>
4. Choose background (Soldier, Scholar, Merchant, etc.)
5. Enter world: play <name>

Type 'guide movement' to learn about navigation.
""",
        "movement": """
╔═══ Movement ═══╗

Basic Directions:
  north (n), south (s), east (e), west (w)
  up (u), down (d)
  northeast (ne), northwest (nw)
  southeast (se), southwest (sw)

Commands:
  look (l)     - View your surroundings
  exits        - Show available exits
  go <dir>     - Move in any direction

Type 'guide combat' for combat help.
""",
        "combat": """
╔═══ Combat ═══╗

Commands:
  attack <target>  - Attack an enemy
  defend           - Take defensive stance
  flee             - Attempt to escape
  cs               - View combat status
  consider <npc>   - Check enemy difficulty

Tips:
  - Always 'consider' enemies before fighting
  - Equip weapons with 'equip <item>'
  - Use 'defend' when low on health

Type 'guide sympathy' for magic help.
""",
        "sympathy": """
╔═══ Sympathy Magic ═══╗

Sympathy creates links between objects to transfer energy.

Setup:
  1. hold <heat source>  - Candle, torch, or brazier
  2. bind <type> <source> <target>

Binding Types:
  heat    - Transfer heat
  kinetic - Transfer force
  damage  - Combat damage

Using Bindings:
  heat [amount]         - Transfer heat
  push [force]          - Kinetic push
  cast damage <target>  - Attack

WARNING: Using body heat (hold body) is DANGEROUS!

Type 'guide inventory' for item help.
""",
        "inventory": """
╔═══ Inventory & Equipment ═══╗

Commands:
  inventory (i)      - View your items
  equipment (eq)     - View equipped gear
  get <item>         - Pick up an item
  drop <item>        - Drop an item
  examine <item>     - Look at item details
  equip <item>       - Equip weapon/armor
  unequip <slot>     - Remove equipment

Equipment Slots:
  weapon, off_hand, head, body
  hands, feet, ring, neck

Type 'guide communication' for chat help.
""",
        "communication": """
╔═══ Communication ═══╗

Room Chat:
  say <message>   - Speak to the room
  '<message>      - Shortcut for say
  emote <action>  - Perform an action
  :<action>       - Shortcut for emote

Global/Private:
  chat <message>            - Global channel
  tell <player> <message>   - Private message

Type 'guide tips' for helpful tips.
""",
        "tips": """
╔═══ Tips for New Players ═══╗

1. Save often - Use 'save' command regularly
2. Check difficulty - Always 'consider' before combat
3. Explore - Use 'look' and 'exits' to navigate
4. Read descriptions - Hints are in room text
5. Start small - Fight easy enemies first
6. Learn sympathy - Magic is powerful but risky

Useful Shortcuts:
  ' = say, : = emote, l = look
  i = inventory, eq = equipment
  cs = combatstatus

Type 'guide topics' to see all guide topics.
""",
        "topics": """
╔═══ Guide Topics ═══╗

Available topics:
  guide start        - Getting started
  guide movement     - Navigation
  guide combat       - Fighting
  guide sympathy     - Magic system
  guide inventory    - Items & equipment
  guide communication - Chat commands
  guide fae          - The Fae realm
  guide tips         - Helpful advice

Just type 'guide' for a quick overview.
""",
        "fae": """
╔═══ The Fae Realm ═══╗

The Fae is a shadow realm accessible through ancient greystones.
At twilight, the barrier between worlds grows thin...

Finding the Fae:
  Travel to the Greystones (northeast of Imre north road)
  Type 'enter fae' to step through

The Cthaeh:
  In the Cthaeh's Clearing lives an ancient oracle
  It speaks only truth - but truth can be poison
  Type 'speak cthaeh' to converse (PERMANENT CHOICE!)

The Curse:
  The Cthaeh offers power in exchange for service
  Type 'embrace curse' to accept (CANNOT BE UNDONE)

  Benefits:
    +15% combat damage
    +10% critical chance
    +3 to STR, DEX, CON

  Cost:
    The Cthaeh will assign 'biddings' - targets to kill
    Complete biddings for bonus XP
    Fail and suffer debuffs

Type 'curse' anytime to view your curse status.
WARNING: The Sithe hunt those who speak with the Cthaeh!
""",
    }

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the guide command."""
        if ctx.args:
            topic = ctx.args[0].lower()
            content = self.GUIDE_SECTIONS.get(topic)
            if content:
                await ctx.connection.send_line(colorize(content, "CYAN"))
            else:
                await ctx.connection.send_line(colorize(f"Unknown topic: {topic}", "YELLOW"))
                await ctx.connection.send_line("Type 'guide topics' for available topics.")
        else:
            # Show overview
            overview = """
╔════════════════════════════════════╗
║     WAYSTONE MUD - Player Guide    ║
╚════════════════════════════════════╝

Welcome to the Four Corners!

Quick Commands:
  Movement:  n/s/e/w/u/d, look, exits
  Combat:    attack, defend, flee
  Info:      score, who, help
  Magic:     bind, sympathy, cast

Guide Topics:
  guide start      - Getting started
  guide movement   - Navigation
  guide combat     - Fighting
  guide sympathy   - Magic system
  guide inventory  - Items & equipment
  guide fae        - The Fae realm
  guide tips       - Helpful advice

Type 'guide <topic>' for detailed help.
Type 'help <command>' for command help.
"""
            await ctx.connection.send_line(colorize(overview, "CYAN"))
