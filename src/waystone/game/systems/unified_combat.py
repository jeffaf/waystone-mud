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


def is_skill_on_cooldown(participant: "CombatParticipant", skill_name: str) -> bool:
    """Check if a skill is on cooldown for a participant.

    Args:
        participant: The combat participant
        skill_name: Name of the skill to check

    Returns:
        True if skill is on cooldown, False if ready to use
    """
    if skill_name not in participant.skill_cooldowns:
        return False

    cooldown_expires = participant.skill_cooldowns[skill_name]
    return datetime.now() < cooldown_expires


def set_skill_cooldown(participant: "CombatParticipant", skill_name: str, seconds: int) -> None:
    """Set a skill cooldown for a participant.

    Args:
        participant: The combat participant
        skill_name: Name of the skill
        seconds: Cooldown duration in seconds
    """
    participant.skill_cooldowns[skill_name] = datetime.now() + timedelta(seconds=seconds)


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
        skill_cooldowns: Dict of skill_name -> expiration datetime
        effects: Dict of effect_name -> effect_value (knockdown, prone, disarmed, etc.)
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
    skill_cooldowns: dict[str, datetime] = field(default_factory=dict)  # Skill cooldowns
    effects: dict[str, Any] = field(default_factory=dict)  # Combat effects

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


def get_position_defense_penalty(participant: CombatParticipant) -> int:
    """Get defense penalty based on position (resting/sleeping).

    Resting players are easier to hit (-2 to defense).
    Sleeping players are much easier to hit (-4 to defense).
    NPCs don't have position, so no penalty.

    Args:
        participant: The combat participant

    Returns:
        Defense penalty (negative number to subtract from AC)
    """
    if participant.is_npc:
        return 0

    if participant._entity_ref:
        position = getattr(participant._entity_ref, "position", "standing")
        if position == "resting":
            return -2  # Easier to hit when resting
        elif position == "sleeping":
            return -4  # Much easier to hit when sleeping

    return 0


async def apply_damage_to_participant(participant: CombatParticipant, damage: int) -> int:
    """Apply damage to participant. Returns new HP.

    For player characters, this also persists the HP change to the database
    so the prompt displays accurate HP values.
    """
    if participant._entity_ref:
        if participant.is_npc:
            participant._entity_ref.current_hp = max(0, participant._entity_ref.current_hp - damage)
            return participant._entity_ref.current_hp
        else:
            # Player character - update in memory
            new_hp = max(0, participant._entity_ref.current_hp - damage)
            participant._entity_ref.current_hp = new_hp

            # Persist to database so prompt shows correct HP
            try:
                from uuid import UUID

                from sqlalchemy import update

                from waystone.database.engine import get_session
                from waystone.database.models import Character

                async with get_session() as session:
                    await session.execute(
                        update(Character)
                        .where(Character.id == UUID(participant.entity_id))
                        .values(current_hp=new_hp)
                    )
                    await session.commit()
            except Exception as e:
                logger.warning(
                    "failed_to_persist_hp",
                    entity_id=participant.entity_id,
                    error=str(e),
                )

            return new_hp
    return 0


async def roll_to_hit(
    attacker: CombatParticipant, defender: CombatParticipant
) -> tuple[bool, bool, int]:
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

    # Position penalty (resting/sleeping makes you easier to hit)
    defense_value += get_position_defense_penalty(defender)

    # Check for prone effect on attacker (-2 to hit)
    prone_penalty = attacker.effects.get("prone", 0)

    total_attack = raw_roll + attack_modifier + prone_penalty
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


# ============================================================================
# Combat Skills (Phase 3)
# ============================================================================


