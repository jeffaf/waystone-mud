"""Character management commands for Waystone MUD."""

import re
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.config import get_settings
from waystone.database.engine import get_session
from waystone.database.models import Character, CharacterBackground, User
from waystone.network import SessionState, colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Character name validation
CHARACTER_NAME_PATTERN = re.compile(r"^[A-Z][a-zA-Z]{1,29}$")


class CharactersCommand(Command):
    """List all characters belonging to the logged-in user."""

    name = "characters"
    aliases = ["chars"]
    help_text = "characters - List your characters"
    min_args = 0
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the characters command."""
        if not ctx.session.user_id:
            await ctx.connection.send_line(
                colorize("You must be logged in to use this command.", "RED")
            )
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character)
                    .where(Character.user_id == UUID(ctx.session.user_id))
                    .order_by(Character.created_at)
                )
                characters = result.scalars().all()

                if not characters:
                    await ctx.connection.send_line(
                        colorize("\nYou don't have any characters yet.", "YELLOW")
                    )
                    await ctx.connection.send_line(
                        "Create one with: " +
                        colorize("create <name>", "CYAN")
                    )
                    return

                await ctx.connection.send_line(
                    colorize("\n╔═══ Your Characters ═══╗", "CYAN")
                )
                for char in characters:
                    level_str = colorize(f"Level {char.level}", "GREEN")
                    bg_str = colorize(char.background.value, "YELLOW")
                    await ctx.connection.send_line(
                        f"  {colorize(char.name, 'BOLD')} - {level_str} {bg_str}"
                    )
                await ctx.connection.send_line(
                    colorize("╚═══════════════════════╝", "CYAN")
                )
                await ctx.connection.send_line(
                    "\nTo play a character, type: " +
                    colorize("play <name>", "CYAN")
                )

        except Exception as e:
            logger.error("characters_list_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to list characters.", "RED")
            )


class CreateCommand(Command):
    """Create a new character with guided character creation flow."""

    name = "create"
    aliases = []
    help_text = "create <name> - Create a new character"
    min_args = 1
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the create command."""
        if not ctx.session.user_id:
            await ctx.connection.send_line(
                colorize("You must be logged in to create a character.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(
                colorize("Usage: create <name>", "YELLOW")
            )
            return

        name = ctx.args[0]

        # Validate character name
        if not CHARACTER_NAME_PATTERN.match(name):
            await ctx.connection.send_line(
                colorize(
                    "Invalid character name. Must be 2-30 letters, starting with a capital letter.",
                    "RED"
                )
            )
            return

        try:
            async with get_session() as session:
                # Check if name is taken
                result = await session.execute(
                    select(Character).where(Character.name == name)
                )
                if result.scalar_one_or_none():
                    await ctx.connection.send_line(
                        colorize(f"The name '{name}' is already taken.", "RED")
                    )
                    return

                # Character creation flow
                await ctx.connection.send_line(
                    colorize(f"\n╔═══ Creating Character: {name} ═══╗", "CYAN")
                )

                # Choose background
                await ctx.connection.send_line(
                    colorize("\nChoose a background:", "YELLOW")
                )
                for i, bg in enumerate(CharacterBackground, 1):
                    await ctx.connection.send_line(
                        f"  {i}. {colorize(bg.value, 'CYAN')}"
                    )

                await ctx.connection.send_line(
                    colorize("\nEnter the number of your choice: ", "GREEN")
                )
                choice = await ctx.connection.readline()

                try:
                    bg_index = int(choice) - 1
                    backgrounds = list(CharacterBackground)
                    if bg_index < 0 or bg_index >= len(backgrounds):
                        await ctx.connection.send_line(
                            colorize("Invalid choice. Character creation cancelled.", "RED")
                        )
                        return
                    background = backgrounds[bg_index]
                except (ValueError, IndexError):
                    await ctx.connection.send_line(
                        colorize("Invalid choice. Character creation cancelled.", "RED")
                    )
                    return

                # Attribute allocation
                await ctx.connection.send_line(
                    colorize(
                        f"\n{name} the {background.value} begins with base attributes of 10.",
                        "CYAN"
                    )
                )
                await ctx.connection.send_line(
                    colorize("You have 5 bonus points to allocate.", "YELLOW")
                )

                attributes = {
                    "strength": 10,
                    "dexterity": 10,
                    "constitution": 10,
                    "intelligence": 10,
                    "wisdom": 10,
                    "charisma": 10,
                }

                points_remaining = 5
                while points_remaining > 0:
                    await ctx.connection.send_line(
                        colorize(
                            f"\nPoints remaining: {points_remaining}",
                            "GREEN"
                        )
                    )
                    await ctx.connection.send_line("Current attributes:")
                    for attr, value in attributes.items():
                        await ctx.connection.send_line(f"  {attr.capitalize()}: {value}")

                    await ctx.connection.send_line(
                        colorize(
                            "\nEnter attribute name to increase (or 'done' to finish): ",
                            "YELLOW"
                        )
                    )
                    attr_choice = (await ctx.connection.readline()).lower()

                    if attr_choice == "done":
                        break

                    if attr_choice not in attributes:
                        await ctx.connection.send_line(
                            colorize("Invalid attribute name.", "RED")
                        )
                        continue

                    attributes[attr_choice] += 1
                    points_remaining -= 1

                # Confirmation
                await ctx.connection.send_line(
                    colorize(f"\n╔═══ Character Summary ═══╗", "CYAN")
                )
                await ctx.connection.send_line(f"Name: {colorize(name, 'BOLD')}")
                await ctx.connection.send_line(
                    f"Background: {colorize(background.value, 'YELLOW')}"
                )
                await ctx.connection.send_line("\nAttributes:")
                for attr, value in attributes.items():
                    await ctx.connection.send_line(f"  {attr.capitalize()}: {value}")
                await ctx.connection.send_line(
                    colorize("╚═════════════════════════╝", "CYAN")
                )

                await ctx.connection.send_line(
                    colorize("\nConfirm creation? (yes/no): ", "GREEN")
                )
                confirm = (await ctx.connection.readline()).lower()

                if confirm not in ["yes", "y"]:
                    await ctx.connection.send_line(
                        colorize("Character creation cancelled.", "YELLOW")
                    )
                    return

                # Create character in database
                settings = get_settings()
                new_character = Character(
                    user_id=UUID(ctx.session.user_id),
                    name=name,
                    background=background,
                    current_room_id=settings.starting_room_id,
                    **attributes,
                )
                session.add(new_character)
                await session.commit()

                await ctx.connection.send_line(
                    colorize(
                        f"\n✨ {name} has been created! ✨",
                        "GREEN"
                    )
                )
                await ctx.connection.send_line(
                    "To start playing, type: " +
                    colorize(f"play {name}", "CYAN")
                )

                logger.info(
                    "character_created",
                    character_name=name,
                    character_id=str(new_character.id),
                    user_id=ctx.session.user_id,
                )

        except Exception as e:
            logger.error("character_creation_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Character creation failed. Please try again.", "RED")
            )


