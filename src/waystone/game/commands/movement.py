"""Movement commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.experience import XP_EXPLORATION_NEW_ROOM, award_xp
from waystone.game.systems.npc_display import (
    format_npcs_for_room,
)
from waystone.game.systems.university import can_access_room, get_university_status, rank_to_display
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Direction shortcuts
DIRECTION_SHORTCUTS = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "u": "up",
    "d": "down",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
}


class MoveCommand(Command):
    """Base class for directional movement commands."""

    direction: str = ""

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the movement command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to move.", "RED")
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

                # Check if resting or sleeping
                position = getattr(character, "position", "standing")
                if position == "resting":
                    await ctx.connection.send_line(
                        colorize("You can't move while resting. Type 'stand' first.", "YELLOW")
                    )
                    return
                if position == "sleeping":
                    await ctx.connection.send_line(
                        colorize(
                            "You can't move while sleeping. Type 'wake' or 'stand' first.", "YELLOW"
                        )
                    )
                    return

                # Get current room
                current_room = ctx.engine.world.get(character.current_room_id)
                if not current_room:
                    await ctx.connection.send_line(
                        colorize("Your current location doesn't exist!", "RED")
                    )
                    logger.error(
                        "character_in_nonexistent_room",
                        character_id=ctx.session.character_id,
                        room_id=character.current_room_id,
                    )
                    return

                # Check if exit exists
                destination_id = current_room.get_exit(self.direction)
                if not destination_id:
                    await ctx.connection.send_line(
                        colorize(f"You can't go {self.direction} from here.", "YELLOW")
                    )
                    return

                # Get destination room
                destination_room = ctx.engine.world.get(destination_id)
                if not destination_room:
                    await ctx.connection.send_line(colorize("That exit leads nowhere!", "RED"))
                    logger.error(
                        "exit_to_nonexistent_room",
                        from_room=character.current_room_id,
                        to_room=destination_id,
                        direction=self.direction,
                    )
                    return

                # Check for rank-restricted access
                requires_rank = destination_room.properties.get("requires_rank")
                if requires_rank and isinstance(requires_rank, str):
                    status = get_university_status(character.id)
                    if not can_access_room(status.arcanum_rank, requires_rank):
                        from waystone.game.systems.university import rank_from_string

                        required = rank_from_string(requires_rank)
                        await ctx.connection.send_line(
                            colorize(
                                f"Access denied. This area requires {rank_to_display(required)} rank.",
                                "RED",
                            )
                        )
                        await ctx.connection.send_line(
                            "Only members of the Arcanum with sufficient rank may enter."
                        )
                        return

                # Remove from old room
                current_room.remove_player(ctx.session.character_id)

                # Notify old room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f"{character.name} leaves {self.direction}.", "CYAN"),
                    exclude=ctx.session.id,
                )

                # Check if this is a new room for exploration XP
                visited_rooms = character.visited_rooms or []
                is_new_room = destination_id not in visited_rooms

                # Update character location
                character.current_room_id = destination_id

                # Track visited room
                if is_new_room:
                    visited_rooms.append(destination_id)
                    character.visited_rooms = visited_rooms
                    # Flag JSON column as modified so SQLAlchemy tracks the change
                    flag_modified(character, "visited_rooms")

                await session.commit()

                # Award exploration XP for new rooms
                if is_new_room:
                    xp_awarded, leveled_up = await award_xp(
                        character.id,
                        XP_EXPLORATION_NEW_ROOM,
                        "exploration_new_room",
                        session=session,
                    )

                    await ctx.connection.send_line(
                        colorize(
                            f"✨ You discovered a new location! +{XP_EXPLORATION_NEW_ROOM} XP",
                            "YELLOW",
                        )
                    )

                    if leveled_up:
                        await ctx.connection.send_line(
                            colorize(
                                f"🎉 Congratulations! You've reached level {character.level}!",
                                "GREEN",
                            )
                        )

                # Add to new room
                destination_room.add_player(ctx.session.character_id)

                # Notify new room
                ctx.engine.broadcast_to_room(
                    destination_id,
                    colorize(f"{character.name} arrives.", "CYAN"),
                    exclude=ctx.session.id,
                )

                # Show new room to player
                await ctx.connection.send_line(
                    colorize(f"\nYou travel {self.direction}.\n", "GREEN")
                )
                await ctx.connection.send_line(destination_room.format_description())

                # Show NPCs in room with numbered targeting
                from waystone.game.systems.npc_combat import get_npcs_in_room

                npcs = get_npcs_in_room(destination_id)
                if npcs:
                    await ctx.connection.send_line("")
                    for text, color in format_npcs_for_room(npcs):
                        await ctx.connection.send_line(colorize(text, color))

                # Show corpses in room
                from waystone.game.systems.corpse import format_corpse_for_room, get_corpses_in_room

                corpses = get_corpses_in_room(destination_id)
                if corpses:
                    await ctx.connection.send_line("")
                    for corpse in corpses:
                        await ctx.connection.send_line(
                            colorize(format_corpse_for_room(corpse), "MAGENTA")
                        )

                # Show other players in room
                other_players = [
                    pid for pid in destination_room.players if pid != ctx.session.character_id
                ]
                if other_players:
                    await ctx.connection.send_line("")
                    other_result = await session.execute(
                        select(Character).where(
                            Character.id.in_([UUID(pid) for pid in other_players])
                        )
                    )
                    other_chars = other_result.scalars().all()
                    for char in other_chars:
                        await ctx.connection.send_line(colorize(f"{char.name} is here.", "CYAN"))

                logger.info(
                    "character_moved",
                    character_name=character.name,
                    character_id=ctx.session.character_id,
                    from_room=current_room.id,
                    to_room=destination_id,
                    direction=self.direction,
                )

        except Exception as e:
            logger.error("movement_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Movement failed. Please try again.", "RED"))


class NorthCommand(MoveCommand):
    """Move north."""

    name = "north"
    aliases = ["n"]
    help_text = "north (n) - Move north"
    direction = "north"


class SouthCommand(MoveCommand):
    """Move south."""

    name = "south"
    aliases = ["s"]
    help_text = "south (s) - Move south"
    direction = "south"


class EastCommand(MoveCommand):
    """Move east."""

    name = "east"
    aliases = ["e"]
    help_text = "east (e) - Move east"
    direction = "east"


class WestCommand(MoveCommand):
    """Move west."""

    name = "west"
    aliases = ["w"]
    help_text = "west (w) - Move west"
    direction = "west"


class UpCommand(MoveCommand):
    """Move up."""

    name = "up"
    aliases = ["u"]
    help_text = "up (u) - Move up"
    direction = "up"


class DownCommand(MoveCommand):
    """Move down."""

    name = "down"
    aliases = ["d"]
    help_text = "down (d) - Move down"
    direction = "down"


class NortheastCommand(MoveCommand):
    """Move northeast."""

    name = "northeast"
    aliases = ["ne"]
    help_text = "northeast (ne) - Move northeast"
    direction = "northeast"


class NorthwestCommand(MoveCommand):
    """Move northwest."""

    name = "northwest"
    aliases = ["nw"]
    help_text = "northwest (nw) - Move northwest"
    direction = "northwest"


class SoutheastCommand(MoveCommand):
    """Move southeast."""

    name = "southeast"
    aliases = ["se"]
    help_text = "southeast (se) - Move southeast"
    direction = "southeast"


class SouthwestCommand(MoveCommand):
    """Move southwest."""

    name = "southwest"
    aliases = ["sw"]
    help_text = "southwest (sw) - Move southwest"
    direction = "southwest"


class OutCommand(MoveCommand):
    """Move out."""

    name = "out"
    aliases = ["o", "leave"]
    help_text = "out (o) - Move out/exit"
    direction = "out"


class InCommand(MoveCommand):
    """Move in/enter."""

    name = "in"
    aliases = ["enter"]
    help_text = "in - Move in/enter"
    direction = "in"


class GoCommand(Command):
    """Alternative movement syntax using 'go <direction>'."""

    name = "go"
    aliases = []
    help_text = "go <direction> - Move in a direction"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the go command."""
        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: go <direction>", "YELLOW"))
            return

        # Normalize direction
        direction = ctx.args[0].lower()
        direction = DIRECTION_SHORTCUTS.get(direction, direction)

        # Create appropriate movement command
        move_commands = {
            "north": NorthCommand(),
            "south": SouthCommand(),
            "east": EastCommand(),
            "west": WestCommand(),
            "up": UpCommand(),
            "down": DownCommand(),
            "northeast": NortheastCommand(),
            "northwest": NorthwestCommand(),
            "southeast": SoutheastCommand(),
            "southwest": SouthwestCommand(),
            "out": OutCommand(),
            "in": InCommand(),
        }

        move_cmd = move_commands.get(direction)
        if not move_cmd:
            await ctx.connection.send_line(colorize(f"Unknown direction: {direction}", "RED"))
            return

        await move_cmd.execute(ctx)