async def execute_bash(
    combat: "Combat", attacker: CombatParticipant, target: CombatParticipant
) -> tuple[bool, str]:
    """Execute bash skill - knockdown attack.

    Roll: d20 + STR vs target AC
    Effect: If hit, target knocked down, loses next turn (wait_state)
    Damage: 1d4 + STR bonus
    User gets 2-round wait state (skill lag)
    Cooldown: 15 seconds

    Args:
        combat: The combat instance
        attacker: The attacking participant
        target: The target participant

    Returns:
        (success, message) tuple
    """
    # Get attacker STR for roll
    attacker_str = await get_participant_attribute(attacker, "strength")
    str_modifier = calculate_attribute_modifier(attacker_str)

    # Get target DEX for AC
    target_dex = await get_participant_attribute(target, "dexterity")
    target_ac = 10 + calculate_attribute_modifier(target_dex)

    # Roll to hit: d20 + STR
    roll = roll_d20()
    total = roll + str_modifier

    if total >= target_ac:
        # Hit! Calculate damage: 1d4 + STR
        base_damage = random.randint(1, 4)
        damage = base_damage + str_modifier
        damage = max(1, damage)  # Minimum 1

        # Apply damage
        await apply_damage_to_participant(target, damage)

        # Apply knockdown effect - target loses next turn
        target.effects["knocked_down"] = True
        target.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL)

        # Apply wait state to attacker (2 rounds)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL * 2)

        # Set cooldown (15 seconds)
        set_skill_cooldown(attacker, "bash", 15)

        # Broadcast message
        damage_verb = get_damage_message(damage)
        msg = (
            f"{attacker.entity_name}'s powerful bash {damage_verb}s {target.entity_name} for {damage} damage! "
            f"{target.entity_name} is knocked down and stunned!"
        )
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "RED"))

        return (True, msg)
    else:
        # Miss
        # Still apply wait state to attacker (2 rounds)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL * 2)

        # Set cooldown even on miss (15 seconds)
        set_skill_cooldown(attacker, "bash", 15)

        msg = f"{attacker.entity_name}'s bash misses {target.entity_name}!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "CYAN"))

        return (False, msg)


async def execute_kick(
    combat: "Combat", attacker: CombatParticipant, target: CombatParticipant
) -> tuple[bool, str]:
    """Execute kick skill - quick damage skill.

    Roll: d20 + DEX vs target AC
    Damage: 1d6 + DEX bonus
    User gets 1-round wait state
    Cooldown: 10 seconds

    Args:
        combat: The combat instance
        attacker: The attacking participant
        target: The target participant

    Returns:
        (success, message) tuple
    """
    # Get attacker DEX for roll
    attacker_dex = await get_participant_attribute(attacker, "dexterity")
    dex_modifier = calculate_attribute_modifier(attacker_dex)

    # Get target DEX for AC
    target_dex = await get_participant_attribute(target, "dexterity")
    target_ac = 10 + calculate_attribute_modifier(target_dex)

    # Roll to hit: d20 + DEX
    roll = roll_d20()
    total = roll + dex_modifier

    if total >= target_ac:
        # Hit! Calculate damage: 1d6 + DEX
        base_damage = random.randint(1, 6)
        damage = base_damage + dex_modifier
        damage = max(1, damage)

        # Apply damage
        await apply_damage_to_participant(target, damage)

        # Apply wait state to attacker (1 round)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL)

        # Set cooldown (10 seconds)
        set_skill_cooldown(attacker, "kick", 10)

        # Broadcast message
        damage_verb = get_damage_message(damage)
        msg = f"{attacker.entity_name}'s kick {damage_verb}s {target.entity_name} for {damage} damage!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "YELLOW"))

        return (True, msg)
    else:
        # Miss
        # Still apply wait state (1 round)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL)

        # Set cooldown even on miss (10 seconds)
        set_skill_cooldown(attacker, "kick", 10)

        msg = f"{attacker.entity_name}'s kick misses {target.entity_name}!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "CYAN"))

        return (False, msg)


