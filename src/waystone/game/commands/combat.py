"""Combat commands for Waystone MUD."""

from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems import unified_combat
from waystone.game.systems.combat import Combat, CombatState
from waystone.game.systems.npc_combat import find_npc_by_name, get_npcs_in_room
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
    aliases = ["att", "a", "k", "kill"]
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

                # First, check for NPC targets
                npc_target = find_npc_by_name(attacker.current_room_id, target_name)

                if npc_target:
                    # NPC combat - use unified combat system
                    # Check for existing combat in room
                    combat = unified_combat.get_combat_for_room(attacker.current_room_id)

                    if not combat:
                        # Create new combat
                        combat = await unified_combat.create_combat(
                            attacker.current_room_id,
                            ctx.engine,
                        )

                        # Add player participant
                        player_participant = await combat.add_participant(
                            entity_id=str(attacker.id),
                            entity_name=attacker.name,
                            is_npc=False,
                            target_id=npc_target.id,
                        )
                        player_participant._entity_ref = attacker

                        # Add NPC participant
                        npc_participant = await combat.add_participant(
                            entity_id=npc_target.id,
                            entity_name=npc_target.name,
                            is_npc=True,
                            target_id=str(attacker.id),
                        )
                        npc_participant._entity_ref = npc_target

                        # Set NPC's last_hit_by for targeting
                        npc_target.last_hit_by = str(attacker.id)

                        # Pack mentality: same-type NPCs join the fight
                        pack_npcs = []
                        if npc_target.pack_mentality:
                            for other_npc in get_npcs_in_room(attacker.current_room_id):
                                if (
                                    other_npc.id != npc_target.id
                                    and other_npc.template_id == npc_target.template_id
                                    and other_npc.is_alive
                                    and other_npc.pack_mentality
                                ):
                                    pack_participant = await combat.add_participant(
                                        entity_id=other_npc.id,
                                        entity_name=other_npc.name,
                                        is_npc=True,
                                        target_id=str(attacker.id),
                                    )
                                    pack_participant._entity_ref = other_npc
                                    pack_npcs.append(other_npc)

                        # Start combat
                        await combat.start()

                        await ctx.connection.send_line(
                            colorize(
                                f"You engage {npc_target.name} in combat! Rounds will execute automatically every 3 seconds.",
                                "YELLOW",
                            )
                        )

                        # Notify about pack joining
                        if pack_npcs:
                            pack_names = ", ".join(n.short_description for n in pack_npcs)
                            await ctx.connection.send_line(
                                colorize(f"{pack_names} joins the fight!", "RED")
                            )
                    else:
                        # Already in combat - check if player is a participant
                        player_participant = combat.get_participant(str(attacker.id))
                        if not player_participant:
                            # Add player to existing combat
                            player_participant = await combat.add_participant(
                                entity_id=str(attacker.id),
                                entity_name=attacker.name,
                                is_npc=False,
                                target_id=npc_target.id,
                            )
                            player_participant._entity_ref = attacker
                            await ctx.connection.send_line(
                                colorize(
                                    f"You join the combat against {npc_target.name}!", "YELLOW"
                                )
                            )
                        else:
                            # Player already in combat - switch target
                            if await combat.switch_target(player_participant, npc_target.id):
                                await ctx.connection.send_line(
                                    colorize(f"You now target {npc_target.name}!", "YELLOW")
                                )
                            else:
                                await ctx.connection.send_line(
                                    colorize("You're already engaged in combat!", "RED")
                                )

                        # Update NPC's last_hit_by
                        npc_target.last_hit_by = str(attacker.id)

                    return

                # Find player target in room
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
                    # Show available targets
                    npcs = get_npcs_in_room(attacker.current_room_id)
                    if npcs:
                        npc_names = ", ".join(npc.name for npc in npcs)
                        await ctx.connection.send_line(
                            colorize(f"You don't see '{target_name}' here.", "RED")
                        )
                        await ctx.connection.send_line(
                            colorize(f"NPCs here: {npc_names}", "YELLOW")
                        )
                    else:
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
            # Check if in unified combat first
            combat = unified_combat.get_combat_for_entity(ctx.session.character_id)

            if combat:
                # Use unified combat system
                participant = combat.get_participant(ctx.session.character_id)
                if participant:
                    success = await combat.attempt_flee(participant)
                    # Message is broadcast by attempt_flee
                    return

            # Fall back to old combat system
            old_combat = get_combat_for_character(ctx.session.character_id)

            if not old_combat:
                await ctx.connection.send_line(colorize("You are not in combat!", "RED"))
                return

            # Attempt to flee (old system)
            success, message = await old_combat.attempt_flee(ctx.session.character_id)

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


class BashCommand(Command):
    """Bash skill - knockdown attack."""

    name = "bash"
    aliases = []
    help_text = "bash <target> - Powerful knockdown attack (2-round lag, 15s cooldown)"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the bash command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use bash.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: bash <target>", "YELLOW"))
            return

        try:
            # Check if in unified combat
            combat = unified_combat.get_combat_for_entity(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(
                    colorize("You must be in combat to use bash!", "RED")
                )
                return

            # Get participant
            participant = combat.get_participant(ctx.session.character_id)
            if not participant:
                await ctx.connection.send_line(colorize("You are not in this combat!", "RED"))
                return

            # Check if on cooldown
            if unified_combat.is_skill_on_cooldown(participant, "bash"):
                await ctx.connection.send_line(colorize("Bash is still on cooldown!", "RED"))
                return

            # Check if in wait state
            if participant.wait_state_until and datetime.now() < participant.wait_state_until:
                await ctx.connection.send_line(
                    colorize("You are still recovering from your last action!", "RED")
                )
                return

            # Find target by keyword
            target_name = " ".join(ctx.args)
            target = combat.find_participant_by_keyword(
                target_name, exclude_id=participant.entity_id
            )

            if not target:
                await ctx.connection.send_line(
                    colorize(f"You don't see '{target_name}' in this combat.", "RED")
                )
                return

            # Execute bash
            success, msg = await unified_combat.execute_bash(combat, participant, target)
            # Message is broadcast by execute_bash

        except Exception as e:
            logger.error("bash_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Bash failed. Please try again.", "RED"))


