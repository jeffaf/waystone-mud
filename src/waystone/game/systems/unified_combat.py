"""Unified combat system for Waystone MUD.

Phase 1: Automatic round-based combat framework for both players and NPCs.
Implements the core combat loop with 3-second combat rounds (ROM PULSE_VIOLENCE).

This system provides:
- Unified CombatParticipant for both players and NPCs
- Automatic combat rounds every 3 seconds
- Initiative-based action ordering
- Combat state management (SETUP, ACTIVE, ENDED)
- Global combat registry by room and entity
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from waystone.network import colorize

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine
    from waystone.game.systems.npc_combat import NPCInstance

logger = structlog.get_logger(__name__)


def calculate_attribute_modifier(attribute: int) -> int:
    """Calculate D&D-style attribute modifier: (attribute - 10) // 2"""
    return (attribute - 10) // 2


def roll_d20() -> int:
    """Roll a d20."""
    return random.randint(1, 20)


def roll_initiative(dex_modifier: int) -> int:
    """Roll initiative with DEX modifier: d20 + dex_modifier"""
    return roll_d20() + dex_modifier


def get_damage_message(damage: int) -> str:
    """Get ROM-style damage verb based on damage amount."""
    if damage == 0:
        return "miss"
    elif damage < 5:
        return "scratch"
    elif damage < 15:
        return "hit"
    elif damage < 20:
        return "wound"
    elif damage < 30:
        return "maul"
    elif damage < 100:
        return "MASSACRE"
    else:
        return "ANNIHILATE"


class CombatState(Enum):
    """Combat state machine states."""

    SETUP = "setup"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass
class CombatParticipant:
    """Unified participant for players and NPCs in combat.

    This dataclass represents any entity participating in combat,
    whether it's a player character or an NPC. It tracks combat-specific
    state like initiative, targeting, and wait states.

    Attributes:
        entity_id: Character UUID (str) or NPC instance ID
        entity_name: Display name for combat messages
        is_npc: True for NPCs, False for player characters
        initiative: d20 + DEX modifier for turn order
        target_id: Current target entity ID (if any)
        wait_state_until: Timestamp when skill lag expires (if any)
        is_defending: True if entity is in defensive stance
        fled: True if entity successfully fled from combat
        damage_dealt: Total damage dealt (used for XP sharing calculations)
        _entity_ref: Cached reference to Character or NPCInstance (internal)
    """

    entity_id: str  # Character UUID or NPC instance ID
    entity_name: str  # Display name
    is_npc: bool  # True for NPCs, False for players
    initiative: int = 0  # d20 + DEX modifier
    target_id: str | None = None  # Current target
    wait_state_until: datetime | None = None  # Skill lag
    is_defending: bool = False
    fled: bool = False
    damage_dealt: int = 0  # Track for XP sharing

    # Cached entity reference (set after creation)
    _entity_ref: Any = field(default=None, repr=False)


async def get_participant_hp(participant: CombatParticipant) -> tuple[int, int]:
    """Get HP for participant. Returns (current_hp, max_hp)."""
    if participant._entity_ref:
        if participant.is_npc:
            return (participant._entity_ref.current_hp, participant._entity_ref.max_hp)
        else:
            # Player character
            return (participant._entity_ref.current_hp, participant._entity_ref.max_hp)
    # Default fallback
    return (100, 100)


async def get_participant_attribute(participant: CombatParticipant, attr: str) -> int:
    """Get attribute value for participant."""
    if participant._entity_ref:
        if participant.is_npc:
            return participant._entity_ref.attributes.get(attr, 10)
        else:
            # Player character - access attribute directly
            return getattr(participant._entity_ref, attr, 10)
    return 10  # Default


async def apply_damage_to_participant(participant: CombatParticipant, damage: int) -> int:
    """Apply damage to participant. Returns new HP."""
    if participant._entity_ref:
        if participant.is_npc:
            participant._entity_ref.current_hp = max(0, participant._entity_ref.current_hp - damage)
            return participant._entity_ref.current_hp
        else:
            # Player character
            participant._entity_ref.current_hp = max(0, participant._entity_ref.current_hp - damage)
            return participant._entity_ref.current_hp
    return 0