async def execute_disarm(
    combat: "Combat", attacker: CombatParticipant, target: CombatParticipant
) -> tuple[bool, str]:
    """Execute disarm skill - remove target's weapon.

    Roll: d20 + DEX vs target DEX + 10
    Effect: Target drops weapon (if has one)
    User gets 2-round wait state
    Cooldown: 30 seconds

    Args:
        combat: The combat instance
        attacker: The attacking participant
        target: The target participant

    Returns:
        (success, message) tuple
    """
    # Get attacker DEX for roll
    attacker_dex = await get_participant_attribute(attacker, "dexterity")
    dex_modifier = calculate_attribute_modifier(attacker_dex)

    # Get target DEX for defense
    target_dex = await get_participant_attribute(target, "dexterity")
    target_dc = target_dex + 10  # Full DEX value + 10

    # Roll: d20 + DEX
    roll = roll_d20()
    total = roll + dex_modifier

    if total >= target_dc:
        # Success! Apply disarmed effect
        target.effects["disarmed"] = True

        # Apply wait state to attacker (2 rounds)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL * 2)

        # Set cooldown (30 seconds)
        set_skill_cooldown(attacker, "disarm", 30)

        msg = f"{attacker.entity_name} disarms {target.entity_name}! Their weapon clatters to the ground!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "YELLOW"))

        return (True, msg)
    else:
        # Failed
        # Still apply wait state (2 rounds)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL * 2)

        # Set cooldown even on failure (30 seconds)
        set_skill_cooldown(attacker, "disarm", 30)

        msg = f"{attacker.entity_name}'s disarm attempt fails against {target.entity_name}!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "CYAN"))

        return (False, msg)