class KickCommand(Command):
    """Kick skill - quick damage attack."""

    name = "kick"
    aliases = []
    help_text = "kick <target> - Quick damage attack (1-round lag, 10s cooldown)"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the kick command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use kick.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: kick <target>", "YELLOW"))
            return

        try:
            # Check if in unified combat
            combat = unified_combat.get_combat_for_entity(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(
                    colorize("You must be in combat to use kick!", "RED")
                )
                return

            # Get participant
            participant = combat.get_participant(ctx.session.character_id)
            if not participant:
                await ctx.connection.send_line(colorize("You are not in this combat!", "RED"))
                return

            # Check if on cooldown
            if unified_combat.is_skill_on_cooldown(participant, "kick"):
                await ctx.connection.send_line(colorize("Kick is still on cooldown!", "RED"))
                return

            # Check if in wait state
            if participant.wait_state_until and datetime.now() < participant.wait_state_until:
                await ctx.connection.send_line(
                    colorize("You are still recovering from your last action!", "RED")
                )
                return

            # Find target by keyword
            target_name = " ".join(ctx.args)
            target = combat.find_participant_by_keyword(
                target_name, exclude_id=participant.entity_id
            )

            if not target:
                await ctx.connection.send_line(
                    colorize(f"You don't see '{target_name}' in this combat.", "RED")
                )
                return

            # Execute kick
            success, msg = await unified_combat.execute_kick(combat, participant, target)
            # Message is broadcast by execute_kick

        except Exception as e:
            logger.error("kick_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Kick failed. Please try again.", "RED"))


class DisarmCommand(Command):
    """Disarm skill - remove target's weapon."""

    name = "disarm"
    aliases = []
    help_text = "disarm <target> - Remove target's weapon (2-round lag, 30s cooldown)"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the disarm command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use disarm.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: disarm <target>", "YELLOW"))
            return

        try:
            # Check if in unified combat
            combat = unified_combat.get_combat_for_entity(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(
                    colorize("You must be in combat to use disarm!", "RED")
                )
                return

            # Get participant
            participant = combat.get_participant(ctx.session.character_id)
            if not participant:
                await ctx.connection.send_line(colorize("You are not in this combat!", "RED"))
                return

            # Check if on cooldown
            if unified_combat.is_skill_on_cooldown(participant, "disarm"):
                await ctx.connection.send_line(colorize("Disarm is still on cooldown!", "RED"))
                return

            # Check if in wait state
            if participant.wait_state_until and datetime.now() < participant.wait_state_until:
                await ctx.connection.send_line(
                    colorize("You are still recovering from your last action!", "RED")
                )
                return

            # Find target by keyword
            target_name = " ".join(ctx.args)
            target = combat.find_participant_by_keyword(
                target_name, exclude_id=participant.entity_id
            )

            if not target:
                await ctx.connection.send_line(
                    colorize(f"You don't see '{target_name}' in this combat.", "RED")
                )
                return

            # Execute disarm
            success, msg = await unified_combat.execute_disarm(combat, participant, target)
            # Message is broadcast by execute_disarm

        except Exception as e:
            logger.error("disarm_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Disarm failed. Please try again.", "RED"))


class TripCommand(Command):
    """Trip skill - knock target prone."""

    name = "trip"
    aliases = []
    help_text = "trip <target> - Knock target prone (-2 hit, 1-round lag, 12s cooldown)"
    min_args = 1
    requires_character = True

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the trip command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use trip.", "RED")
            )
            return

        if len(ctx.args) < 1:
            await ctx.connection.send_line(colorize("Usage: trip <target>", "YELLOW"))
            return

        try:
            # Check if in unified combat
            combat = unified_combat.get_combat_for_entity(ctx.session.character_id)

            if not combat:
                await ctx.connection.send_line(
                    colorize("You must be in combat to use trip!", "RED")
                )
                return

            # Get participant
            participant = combat.get_participant(ctx.session.character_id)
            if not participant:
                await ctx.connection.send_line(colorize("You are not in this combat!", "RED"))
                return

            # Check if on cooldown
            if unified_combat.is_skill_on_cooldown(participant, "trip"):
                await ctx.connection.send_line(colorize("Trip is still on cooldown!", "RED"))
                return

            # Check if in wait state
            if participant.wait_state_until and datetime.now() < participant.wait_state_until:
                await ctx.connection.send_line(
                    colorize("You are still recovering from your last action!", "RED")
                )
                return

            # Find target by keyword
            target_name = " ".join(ctx.args)
            target = combat.find_participant_by_keyword(
                target_name, exclude_id=participant.entity_id
            )

            if not target:
                await ctx.connection.send_line(
                    colorize(f"You don't see '{target_name}' in this combat.", "RED")
                )
                return

            # Execute trip
            success, msg = await unified_combat.execute_trip(combat, participant, target)
            # Message is broadcast by execute_trip

        except Exception as e:
            logger.error("trip_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Trip failed. Please try again.", "RED"))