async def roll_to_hit(attacker: CombatParticipant, defender: CombatParticipant) -> tuple[bool, bool, int]:
    """Roll to-hit check. Returns (hit, is_critical, raw_roll)."""
    raw_roll = roll_d20()

    # Natural 1 always misses
    if raw_roll == 1:
        return (False, False, raw_roll)

    # Natural 20 always crits
    if raw_roll == 20:
        return (True, True, raw_roll)

    # Get DEX modifiers
    attacker_dex = await get_participant_attribute(attacker, "dexterity")
    defender_dex = await get_participant_attribute(defender, "dexterity")

    attack_modifier = calculate_attribute_modifier(attacker_dex)
    defense_value = 10 + calculate_attribute_modifier(defender_dex)

    # Defending stance adds +5
    if defender.is_defending:
        defense_value += 5

    total_attack = raw_roll + attack_modifier
    hit = total_attack >= defense_value

    return (hit, False, raw_roll)


async def calculate_damage(attacker: CombatParticipant, is_critical: bool) -> int:
    """Calculate damage. Base: 1d6 + STR mod, Critical: 2d6 + STR mod."""
    str_value = await get_participant_attribute(attacker, "strength")
    str_modifier = calculate_attribute_modifier(str_value)

    if is_critical:
        # 2d6 for critical
        base_damage = random.randint(1, 6) + random.randint(1, 6)
    else:
        # 1d6 normal
        base_damage = random.randint(1, 6)

    total_damage = base_damage + str_modifier
    return max(1, total_damage)  # Minimum 1 damage