class PlayCommand(Command):
    """Enter the game world with a character."""

    name = "play"
    aliases = []
    help_text = "play <name> - Enter the game with a character"
    min_args = 1
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the play command."""
        if not ctx.session.user_id:
            await ctx.connection.send_line(
                colorize("You must be logged in to play.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(
                colorize("Usage: play <name>", "YELLOW")
            )
            return

        name = ctx.args[0]

        try:
            async with get_session() as session:
                # Find character by name and user
                result = await session.execute(
                    select(Character)
                    .where(
                        Character.name == name,
                        Character.user_id == UUID(ctx.session.user_id)
                    )
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(
                        colorize(f"You don't have a character named '{name}'.", "RED")
                    )
                    return

                # Check if character is already in use
                char_id_str = str(character.id)
                if char_id_str in ctx.engine.character_to_session:
                    existing_session = ctx.engine.character_to_session[char_id_str]
                    if existing_session.id != ctx.session.id:
                        await ctx.connection.send_line(
                            colorize(
                                f"{name} is already being played in another session.",
                                "RED"
                            )
                        )
                        return

                # Set character in session
                ctx.session.set_character(char_id_str)
                ctx.session.set_state(SessionState.PLAYING)
                ctx.engine.character_to_session[char_id_str] = ctx.session

                # Add character to room
                room = ctx.engine.world.get(character.current_room_id)
                if room:
                    room.add_player(char_id_str)

                    # Notify room
                    ctx.engine.broadcast_to_room(
                        character.current_room_id,
                        colorize(f"{name} has entered the world.", "CYAN"),
                        exclude=ctx.session.id
                    )

                await ctx.connection.send_line(
                    colorize(f"\n✨ Welcome to the world, {name}! ✨\n", "GREEN")
                )

                # Show current room
                if room:
                    await ctx.connection.send_line(room.format_description())

                logger.info(
                    "character_entered_world",
                    character_name=name,
                    character_id=char_id_str,
                    room_id=character.current_room_id,
                )

        except Exception as e:
            logger.error("play_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to enter the world. Please try again.", "RED")
            )


class DeleteCommand(Command):
    """Delete a character (with confirmation)."""

    name = "delete"
    aliases = []
    help_text = "delete <name> - Delete a character (permanent!)"
    min_args = 1
    requires_character = False

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the delete command."""
        if not ctx.session.user_id:
            await ctx.connection.send_line(
                colorize("You must be logged in to delete a character.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(
                colorize("Usage: delete <name>", "YELLOW")
            )
            return

        name = ctx.args[0]

        try:
            async with get_session() as session:
                # Find character by name and user
                result = await session.execute(
                    select(Character)
                    .where(
                        Character.name == name,
                        Character.user_id == UUID(ctx.session.user_id)
                    )
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(
                        colorize(f"You don't have a character named '{name}'.", "RED")
                    )
                    return

                # Confirmation
                await ctx.connection.send_line(
                    colorize(
                        f"\n⚠️  WARNING: This will permanently delete {name}!",
                        "RED"
                    )
                )
                await ctx.connection.send_line(
                    colorize(
                        f"Type '{name}' exactly to confirm deletion: ",
                        "YELLOW"
                    )
                )
                confirm = await ctx.connection.readline()

                if confirm != name:
                    await ctx.connection.send_line(
                        colorize("Deletion cancelled.", "GREEN")
                    )
                    return

                # Delete character
                char_id_str = str(character.id)
                await session.delete(character)
                await session.commit()

                # Clean up from engine if active
                if char_id_str in ctx.engine.character_to_session:
                    del ctx.engine.character_to_session[char_id_str]

                await ctx.connection.send_line(
                    colorize(f"\n{name} has been deleted.", "YELLOW")
                )

                logger.info(
                    "character_deleted",
                    character_name=name,
                    character_id=char_id_str,
                    user_id=ctx.session.user_id,
                )

        except Exception as e:
            logger.error("character_deletion_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to delete character. Please try again.", "RED")
            )