async def execute_trip(
    combat: "Combat", attacker: CombatParticipant, target: CombatParticipant
) -> tuple[bool, str]:
    """Execute trip skill - knock target prone.

    Roll: d20 + DEX vs target DEX + 8
    Effect: Target falls, -2 to hit next round
    User gets 1-round wait state
    Cooldown: 12 seconds

    Args:
        combat: The combat instance
        attacker: The attacking participant
        target: The target participant

    Returns:
        (success, message) tuple
    """
    # Get attacker DEX for roll
    attacker_dex = await get_participant_attribute(attacker, "dexterity")
    dex_modifier = calculate_attribute_modifier(attacker_dex)

    # Get target DEX for defense
    target_dex = await get_participant_attribute(target, "dexterity")
    target_dc = target_dex + 8  # Full DEX value + 8

    # Roll: d20 + DEX
    roll = roll_d20()
    total = roll + dex_modifier

    if total >= target_dc:
        # Success! Apply prone effect (-2 to hit)
        target.effects["prone"] = -2

        # Apply wait state to attacker (1 round)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL)

        # Set cooldown (12 seconds)
        set_skill_cooldown(attacker, "trip", 12)

        msg = f"{attacker.entity_name} trips {target.entity_name}! They fall to the ground!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "YELLOW"))

        return (True, msg)
    else:
        # Failed
        # Still apply wait state (1 round)
        attacker.wait_state_until = datetime.now() + timedelta(seconds=combat.ROUND_INTERVAL)

        # Set cooldown even on failure (12 seconds)
        set_skill_cooldown(attacker, "trip", 12)

        msg = f"{attacker.entity_name}'s trip attempt fails against {target.entity_name}!"
        combat.engine.broadcast_to_room(combat.room_id, colorize(msg, "CYAN"))

        return (False, msg)


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

        # Record combat end time for players (used for recall cooldown)
        if not participant.is_npc:
            record_combat_end(entity_id)

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

    def find_participant_by_keyword(
        self, keyword: str, exclude_id: str | None = None
    ) -> CombatParticipant | None:
        """Find a participant by keyword match.

        Matches against:
        - NPC keywords (if available)
        - Entity name (partial match)

        Supports N.keyword syntax for targeting specific participants:
        - "rat" - first rat
        - "2.rat" - second rat

        Args:
            keyword: Search keyword (may include N. prefix)
            exclude_id: Entity ID to exclude from search (usually self)

        Returns:
            Matching participant or None
        """
        # Parse N.keyword syntax (e.g., "2.rat")
        target_index = 1
        search_term = keyword.lower()

        if "." in keyword:
            parts = keyword.split(".", 1)
            if parts[0].isdigit():
                target_index = int(parts[0])
                search_term = parts[1].lower()
                if target_index < 1:
                    target_index = 1

        match_count = 0

        for participant in self.participants:
            if participant.fled:
                continue
            if exclude_id and participant.entity_id == exclude_id:
                continue

            matched = False

            # For NPCs, check keywords from entity_ref
            if participant.is_npc and participant._entity_ref:
                npc = participant._entity_ref
                if hasattr(npc, "keywords") and npc.keywords:
                    for kw in npc.keywords:
                        if kw.lower() == search_term:
                            matched = True
                            break

            # Fall back to name matching (partial)
            if not matched and search_term in participant.entity_name.lower():
                matched = True

            if matched:
                match_count += 1
                if match_count == target_index:
                    return participant

        return None

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

            # Execute auto action for this participant
            await self._auto_action(participant)

        # Reset defending flags and clear temporary effects at end of round
        for participant in self.participants:
            participant.is_defending = False

            # Clear knocked_down effect (only lasts 1 turn)
            if "knocked_down" in participant.effects:
                del participant.effects["knocked_down"]

            # Clear prone effect (only lasts 1 round)
            if "prone" in participant.effects:
                del participant.effects["prone"]

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
        On success, moves player to a random adjacent room.
        """
        # Only players can flee to other rooms (NPCs just disengage)
        if participant.is_npc:
            participant.fled = True
            msg = colorize(f"{participant.entity_name} flees from combat!", "YELLOW")
            self.engine.broadcast_to_room(self.room_id, msg)
            return True

        dex = 10  # Default
        if participant._entity_ref:
            dex = getattr(participant._entity_ref, "dexterity", 10)

        dex_modifier = calculate_attribute_modifier(dex)
        roll = roll_d20()
        total = roll + dex_modifier

        success = total >= 10

        if success:
            # Get current room and find a random exit
            room = self.engine.world.get(self.room_id)
            if not room or not room.exits:
                # No exits - flee fails
                msg = colorize(f"{participant.entity_name} has nowhere to flee!", "RED")
                self.engine.broadcast_to_room(self.room_id, msg)
                return False

            # Pick a random exit
            direction = random.choice(list(room.exits.keys()))
            destination_id = room.exits[direction]
            destination_room = self.engine.world.get(destination_id)

            if not destination_room:
                msg = colorize(f"{participant.entity_name} has nowhere to flee!", "RED")
                self.engine.broadcast_to_room(self.room_id, msg)
                return False

            participant.fled = True

            # Broadcast flee message to old room
            msg = colorize(f"{participant.entity_name} flees {direction}!", "YELLOW")
            self.engine.broadcast_to_room(self.room_id, msg)

            # Move the player
            from uuid import UUID

            from sqlalchemy import select

            from waystone.database.engine import get_session
            from waystone.database.models import Character

            try:
                async with get_session() as session:
                    result = await session.execute(
                        select(Character).where(Character.id == UUID(participant.entity_id))
                    )
                    character = result.scalar_one_or_none()

                    if character:
                        # Remove from old room
                        room.remove_player(participant.entity_id)

                        # Update character location
                        character.current_room_id = destination_id
                        await session.commit()

                        # Add to new room
                        destination_room.add_player(participant.entity_id)

                        # Notify new room
                        arrive_msg = colorize(f"{participant.entity_name} arrives in a panic!", "CYAN")
                        self.engine.broadcast_to_room(
                            destination_id, arrive_msg, exclude=UUID(participant.entity_id)
                        )

                        # Show new room to the fleeing player
                        player_session = self.engine.character_to_session.get(participant.entity_id)
                        if player_session:
                            await player_session.connection.send_line(
                                colorize(f"\nYou flee {direction}!\n", "YELLOW")
                            )
                            await player_session.connection.send_line(destination_room.format_description())

                        logger.info(
                            "participant_fled",
                            entity_id=participant.entity_id,
                            entity_name=participant.entity_name,
                            from_room=self.room_id,
                            to_room=destination_id,
                            direction=direction,
                            roll=roll,
                            total=total,
                        )
            except Exception as e:
                logger.error("flee_movement_failed", error=str(e), exc_info=True)
                # Still mark as fled even if movement fails
                pass
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

    async def _execute_attack(
        self, attacker: CombatParticipant, defender: CombatParticipant
    ) -> None:
        """Execute attack from attacker to defender."""
        hit, is_crit, roll = await roll_to_hit(attacker, defender)

        if hit:
            damage = await calculate_damage(attacker, is_crit)
            new_hp = await apply_damage_to_participant(defender, damage)

            # Track damage dealt (for XP sharing later)
            attacker.damage_dealt += damage

            damage_verb = get_damage_message(damage)
            crit_text = " **CRITICAL HIT!**" if is_crit else ""
            msg = colorize(
                f"{attacker.entity_name}'s attack {damage_verb}s {defender.entity_name} for {damage} damage!{crit_text}",
                "RED" if is_crit else "YELLOW",
            )
            self.engine.broadcast_to_room(self.room_id, msg)

            # Check if defender died
            if new_hp <= 0:
                await self._handle_death(defender, attacker)
        else:
            msg = colorize(
                f"{attacker.entity_name}'s attack misses {defender.entity_name}!",
                "CYAN",
            )
            self.engine.broadcast_to_room(self.room_id, msg)

    async def _handle_death(self, victim: CombatParticipant, killer: CombatParticipant) -> None:
        """Handle participant death."""
        msg = colorize(
            f"\n*** {victim.entity_name} has been SLAIN by {killer.entity_name}! ***\n",
            "RED",
        )
        self.engine.broadcast_to_room(self.room_id, msg)

        if victim.is_npc:
            # NPC death - mark as dead
            npc = victim._entity_ref
            if npc:
                npc.is_alive = False

                # Award XP to all participants who damaged this NPC
                await self._award_npc_xp(victim, killer)
        else:
            # Player death - handle respawn, XP loss, etc.
            from uuid import UUID

            from waystone.game.systems.death import handle_player_death

            try:
                await handle_player_death(
                    character_id=UUID(victim.entity_id),
                    death_location=self.room_id,
                    engine=self.engine,
                )
            except Exception as e:
                logger.error(
                    "player_death_handling_failed",
                    entity_id=victim.entity_id,
                    error=str(e),
                    exc_info=True,
                )

        # Remove from combat
        await self.remove_participant(victim.entity_id)

    async def _award_npc_xp(self, npc_victim: CombatParticipant, killer: CombatParticipant) -> None:
        """Award XP for NPC death to all attackers.

        Awards XP based on damage dealt:
        - Killer gets bonus XP (40% base)
        - Other attackers share remaining XP based on damage dealt
        """
        from uuid import UUID

        from waystone.database.engine import get_session
        from waystone.game.systems.experience import award_xp

        npc = npc_victim._entity_ref
        if not npc:
            return

        # Calculate total XP for this NPC
        base_xp = 10 * npc.level

        # Find all player participants who damaged this NPC
        attackers = []
        total_damage = 0
        for p in self.participants:
            if not p.is_npc and p.damage_dealt > 0 and not p.fled:
                attackers.append(p)
                total_damage += p.damage_dealt

        if not attackers:
            return

        # Award XP
        async with get_session() as session:
            if len(attackers) == 1:
                # Solo kill - full XP
                await award_xp(UUID(killer.entity_id), base_xp, f"defeating {npc.name}", session)
                xp_msg = colorize(f"{killer.entity_name} gains {base_xp} experience!", "GREEN")
                self.engine.broadcast_to_room(self.room_id, xp_msg)
            else:
                # Group kill - distribute based on damage
                for attacker in attackers:
                    damage_ratio = attacker.damage_dealt / total_damage
                    xp_share = int(base_xp * damage_ratio)
                    if xp_share > 0:
                        await award_xp(
                            UUID(attacker.entity_id),
                            xp_share,
                            f"defeating {npc.name}",
                            session,
                        )
                        xp_msg = colorize(
                            f"{attacker.entity_name} gains {xp_share} experience!",
                            "GREEN",
                        )
                        self.engine.broadcast_to_room(self.room_id, xp_msg)

    async def _npc_auto_action(self, participant: CombatParticipant) -> None:
        """NPC AI - check wimpy, choose target, attack."""
        npc = participant._entity_ref  # NPCInstance
        if not npc:
            return

        # Skip if NPC is dead
        if not npc.is_alive or npc.current_hp <= 0:
            return

        # Check wimpy - flee if HP < 20%
        hp_percent = npc.current_hp / npc.max_hp if npc.max_hp > 0 else 0
        if hp_percent < 0.2 and npc.behavior != "training_dummy":
            await self.attempt_flee(participant)
            return

        # Passive NPCs flee when in combat
        if npc.behavior == "passive":
            await self.attempt_flee(participant)
            return

        # Training dummies don't act
        if npc.behavior == "training_dummy":
            return

        # Aggressive NPCs attack
        if not participant.target_id:
            # Choose target - prioritize last_hit_by
            if npc.last_hit_by:
                for p in self.participants:
                    if p.entity_id == str(npc.last_hit_by) and not p.fled:
                        participant.target_id = p.entity_id
                        break

            # Otherwise pick random player
            if not participant.target_id:
                players = [p for p in self.participants if not p.is_npc and not p.fled]
                if players:
                    participant.target_id = random.choice(players).entity_id

        # Execute attack if has target
        if participant.target_id:
            target = self.get_participant(participant.target_id)
            if target and not target.fled:
                await self._execute_attack(participant, target)

    async def _auto_action(self, participant: CombatParticipant) -> None:
        """Execute automatic combat action for a participant."""
        # Skip if in wait state
        if self._is_in_wait_state(participant):
            return

        # NPC AI
        if participant.is_npc:
            await self._npc_auto_action(participant)
            return

        # Player auto-action
        if not participant.target_id:
            return

        target = self.get_participant(participant.target_id)
        if not target or target.fled:
            return

        await self._execute_attack(participant, target)

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

# Track when entities left combat (entity_id -> datetime when combat ended)
# Used for recall cooldown (30 seconds after combat)
_entity_combat_end_times: dict[str, datetime] = {}


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


# Combat cooldown tracking constants
COMBAT_COOLDOWN_SECONDS = 30  # Cooldown after leaving combat


def record_combat_end(entity_id: str) -> None:
    """Record that an entity has left combat.

    Args:
        entity_id: The entity that left combat
    """
    _entity_combat_end_times[entity_id] = datetime.now()


def get_combat_cooldown_remaining(entity_id: str) -> int:
    """Get remaining combat cooldown for an entity.

    Args:
        entity_id: The entity to check

    Returns:
        Seconds remaining in cooldown, or 0 if no cooldown
    """
    if entity_id not in _entity_combat_end_times:
        return 0

    combat_end = _entity_combat_end_times[entity_id]
    cooldown_expires = combat_end + timedelta(seconds=COMBAT_COOLDOWN_SECONDS)
    remaining = (cooldown_expires - datetime.now()).total_seconds()

    return max(0, int(remaining))


def is_in_combat_cooldown(entity_id: str) -> bool:
    """Check if an entity is in post-combat cooldown.

    Args:
        entity_id: The entity to check

    Returns:
        True if entity cannot recall yet, False if they can
    """
    return get_combat_cooldown_remaining(entity_id) > 0


def clear_combat_cooldown(entity_id: str) -> None:
    """Clear combat cooldown for an entity (used when they die, etc).

    Args:
        entity_id: The entity to clear cooldown for
    """
    _entity_combat_end_times.pop(entity_id, None)