class Combat:
    """Unified combat instance for automatic round-based combat.

    This class manages a single combat encounter in a room. It handles:
    - Adding/removing participants (players and NPCs)
    - Rolling initiative and determining turn order
    - Running automatic combat rounds every 3 seconds
    - Checking combat continuation conditions
    - Broadcasting combat events to the room

    The combat loop runs asynchronously using asyncio.create_task() and
    continues until combat ends (one side defeated, all fled, etc.).
    """

    ROUND_INTERVAL = 3.0  # Seconds between rounds (ROM PULSE_VIOLENCE)

    def __init__(self, room_id: str, engine: "GameEngine") -> None:
        """Initialize a new combat instance.

        Args:
            room_id: The room where combat is taking place
            engine: The game engine instance for broadcasting and entity access
        """
        self.room_id = room_id
        self.engine = engine
        self.state = CombatState.SETUP
        self.participants: list[CombatParticipant] = []
        self.round_number = 0
        self.round_task: asyncio.Task | None = None
        self.created_at = datetime.now()

        logger.info("unified_combat_initialized", room_id=room_id)

    async def add_participant(
        self,
        entity_id: str,
        entity_name: str,
        is_npc: bool,
        target_id: str | None = None,
    ) -> CombatParticipant:
        """Add a participant to combat.

        Args:
            entity_id: Character UUID or NPC instance ID
            entity_name: Display name for combat messages
            is_npc: True for NPCs, False for player characters
            target_id: Initial target (optional)

        Returns:
            The created CombatParticipant

        Raises:
            ValueError: If participant already exists in combat
        """
        # Check if already in combat
        existing = self.get_participant(entity_id)
        if existing:
            logger.warning(
                "participant_already_in_combat",
                entity_id=entity_id,
                room_id=self.room_id,
            )
            raise ValueError(f"Entity {entity_id} already in combat")

        # Create participant with initiative roll
        participant = CombatParticipant(
            entity_id=entity_id,
            entity_name=entity_name,
            is_npc=is_npc,
            initiative=0,  # Will be rolled when combat starts
            target_id=target_id,
        )

        # Roll initiative
        participant.initiative = self._roll_initiative(participant)

        self.participants.append(participant)

        logger.info(
            "participant_added_to_unified_combat",
            entity_id=entity_id,
            entity_name=entity_name,
            is_npc=is_npc,
            initiative=participant.initiative,
            room_id=self.room_id,
        )

        return participant

    async def remove_participant(self, entity_id: str) -> None:
        """Remove a participant from combat.

        This is called when an entity dies, flees, or otherwise
        leaves combat. It also checks if combat should end.

        Args:
            entity_id: The entity to remove
        """
        participant = self.get_participant(entity_id)
        if not participant:
            logger.warning(
                "participant_not_found_for_removal",
                entity_id=entity_id,
                room_id=self.room_id,
            )
            return

        self.participants = [p for p in self.participants if p.entity_id != entity_id]

        logger.info(
            "participant_removed_from_unified_combat",
            entity_id=entity_id,
            entity_name=participant.entity_name,
            room_id=self.room_id,
            remaining=len(self.participants),
        )

        # Check if combat should end
        if not self._check_combat_continues():
            await self.end_combat("no_valid_participants")

    def get_participant(self, entity_id: str) -> CombatParticipant | None:
        """Get a participant by entity ID.

        Args:
            entity_id: The entity ID to search for

        Returns:
            The CombatParticipant or None if not found
        """
        for participant in self.participants:
            if participant.entity_id == entity_id:
                return participant
        return None

    def is_character_in_combat(self, entity_id: str) -> bool:
        """Check if a character is in this combat."""
        return self.get_participant(entity_id) is not None

    async def start(self) -> None:
        """Start combat by sorting participants and beginning the round loop.

        This transitions combat from SETUP to ACTIVE and kicks off the
        automatic combat round loop.
        """
        if self.state != CombatState.SETUP:
            logger.warning(
                "combat_already_started",
                state=self.state.value,
                room_id=self.room_id,
            )
            return

        # Sort by initiative (highest first)
        self.participants.sort(key=lambda p: p.initiative, reverse=True)
        self.state = CombatState.ACTIVE
        self.round_number = 0

        # Broadcast combat start
        start_msg = colorize("\n=== Combat begins! ===", "RED")
        self.engine.broadcast_to_room(self.room_id, start_msg)

        # Show initiative order
        order_lines = ["Initiative order:"]
        for participant in self.participants:
            type_label = "NPC" if participant.is_npc else "Player"
            order_lines.append(
                f"  {participant.entity_name} ({type_label}): {participant.initiative}"
            )
        self.engine.broadcast_to_room(self.room_id, "\n".join(order_lines))

        logger.info(
            "unified_combat_started",
            room_id=self.room_id,
            participant_count=len(self.participants),
            turn_order=[p.entity_name for p in self.participants],
        )

        # Start the combat round loop
        self.round_task = asyncio.create_task(self._combat_round_loop())

    async def end_combat(self, reason: str = "ended") -> None:
        """End combat and clean up.

        Args:
            reason: Reason for combat ending (for logging)
        """
        if self.state == CombatState.ENDED:
            return

        self.state = CombatState.ENDED

        # Cancel the round loop task if running
        if self.round_task and not self.round_task.done():
            self.round_task.cancel()
            try:
                await self.round_task
            except asyncio.CancelledError:
                pass
            self.round_task = None

        # Broadcast combat end
        end_msg = colorize("\n=== Combat has ended ===\n", "GREEN")
        self.engine.broadcast_to_room(self.room_id, end_msg)

        logger.info(
            "unified_combat_ended",
            room_id=self.room_id,
            reason=reason,
            rounds=self.round_number,
            duration=(datetime.now() - self.created_at).total_seconds(),
        )

    async def _combat_round_loop(self) -> None:
        """Main combat round loop that runs every ROUND_INTERVAL seconds.

        This loop continues until combat ends. Each iteration executes
        one combat round and then waits for the next round interval.
        """
        try:
            while self.state == CombatState.ACTIVE:
                # Execute the combat round
                await self._execute_round()

                # Check if combat should continue
                if not self._should_continue_combat():
                    await self.end_combat("combat_resolved")
                    break

                # Wait for next round
                await asyncio.sleep(self.ROUND_INTERVAL)

        except asyncio.CancelledError:
            logger.info(
                "combat_round_loop_cancelled",
                room_id=self.room_id,
                round_number=self.round_number,
            )
            raise
        except Exception as e:
            logger.error(
                "combat_round_loop_error",
                room_id=self.room_id,
                round_number=self.round_number,
                error=str(e),
                exc_info=True,
            )
            await self.end_combat("error")

    async def _execute_round(self) -> None:
        """Execute a single combat round.

        This method is called every ROUND_INTERVAL seconds by the round loop.
        It processes actions for all participants in initiative order.

        Note: Actual attack/damage mechanics are implemented by another engineer.
        This is just the framework for round execution.
        """
        self.round_number += 1

        # Broadcast round start
        round_msg = colorize(
            f"\n--- Round {self.round_number} ---",
            "CYAN",
        )
        self.engine.broadcast_to_room(self.room_id, round_msg)

        logger.debug(
            "combat_round_executing",
            room_id=self.room_id,
            round_number=self.round_number,
            participant_count=len(self.participants),
        )

        # Process each participant in initiative order
        for participant in self.participants:
            # Skip if fled
            if participant.fled:
                continue

            # Check wait state (skill lag)
            if participant.wait_state_until:
                if datetime.now() < participant.wait_state_until:
                    # Still in wait state, skip turn
                    msg = colorize(
                        f"{participant.entity_name} is recovering...",
                        "YELLOW",
                    )
                    self.engine.broadcast_to_room(self.room_id, msg)
                    continue
                else:
                    # Wait state expired
                    participant.wait_state_until = None

            # TODO: Actual combat action processing will be implemented here
            # For now, just log that this participant would act
            logger.debug(
                "participant_turn",
                entity_id=participant.entity_id,
                entity_name=participant.entity_name,
                is_npc=participant.is_npc,
                round_number=self.round_number,
            )

        # Reset defending flags at end of round
        for participant in self.participants:
            participant.is_defending = False

    def _check_combat_continues(self) -> bool:
        """Check if combat should continue.

        Combat ends when:
        - All participants on one side are defeated/fled
        - Only one participant remains
        - No valid participants remain

        Returns:
            True if combat should continue, False otherwise
        """
        # Filter out fled participants
        active = [p for p in self.participants if not p.fled]

        if len(active) < 2:
            logger.info(
                "combat_ending_insufficient_active",
                room_id=self.room_id,
                active_count=len(active),
            )
            return False

        # Count NPCs vs Players
        npc_count = sum(1 for p in active if p.is_npc)
        player_count = sum(1 for p in active if not p.is_npc)

        # Combat ends if one side has no participants
        if npc_count == 0 or player_count == 0:
            logger.info(
                "combat_ending_one_side_eliminated",
                room_id=self.room_id,
                npcs=npc_count,
                players=player_count,
            )
            return False

        return True

    def _should_continue_combat(self) -> bool:
        """Check if combat should continue. Alias for _check_combat_continues."""
        return self._check_combat_continues()

    def _is_dead_sync(self, participant: CombatParticipant) -> bool:
        """Check if participant is dead (synchronous check via entity ref)."""
        if participant._entity_ref:
            if participant.is_npc:
                return participant._entity_ref.current_hp <= 0
            else:
                return participant._entity_ref.current_hp <= 0
        return False

    def _is_in_wait_state(self, participant: CombatParticipant) -> bool:
        """Check if participant is in wait state (skill lag)."""
        if participant.wait_state_until is None:
            return False
        return datetime.now() < participant.wait_state_until

    async def attempt_flee(self, participant: CombatParticipant) -> bool:
        """Attempt to flee from combat.

        Flee check: d20 + DEX mod >= 10 (~60% success for DEX 10).
        On failure, sets 1-second wait state.
        """
        dex = 10  # Default
        if participant._entity_ref:
            if participant.is_npc:
                dex = participant._entity_ref.attributes.get("dexterity", 10)
            else:
                dex = getattr(participant._entity_ref, "dexterity", 10)

        dex_modifier = calculate_attribute_modifier(dex)
        roll = roll_d20()
        total = roll + dex_modifier

        success = total >= 10

        if success:
            participant.fled = True
            msg = colorize(f"{participant.entity_name} flees from combat!", "YELLOW")
            self.engine.broadcast_to_room(self.room_id, msg)
            logger.info(
                "participant_fled",
                entity_id=participant.entity_id,
                entity_name=participant.entity_name,
                roll=roll,
                total=total,
            )
        else:
            # Failed flee attempt - 1 second wait state
            participant.wait_state_until = datetime.now() + timedelta(seconds=1)
            msg = colorize(f"{participant.entity_name} fails to flee!", "RED")
            self.engine.broadcast_to_room(self.room_id, msg)
            logger.info(
                "flee_failed",
                entity_id=participant.entity_id,
                roll=roll,
                total=total,
            )

        return success

    async def switch_target(self, participant: CombatParticipant, target_id: str) -> bool:
        """Switch participant's target to a new entity.

        Returns False if:
        - Target not in combat
        - Target is self
        - Target has fled
        """
        # Can't target self
        if target_id == participant.entity_id:
            return False

        # Find target
        target = self.get_participant(target_id)
        if not target:
            return False

        # Can't target fled participants
        if target.fled:
            return False

        participant.target_id = target_id
        logger.debug(
            "target_switched",
            entity_id=participant.entity_id,
            new_target=target_id,
        )
        return True

    async def _auto_action(self, participant: CombatParticipant) -> None:
        """Execute automatic combat action for a participant."""
        # Skip if in wait state
        if self._is_in_wait_state(participant):
            return

        # Find target
        if not participant.target_id:
            return

        target = self.get_participant(participant.target_id)
        if not target or target.fled:
            return

        # Roll to hit
        hit, is_crit, roll = await roll_to_hit(participant, target)

        if hit:
            damage = await calculate_damage(participant, is_crit)
            await apply_damage_to_participant(target, damage)

            damage_verb = get_damage_message(damage)
            crit_text = " CRITICAL!" if is_crit else ""
            msg = colorize(
                f"{participant.entity_name}'s attack {damage_verb}s {target.entity_name} for {damage} damage!{crit_text}",
                "RED" if is_crit else "YELLOW",
            )
            self.engine.broadcast_to_room(self.room_id, msg)
        else:
            msg = colorize(
                f"{participant.entity_name}'s attack misses {target.entity_name}!",
                "CYAN",
            )
            self.engine.broadcast_to_room(self.room_id, msg)

    def _roll_initiative(self, participant: CombatParticipant) -> int:
        """Roll initiative for a participant.

        Initiative is d20 + DEX modifier. For NPCs, we'll need to
        access their attributes. For players, we'll need to query
        the database or use cached values.

        Args:
            participant: The participant to roll initiative for

        Returns:
            Initiative value (d20 + DEX modifier)

        Note: This is a placeholder implementation. The actual DEX
        modifier calculation will need to access entity attributes.
        """
        # Roll d20
        roll = random.randint(1, 20)

        # TODO: Get DEX modifier from entity
        # For now, use a default modifier of 0
        dex_modifier = 0

        # If entity_ref is set, try to get DEX from it
        # (This will be implemented when entities are cached)
        # if participant._entity_ref:
        #     if participant.is_npc:
        #         dex = participant._entity_ref.attributes.get("dexterity", 10)
        #     else:
        #         dex = participant._entity_ref.dexterity
        #     dex_modifier = (dex - 10) // 2

        total = roll + dex_modifier

        logger.debug(
            "initiative_rolled",
            entity_id=participant.entity_id,
            entity_name=participant.entity_name,
            roll=roll,
            dex_modifier=dex_modifier,
            total=total,
        )

        return total


