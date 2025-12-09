"""Death and respawn mechanics for Waystone MUD."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.experience import XP_COMBAT_KILL_BASE, award_xp
from waystone.game.systems.loot import drop_loot_to_room, generate_loot
from waystone.network import colorize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


# Death penalty constants
PLAYER_DEATH_XP_PENALTY = 0.1  # Lose 10% of current level's XP
PLAYER_DEATH_WEAKENED_DURATION = 300  # 5 minutes in seconds
PLAYER_DEATH_STAT_PENALTY = 0.2  # 20% stat reduction while weakened
PLAYER_RESPAWN_ROOM = "university_main_hall"  # Safe respawn location


@dataclass
class NPCDeathInfo:
    """Information about a dead NPC for respawn tracking."""

    npc_id: str
    npc_name: str
    level: int
    original_room_id: str
    death_time: datetime
    respawn_time: int  # Seconds until respawn
    max_hp: int
    attributes: dict[str, int]
    loot_table_id: str | None
    behavior: str


@dataclass
class PlayerDeathInfo:
    """Information about player death and penalties."""

    character_id: UUID
    death_location: str
    xp_lost: int
    weakened_until: datetime


# Global NPC respawn tracking
_dead_npcs: dict[str, NPCDeathInfo] = {}


async def handle_npc_death(
    npc_id: str,
    npc_name: str,
    npc_level: int,
    room_id: str,
    killer_id: str | None,
    engine: "GameEngine",
    loot_table_id: str | None = None,
    respawn_time: int = 0,
    max_hp: int = 20,
    attributes: dict[str, int] | None = None,
    behavior: str = "aggressive",
) -> None:
    """
    Handle NPC death, including XP award, loot generation, and respawn scheduling.

    Args:
        npc_id: Unique identifier for the NPC
        npc_name: Display name of the NPC
        npc_level: Level of the NPC
        room_id: Room where death occurred
        killer_id: Character ID of the killer (None if environmental death)
        engine: Game engine instance for broadcasting
        loot_table_id: Optional loot table ID for generating loot
        respawn_time: Seconds until respawn (0 = no respawn)
        max_hp: Max HP for respawn
        attributes: NPC attributes for respawn
        behavior: NPC behavior type for respawn
    """
    logger.info(
        "npc_death_started",
        npc_id=npc_id,
        npc_name=npc_name,
        npc_level=npc_level,
        room_id=room_id,
        killer_id=killer_id,
        loot_table_id=loot_table_id,
        respawn_time=respawn_time,
    )

    # Award XP to killer if present
    if killer_id:
        xp_amount = XP_COMBAT_KILL_BASE * npc_level

        try:
            killer_uuid = UUID(killer_id)
            new_xp, leveled_up = await award_xp(
                character_id=killer_uuid,
                amount=xp_amount,
                source=f"npc_kill_{npc_id}",
            )

            # Get killer's session to send notifications
            async with get_session() as session:
                result = await session.execute(select(Character).where(Character.id == killer_uuid))
                killer = result.scalar_one_or_none()

                if killer:
                    killer_session = engine.character_to_session.get(killer_id)
                    if killer_session:
                        xp_msg = colorize(
                            f"\nYou gain {xp_amount} experience! (Total: {new_xp} XP)",
                            "CYAN",
                        )
                        await killer_session.connection.send_line(xp_msg)

                        if leveled_up:
                            level_msg = colorize(
                                f"\n*** LEVEL UP! You are now level {killer.level}! ***",
                                "YELLOW",
                            )
                            await killer_session.connection.send_line(level_msg)

            logger.info(
                "npc_death_xp_awarded",
                npc_id=npc_id,
                killer_id=killer_id,
                xp_amount=xp_amount,
                leveled_up=leveled_up,
            )

        except Exception as e:
            logger.error(
                "npc_death_xp_award_failed",
                npc_id=npc_id,
                killer_id=killer_id,
                error=str(e),
                exc_info=True,
            )

    # Generate and drop loot
    if loot_table_id:
        try:
            loot_items = await generate_loot(loot_table_id)

            if loot_items:
                dropped_items = await drop_loot_to_room(room_id, loot_items)

                # Broadcast loot message
                loot_names = [f"{qty}x {item_id}" for item_id, qty in loot_items]
                loot_msg = colorize(
                    f"\n{npc_name} drops: {', '.join(loot_names)}",
                    "YELLOW",
                )
                engine.broadcast_to_room(room_id, loot_msg)

                logger.info(
                    "npc_death_loot_dropped",
                    npc_id=npc_id,
                    room_id=room_id,
                    loot_count=len(dropped_items),
                    loot_items=loot_items,
                )

        except Exception as e:
            logger.error(
                "npc_death_loot_generation_failed",
                npc_id=npc_id,
                loot_table_id=loot_table_id,
                error=str(e),
                exc_info=True,
            )

    # Schedule respawn if applicable
    if respawn_time > 0:
        npc_death_info = NPCDeathInfo(
            npc_id=npc_id,
            npc_name=npc_name,
            level=npc_level,
            original_room_id=room_id,
            death_time=datetime.now(),
            respawn_time=respawn_time,
            max_hp=max_hp,
            attributes=attributes or {},
            loot_table_id=loot_table_id,
            behavior=behavior,
        )

        _dead_npcs[npc_id] = npc_death_info

        logger.info(
            "npc_death_respawn_scheduled",
            npc_id=npc_id,
            respawn_in_seconds=respawn_time,
        )

    logger.info(
        "npc_death_completed",
        npc_id=npc_id,
    )


async def handle_player_death(
    character_id: UUID,
    death_location: str,
    engine: "GameEngine",
    session: "AsyncSession | None" = None,
) -> PlayerDeathInfo:
    """
    Handle player character death with XP penalty and respawn.

    Death penalties:
    - Lose 10% of current level's XP (cannot delevel)
    - Respawn at safe location (University main hall)
    - Apply "weakened" status for 5 minutes (-20% stats)
    - Optional: Drop inventory (currently disabled)

    Args:
        character_id: UUID of the character who died
        death_location: Room ID where death occurred
        engine: Game engine instance for broadcasting
        session: Optional existing database session

    Returns:
        PlayerDeathInfo with death details and penalties
    """
    logger.info(
        "player_death_started",
        character_id=str(character_id),
        death_location=death_location,
    )

    should_close = session is None

    try:
        if session is None:
            session = get_session()
            await session.__aenter__()

        # Get character
        result = await session.execute(select(Character).where(Character.id == character_id))
        character = result.scalar_one_or_none()

        if not character:
            raise ValueError(f"Character {character_id} not found")

        # Calculate XP penalty (10% of current level's XP)
        from waystone.game.systems.experience import xp_for_level, xp_for_next_level

        current_level_xp = xp_for_level(character.level)
        next_level_xp = xp_for_next_level(character.level)

        # Lose 10% of the XP needed for current level
        xp_loss = int(next_level_xp * PLAYER_DEATH_XP_PENALTY)

        # Don't drop below current level's minimum
        new_xp = max(current_level_xp, character.experience - xp_loss)
        actual_xp_lost = character.experience - new_xp

        character.experience = new_xp

        # Respawn at safe location with 1 HP
        old_room = character.current_room_id
        character.current_room_id = PLAYER_RESPAWN_ROOM
        character.current_hp = 1

        # Apply weakened status (tracked via timestamp)
        weakened_until = datetime.now() + timedelta(seconds=PLAYER_DEATH_WEAKENED_DURATION)

        # TODO: Store weakened status in character model
        # For now, we'll just log it and implement status tracking later

        await session.commit()

        # Update room tracking
        old_room_obj = engine.world.get(old_room)
        if old_room_obj:
            old_room_obj.remove_player(str(character_id))

        new_room_obj = engine.world.get(PLAYER_RESPAWN_ROOM)
        if new_room_obj:
            new_room_obj.add_player(str(character_id))

        # Broadcast death message to old room
        death_msg = colorize(
            f"\n{character.name} falls in battle and fades away...",
            "RED",
        )
        engine.broadcast_to_room(old_room, death_msg)

        # Broadcast respawn message to new room
        respawn_msg = colorize(
            f"\n{character.name} appears in a flash of light, looking weakened and battered.",
            "YELLOW",
        )
        engine.broadcast_to_room(
            PLAYER_RESPAWN_ROOM,
            respawn_msg,
            exclude=engine.character_to_session.get(str(character_id)).id
            if str(character_id) in engine.character_to_session
            else None,
        )

        # Send death message to player
        player_session = engine.character_to_session.get(str(character_id))
        if player_session:
            player_death_msg = colorize(
                f"\n{'=' * 60}\n"
                f"You have died!\n\n"
                f"XP Lost: -{actual_xp_lost} ({character.experience}/{xp_for_level(character.level + 1)} XP)\n"
                f"You awaken at {new_room_obj.name if new_room_obj else PLAYER_RESPAWN_ROOM}\n"
                f"You feel weakened... (-20% stats for {PLAYER_DEATH_WEAKENED_DURATION // 60} minutes)\n"
                f"{'=' * 60}",
                "RED",
            )
            await player_session.connection.send_line(player_death_msg)

        death_info = PlayerDeathInfo(
            character_id=character_id,
            death_location=death_location,
            xp_lost=actual_xp_lost,
            weakened_until=weakened_until,
        )

        logger.info(
            "player_death_completed",
            character_id=str(character_id),
            character_name=character.name,
            xp_lost=actual_xp_lost,
            respawn_location=PLAYER_RESPAWN_ROOM,
        )

        return death_info

    finally:
        if should_close and session:
            await session.__aexit__(None, None, None)


async def check_respawns(engine: "GameEngine") -> int:
    """
    Check for NPCs ready to respawn and respawn them.

    This should be called periodically from the game engine's tick loop.

    Args:
        engine: Game engine instance

    Returns:
        Number of NPCs respawned
    """
    now = datetime.now()
    respawned_count = 0

    # Check each dead NPC
    to_remove = []

    for npc_id, death_info in _dead_npcs.items():
        # Check if respawn time has elapsed
        time_since_death = (now - death_info.death_time).total_seconds()

        if time_since_death >= death_info.respawn_time:
            # Respawn NPC
            try:
                # TODO: When NPC system is implemented, create new NPC instance here
                # For now, just log and remove from tracking

                logger.info(
                    "npc_respawned",
                    npc_id=npc_id,
                    npc_name=death_info.npc_name,
                    room_id=death_info.original_room_id,
                    time_dead=int(time_since_death),
                )

                # Broadcast respawn message
                respawn_msg = colorize(
                    f"\n{death_info.npc_name} emerges from the shadows.",
                    "YELLOW",
                )
                engine.broadcast_to_room(death_info.original_room_id, respawn_msg)

                to_remove.append(npc_id)
                respawned_count += 1

            except Exception as e:
                logger.error(
                    "npc_respawn_failed",
                    npc_id=npc_id,
                    error=str(e),
                    exc_info=True,
                )

    # Remove respawned NPCs from tracking
    for npc_id in to_remove:
        del _dead_npcs[npc_id]

    if respawned_count > 0:
        logger.info(
            "respawn_check_completed",
            respawned_count=respawned_count,
        )

    return respawned_count


def get_pending_respawns() -> list[NPCDeathInfo]:
    """
    Get list of all NPCs pending respawn.

    Returns:
        List of NPCDeathInfo objects for dead NPCs
    """
    return list(_dead_npcs.values())


def clear_respawn_queue() -> None:
    """Clear all pending respawns. Useful for testing."""
    global _dead_npcs
    _dead_npcs.clear()
    logger.info("respawn_queue_cleared")
