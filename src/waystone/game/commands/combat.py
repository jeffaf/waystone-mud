"""Combat commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.combat import Combat, CombatState
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)

# Global combat instances per room
_active_combats: dict[str, Combat] = {}


def get_combat_for_room(room_id: str) -> Combat | None:
    """
    Get active combat instance for a room.

    Args:
        room_id: The room ID

    Returns:
        Combat instance or None if no active combat
    """
    combat = _active_combats.get(room_id)
    if combat and combat.state != CombatState.ENDED:
        return combat
    return None


def get_combat_for_character(character_id: str) -> Combat | None:
    """
    Get the combat instance a character is participating in.

    Args:
        character_id: The character's UUID string

    Returns:
        Combat instance or None
    """
    for combat in _active_combats.values():
        if combat.state != CombatState.ENDED and combat.is_character_in_combat(character_id):
            return combat
    return None


async def create_combat(room_id: str, ctx: CommandContext) -> Combat:
    """
    Create a new combat instance for a room.

    Args:
        room_id: The room ID
        ctx: Command context

    Returns:
        New combat instance
    """
    combat = Combat(room_id, ctx.engine)
    _active_combats[room_id] = combat
    return combat


class AttackCommand(Command):
    """Initiate combat or attack a target in combat."""

    name = "attack"
    aliases = ["att", "a"]
    help_text = "attack <target> - Attack a target (initiates combat)"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the attack command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to attack.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: attack <target>", "YELLOW"))
            return

        target_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get attacker
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                attacker = result.scalar_one_or_none()

                if not attacker:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check if attacker is dead
                if attacker.current_hp <= 0:
                    await ctx.connection.send_line(
                        colorize("You are defeated and cannot attack!", "RED")
                    )
                    return

                # Get current room
                room = ctx.engine.world.get(attacker.current_room_id)
                if not room:
                    await ctx.connection.send_line(
                        colorize("Your current location doesn't exist!", "RED")
                    )
                    return

                # Find target in room
                target = None
                for character_id in room.players:
                    if character_id == ctx.session.character_id:
                        continue

                    result = await session.execute(
                        select(Character).where(Character.id == UUID(character_id))
                    )
                    potential_target = result.scalar_one_or_none()

                    if potential_target and potential_target.name.lower() == target_name:
                        target = potential_target
                        break

                if not target:
                    await ctx.connection.send_line(
                        colorize(f"You don't see '{target_name}' here.", "RED")
                    )
                    return

                # Check if target is dead
                if target.current_hp <= 0:
                    await ctx.connection.send_line(
                        colorize(f"{target.name} is already defeated!", "RED")
                    )
                    return

                # Check for existing combat
                combat = get_combat_for_room(attacker.current_room_id)

                if not combat:
                    # Create new combat
                    combat = await create_combat(attacker.current_room_id, ctx)

                    # Add both participants
                    await combat.add_participant(ctx.session.character_id)
                    await combat.add_participant(str(target.id))

                    # Start combat
                    combat.start_combat()

                    # Announce combat start
                    start_msg = colorize(
                        f"\n{attacker.name} attacks {target.name}! Combat begins!",
                        "RED",
                    )
                    ctx.engine.broadcast_to_room(attacker.current_room_id, start_msg)

                    # Show initiative order
                    ctx.engine.broadcast_to_room(
                        attacker.current_room_id,
                        combat.get_combat_status(),
                    )

                    # Start first turn
                    await combat.start_turn_timer()
                    current = combat.get_current_participant()
                    if current:
                        turn_msg = colorize(
                            f"\n=== {current.character_name}'s turn ===",
                            "CYAN",
                        )
                        ctx.engine.broadcast_to_room(
                            attacker.current_room_id,
                            turn_msg,
                        )

                else:
                    # Existing combat - try to attack
                    # Add target if not in combat
                    if not combat.is_character_in_combat(str(target.id)):
                        await combat.add_participant(str(target.id))

                    # Perform attack
                    success, message = await combat.perform_attack(
                        ctx.session.character_id,
                        str(target.id),
                    )

                    await ctx.connection.send_line(colorize(message, "GREEN" if success else "RED"))

        except Exception as e:
            logger.error("attack_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Attack failed. Please try again.", "RED"))


class DefendCommand(Command):
    """Take a defensive stance in combat."""

    name = "defend"
    aliases = ["def"]
    help_text = "defend - Take defensive stance (+5 Defense, skip attack)"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the defend command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to defend.", "RED")
            )
            return

        try:
            # Check if in combat
            combat = get_combat_for_character(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(colorize("You are not in combat!", "RED"))
                return

            # Perform defend action
            success, message = await combat.perform_defend(ctx.session.character_id)

            await ctx.connection.send_line(colorize(message, "GREEN" if success else "RED"))

        except Exception as e:
            logger.error("defend_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Defend action failed. Please try again.", "RED")
            )


class FleeCommand(Command):
    """Attempt to flee from combat."""

    name = "flee"
    aliases = ["run", "escape"]
    help_text = "flee - Attempt to escape from combat"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the flee command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to flee.", "RED")
            )
            return

        try:
            # Check if in combat
            combat = get_combat_for_character(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(colorize("You are not in combat!", "RED"))
                return

            # Attempt to flee
            success, message = await combat.attempt_flee(ctx.session.character_id)

            await ctx.connection.send_line(colorize(message, "GREEN" if success else "RED"))

        except Exception as e:
            logger.error("flee_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Flee attempt failed. Please try again.", "RED")
            )


class CombatStatusCommand(Command):
    """View current combat status."""

    name = "combat"
    aliases = ["cs"]
    help_text = "combat - View current combat status"
    min_args = 0
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the combat status command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to check combat.", "RED")
            )
            return

        try:
            # Check if in combat
            combat = get_combat_for_character(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(colorize("You are not in combat.", "YELLOW"))
                return

            # Show combat status
            status = combat.get_combat_status()
            await ctx.connection.send_line(status)

        except Exception as e:
            logger.error("combat_status_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to get combat status. Please try again.", "RED")
            )