class LookCommand(Command):
    """View current room description."""

    name = "look"
    aliases = ["l"]
    help_text = "look (l) - View current room description"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the look command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to look around.", "RED")
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

                # Get current room
                room = ctx.engine.world.get(character.current_room_id)
                if not room:
                    await ctx.connection.send_line(
                        colorize("Your current location doesn't exist!", "RED")
                    )
                    return

                # Show room description
                await ctx.connection.send_line(room.format_description())

                # Show NPCs in room with numbered targeting
                from waystone.game.systems.npc_combat import get_npcs_in_room

                npcs = get_npcs_in_room(character.current_room_id)
                if npcs:
                    await ctx.connection.send_line("")
                    # Display each NPC with a number for targeting
                    for text, color in format_npcs_for_room(npcs):
                        await ctx.connection.send_line(colorize(text, color))

                # Show corpses in room
                from waystone.game.systems.corpse import format_corpse_for_room, get_corpses_in_room

                corpses = get_corpses_in_room(character.current_room_id)
                if corpses:
                    await ctx.connection.send_line("")
                    for corpse in corpses:
                        await ctx.connection.send_line(
                            colorize(format_corpse_for_room(corpse), "MAGENTA")
                        )

                # Show other players in room
                other_players = [pid for pid in room.players if pid != ctx.session.character_id]

                if other_players:
                    await ctx.connection.send_line("")
                    # Get character names
                    result = await session.execute(
                        select(Character).where(
                            Character.id.in_([UUID(pid) for pid in other_players])
                        )
                    )
                    characters = result.scalars().all()

                    for char in characters:
                        await ctx.connection.send_line(colorize(f"{char.name} is here.", "CYAN"))

        except Exception as e:
            logger.error("look_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to look around. Please try again.", "RED")
            )


class ExitsCommand(Command):
    """Show available exits from current room."""

    name = "exits"
    aliases = []
    help_text = "exits - Show available exits"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the exits command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to check exits.", "RED")
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

                # Get current room
                room = ctx.engine.world.get(character.current_room_id)
                if not room:
                    await ctx.connection.send_line(
                        colorize("Your current location doesn't exist!", "RED")
                    )
                    return

                # Show exits
                if not room.exits:
                    await ctx.connection.send_line(
                        colorize("There are no obvious exits.", "YELLOW")
                    )
                    return

                await ctx.connection.send_line(colorize("\nObvious exits:", "CYAN"))
                for direction, dest_id in sorted(room.exits.items()):
                    dest_room = ctx.engine.world.get(dest_id)
                    if dest_room:
                        await ctx.connection.send_line(
                            f"  {colorize(direction.capitalize(), 'GREEN')} - {dest_room.name}"
                        )
                    else:
                        await ctx.connection.send_line(
                            f"  {colorize(direction.capitalize(), 'GREEN')}"
                        )

        except Exception as e:
            logger.error("exits_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to list exits. Please try again.", "RED")
            )
