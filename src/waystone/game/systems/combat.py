"""Turn-based combat system for Waystone MUD."""

import asyncio
import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.cthaeh import get_curse_combat_bonuses
from waystone.network import colorize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


class CombatState(Enum):
    """Combat state machine states."""

    SETUP = "setup"
    IN_PROGRESS = "in_progress"
    ENDED = "ended"


@dataclass
class CombatParticipant:
    """Represents a participant in combat."""

    character_id: str
    character_name: str
    initiative: int
    is_defending: bool = False
    action_taken: bool = False


class Combat:
    """
    Manages a single combat instance.

    Handles initiative, turn order, combat state, and action resolution.
    """

    def __init__(self, room_id: str, engine: "GameEngine") -> None:
        """
        Initialize a combat instance.

        Args:
            room_id: The room where combat is taking place
            engine: The game engine instance
        """
        self.room_id = room_id
        self.engine = engine
        self.state = CombatState.SETUP
        self.participants: list[CombatParticipant] = []
        self.current_turn_index = 0
        self.round_number = 1
        self.turn_timer_task: asyncio.Task[None] | None = None

        logger.info("combat_initialized", room_id=room_id)

    async def add_participant(self, character_id: str) -> None:
        """
        Add a character to combat.

        Args:
            character_id: UUID string of the character
        """
        # Check if already in combat
        if any(p.character_id == character_id for p in self.participants):
            return

        async with get_session() as session:
            # Get character for initiative and name
            from sqlalchemy import select

            result = await session.execute(
                select(Character).where(Character.id == UUID(character_id))
            )
            character = result.scalar_one_or_none()

            if not character:
                return

            # Roll initiative: d20 + DEX modifier
            initiative_roll = self._roll_initiative(character.dexterity)

            participant = CombatParticipant(
                character_id=character_id,
                character_name=character.name,
                initiative=initiative_roll,
            )

            self.participants.append(participant)

            logger.info(
                "participant_added_to_combat",
                character_id=character_id,
                character_name=character.name,
                initiative=initiative_roll,
            )

    def _roll_initiative(self, dexterity: int) -> int:
        """
        Roll initiative for a character.

        Args:
            dexterity: Character's dexterity attribute

        Returns:
            Initiative value (d20 + DEX modifier)
        """
        dex_modifier = (dexterity - 10) // 2
        roll = random.randint(1, 20)
        return roll + dex_modifier

    def start_combat(self) -> None:
        """Start combat by sorting participants by initiative."""
        if self.state != CombatState.SETUP:
            return

        # Sort by initiative (highest first)
        self.participants.sort(key=lambda p: p.initiative, reverse=True)
        self.state = CombatState.IN_PROGRESS
        self.current_turn_index = 0

        logger.info(
            "combat_started",
            room_id=self.room_id,
            participant_count=len(self.participants),
            turn_order=[p.character_name for p in self.participants],
        )

    def get_current_participant(self) -> CombatParticipant | None:
        """
        Get the participant whose turn it currently is.

        Returns:
            Current participant or None if combat not in progress
        """
        if self.state != CombatState.IN_PROGRESS or not self.participants:
            return None

        return self.participants[self.current_turn_index]

    def next_turn(self) -> None:
        """Advance to the next turn."""
        if self.state != CombatState.IN_PROGRESS:
            return

        # Cancel any existing turn timer
        if self.turn_timer_task:
            self.turn_timer_task.cancel()
            self.turn_timer_task = None

        # Reset current participant's action flag
        current = self.get_current_participant()
        if current:
            current.action_taken = False
            current.is_defending = False

        # Move to next participant
        self.current_turn_index += 1

        # If we've gone through all participants, start a new round
        if self.current_turn_index >= len(self.participants):
            self.current_turn_index = 0
            self.round_number += 1
            logger.info(
                "combat_new_round",
                room_id=self.room_id,
                round_number=self.round_number,
            )

    async def start_turn_timer(self, timeout: int = 30) -> None:
        """
        Start a timer for the current turn.

        Args:
            timeout: Seconds before automatic action (default 30)
        """
        if self.turn_timer_task:
            self.turn_timer_task.cancel()

        async def timer() -> None:
            try:
                await asyncio.sleep(timeout)
                # Timeout - perform default action
                await self._handle_turn_timeout()
            except asyncio.CancelledError:
                pass

        self.turn_timer_task = asyncio.create_task(timer())

    async def _handle_turn_timeout(self) -> None:
        """Handle turn timeout by performing a default action."""
        current = self.get_current_participant()
        if not current:
            return

        # Default action: defend
        self.engine.broadcast_to_room(
            self.room_id,
            colorize(
                f"{current.character_name} hesitates and takes a defensive stance.",
                "YELLOW",
            ),
        )

        current.is_defending = True
        current.action_taken = True
        self.next_turn()

        # Notify next participant
        await self._notify_current_turn()

    async def _notify_current_turn(self) -> None:
        """Notify the room whose turn it is."""
        current = self.get_current_participant()
        if not current:
            return

        message = colorize(
            f"\n=== {current.character_name}'s turn ===",
            "CYAN",
        )
        self.engine.broadcast_to_room(self.room_id, message)

    async def perform_attack(
        self,
        attacker_id: str,
        target_id: str,
    ) -> tuple[bool, str]:
        """
        Perform an attack action.

        Args:
            attacker_id: UUID string of attacking character
            target_id: UUID string of target character

        Returns:
            Tuple of (success, message)
        """
        # Verify it's the attacker's turn
        current = self.get_current_participant()
        if not current or current.character_id != attacker_id:
            return False, "It's not your turn!"

        if current.action_taken:
            return False, "You've already taken an action this turn!"

        # Verify target is in combat
        if not any(p.character_id == target_id for p in self.participants):
            return False, "Target is not in combat!"

        async with get_session() as session:
            from sqlalchemy import select

            # Get attacker
            result = await session.execute(
                select(Character).where(Character.id == UUID(attacker_id))
            )
            attacker = result.scalar_one_or_none()

            # Get target
            result = await session.execute(select(Character).where(Character.id == UUID(target_id)))
            target = result.scalar_one_or_none()

            if not attacker or not target:
                return False, "Character not found!"

            # Get curse bonuses for attacker (if any)
            curse_bonuses = get_curse_combat_bonuses(attacker)
            crit_bonus = curse_bonuses.get("crit_bonus", 0)
            damage_bonus = curse_bonuses.get("damage_bonus", 0)

            # Calculate to-hit: d20 + DEX modifier
            to_hit_roll = random.randint(1, 20)
            dex_modifier = (attacker.dexterity - 10) // 2
            # Crit on natural 20 OR curse crit bonus
            is_critical = to_hit_roll == 20 or (crit_bonus > 0 and random.random() < crit_bonus)
            is_fumble = to_hit_roll == 1

            # Calculate defense: 10 + DEX modifier (+5 if defending)
            target_dex_mod = (target.dexterity - 10) // 2
            target_defense = 10 + target_dex_mod

            # Check if target is defending
            target_participant = next(
                (p for p in self.participants if p.character_id == target_id),
                None,
            )
            if target_participant and target_participant.is_defending:
                target_defense += 5

            # Check hit (fumble always misses, critical always hits)
            final_roll = to_hit_roll + dex_modifier
            if is_fumble or (final_roll < target_defense and not is_critical):
                # Miss
                miss_msg = colorize(
                    f"{attacker.name} attacks {target.name} but misses! "
                    f"(Rolled {final_roll} vs Defense {target_defense})",
                    "YELLOW",
                )
                self.engine.broadcast_to_room(self.room_id, miss_msg)

                current.action_taken = True
                self.next_turn()
                await self._notify_current_turn()

                return True, "Your attack missed!"

            # Hit - calculate damage
            # Base damage 1d6 + STR modifier (2x dice on critical)
            str_modifier = (attacker.strength - 10) // 2
            damage_roll = random.randint(1, 6)
            if is_critical:
                damage_roll += random.randint(1, 6)  # Double dice on crit
            base_damage = max(1, damage_roll + str_modifier)
            # Apply curse damage bonus (+15% if cursed)
            total_damage = int(base_damage * (1 + damage_bonus))
            total_damage = max(1, total_damage)  # Minimum 1 damage

            # Apply damage
            target.current_hp = max(0, target.current_hp - total_damage)
            await session.commit()

            # Broadcast hit message
            if is_critical:
                hit_msg = colorize(
                    f"CRITICAL HIT! {attacker.name} hits {target.name} for {total_damage} damage! "
                    f"({target.name}: {target.current_hp}/{target.max_hp} HP)",
                    "YELLOW",
                )
            else:
                hit_msg = colorize(
                    f"{attacker.name} hits {target.name} for {total_damage} damage! "
                    f"({target.name}: {target.current_hp}/{target.max_hp} HP)",
                    "RED",
                )
            self.engine.broadcast_to_room(self.room_id, hit_msg)

            # Check for death
            if target.current_hp <= 0:
                await self._handle_character_death(target, session)

            current.action_taken = True
            self.next_turn()
            await self._notify_current_turn()

            return True, f"You hit {target.name} for {total_damage} damage!"

    async def _handle_character_death(
        self,
        character: Character,
        session: "AsyncSession",
    ) -> None:
        """
        Handle a character's death in combat.

        Args:
            character: The defeated character
            session: Database session for updates
        """
        from waystone.game.systems.death import handle_player_death

        death_msg = colorize(
            f"\n{character.name} has been defeated!",
            "RED",
        )
        self.engine.broadcast_to_room(self.room_id, death_msg)

        # Remove from combat
        self.participants = [p for p in self.participants if p.character_id != str(character.id)]

        # Handle player death with full death mechanics
        try:
            await handle_player_death(
                character_id=character.id,
                death_location=self.room_id,
                engine=self.engine,
                session=session,
            )
        except Exception as e:
            logger.error(
                "player_death_handling_failed",
                character_id=str(character.id),
                error=str(e),
                exc_info=True,
            )
            # Fallback: restore HP to 1 if death handler fails
            character.current_hp = 1
            await session.commit()

        # Check if combat should end
        if len(self.participants) <= 1:
            await self._end_combat()

    async def perform_defend(self, character_id: str) -> tuple[bool, str]:
        """
        Perform a defend action.

        Args:
            character_id: UUID string of the character

        Returns:
            Tuple of (success, message)
        """
        current = self.get_current_participant()
        if not current or current.character_id != character_id:
            return False, "It's not your turn!"

        if current.action_taken:
            return False, "You've already taken an action this turn!"

        current.is_defending = True
        current.action_taken = True

        defend_msg = colorize(
            f"{current.character_name} takes a defensive stance! (+5 Defense)",
            "CYAN",
        )
        self.engine.broadcast_to_room(self.room_id, defend_msg)

        self.next_turn()
        await self._notify_current_turn()

        return True, "You take a defensive stance, gaining +5 Defense until your next turn."

    async def attempt_flee(self, character_id: str) -> tuple[bool, str]:
        """
        Attempt to flee from combat.

        Args:
            character_id: UUID string of the character

        Returns:
            Tuple of (success, message)
        """
        current = self.get_current_participant()
        if not current or current.character_id != character_id:
            return False, "It's not your turn!"

        if current.action_taken:
            return False, "You've already taken an action this turn!"

        async with get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Character).where(Character.id == UUID(character_id))
            )
            character = result.scalar_one_or_none()

            if not character:
                return False, "Character not found!"

            # Flee chance: d20 + DEX modifier vs DC 12
            flee_roll = random.randint(1, 20)
            dex_modifier = (character.dexterity - 10) // 2
            total_roll = flee_roll + dex_modifier

            if total_roll >= 12:
                # Success
                flee_msg = colorize(
                    f"{character.name} flees from combat!",
                    "YELLOW",
                )
                self.engine.broadcast_to_room(self.room_id, flee_msg)

                # Remove from combat
                self.participants = [p for p in self.participants if p.character_id != character_id]

                # Check if combat should end
                if len(self.participants) <= 1:
                    await self._end_combat()
                else:
                    self.next_turn()
                    await self._notify_current_turn()

                return True, "You successfully flee from combat!"
            else:
                # Failure
                fail_msg = colorize(
                    f"{character.name} tries to flee but fails! (Rolled {total_roll} vs DC 12)",
                    "YELLOW",
                )
                self.engine.broadcast_to_room(self.room_id, fail_msg)

                current.action_taken = True
                self.next_turn()
                await self._notify_current_turn()

                return True, "You fail to escape!"

    async def _end_combat(self) -> None:
        """End the combat."""
        if self.state == CombatState.ENDED:
            return

        self.state = CombatState.ENDED

        # Cancel turn timer
        if self.turn_timer_task:
            self.turn_timer_task.cancel()
            self.turn_timer_task = None

        end_msg = colorize("\n=== Combat has ended ===\n", "GREEN")
        self.engine.broadcast_to_room(self.room_id, end_msg)

        logger.info("combat_ended", room_id=self.room_id)

    def is_character_in_combat(self, character_id: str) -> bool:
        """
        Check if a character is in this combat.

        Args:
            character_id: UUID string of the character

        Returns:
            True if character is in combat, False otherwise
        """
        return any(p.character_id == character_id for p in self.participants)

    def get_combat_status(self) -> str:
        """
        Get a formatted status of the combat.

        Returns:
            Formatted combat status string
        """
        if self.state == CombatState.SETUP:
            return colorize("Combat is being set up...", "YELLOW")

        if self.state == CombatState.ENDED:
            return colorize("Combat has ended.", "GREEN")

        lines = [
            colorize(f"\n=== Combat Status (Round {self.round_number}) ===", "CYAN"),
        ]

        current = self.get_current_participant()
        for participant in self.participants:
            status = ">>> " if participant == current else "    "
            defending = " [DEFENDING]" if participant.is_defending else ""
            lines.append(
                f"{status}{colorize(participant.character_name, 'YELLOW')}"
                f" (Initiative: {participant.initiative}){defending}"
            )

        return "\n".join(lines)