# ============================================================================
# Global Combat Registry
# ============================================================================

# Global registry of active combats by room
_active_combats: dict[str, Combat] = {}


def get_combat_for_room(room_id: str) -> Combat | None:
    """Get active combat in a room.

    Args:
        room_id: The room ID to check

    Returns:
        Active Combat instance or None if no active combat
    """
    combat = _active_combats.get(room_id)
    if combat and combat.state != CombatState.ENDED:
        return combat
    return None


def get_combat_for_entity(entity_id: str) -> Combat | None:
    """Find combat containing an entity.

    Searches all active combats to find one containing the
    specified entity ID.

    Args:
        entity_id: The entity ID to search for

    Returns:
        Combat instance containing the entity, or None if not found
    """
    for combat in _active_combats.values():
        if combat.state != CombatState.ENDED:
            if combat.get_participant(entity_id):
                return combat
    return None


async def create_combat(room_id: str, engine: "GameEngine") -> Combat:
    """Create a new combat in a room.

    Args:
        room_id: The room where combat will take place
        engine: The game engine instance

    Returns:
        The newly created Combat instance

    Note: This does not start combat, just creates it in SETUP state.
    Call combat.start() after adding all participants.
    """
    combat = Combat(room_id, engine)
    _active_combats[room_id] = combat

    logger.info(
        "unified_combat_created",
        room_id=room_id,
    )

    return combat


def cleanup_ended_combats() -> int:
    """Remove ended combats from registry.

    This should be called periodically to clean up finished combats
    and free memory.

    Returns:
        Number of combats removed
    """
    to_remove = [rid for rid, c in _active_combats.items() if c.state == CombatState.ENDED]

    for rid in to_remove:
        del _active_combats[rid]

    if to_remove:
        logger.debug(
            "unified_combats_cleaned_up",
            count=len(to_remove),
            rooms=to_remove,
        )

    return len(to_remove)
