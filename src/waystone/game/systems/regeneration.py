"""HP and resource regeneration system for Waystone MUD.

Handles passive regeneration of HP (and future resources like mana/stamina)
on the game tick. Regeneration rates are affected by:
- Position (resting/sleeping regenerates faster)
- Combat status (no regen while in combat)
- Weakened status (reduced regen after death)
- Constitution modifier
"""

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, update

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.unified_combat import get_combat_for_entity

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)

# Regeneration constants
BASE_HP_REGEN_PERCENT = 0.05  # 5% of max HP per tick (30 seconds)
RESTING_REGEN_MULTIPLIER = 2.0  # 2x regen when resting
SLEEPING_REGEN_MULTIPLIER = 4.0  # 4x regen when sleeping
COMBAT_REGEN_MULTIPLIER = 0.0  # No regen in combat
WEAKENED_REGEN_MULTIPLIER = 0.5  # 50% regen when weakened


async def regenerate_all_players(engine: "GameEngine") -> int:
    """
    Regenerate HP for all online players not in combat.

    Called every tick (30 seconds) from the game engine's periodic loop.

    Args:
        engine: Game engine instance for accessing sessions and combat state

    Returns:
        Number of players who regenerated HP
    """
    regenerated_count = 0

    # Get all online character IDs
    online_character_ids = [
        session.character_id
        for session in engine.character_to_session.values()
        if session.character_id
    ]

    if not online_character_ids:
        return 0

    async with get_session() as session:
        # Fetch all online characters who need healing
        from uuid import UUID

        character_uuids = [UUID(cid) for cid in online_character_ids]

        result = await session.execute(
            select(Character).where(
                Character.id.in_(character_uuids),
                Character.current_hp < Character.max_hp,  # Only heal if damaged
            )
        )
        characters = result.scalars().all()

        for character in characters:
            char_id_str = str(character.id)

            # Skip if in combat
            combat = get_combat_for_entity(char_id_str)
            if combat:
                logger.debug(
                    "regen_skipped_in_combat",
                    character_id=char_id_str,
                    character_name=character.name,
                )
                continue

            # Calculate regeneration amount
            regen_amount = calculate_regen_amount(character)

            if regen_amount > 0:
                old_hp = character.current_hp
                new_hp = min(character.max_hp, character.current_hp + regen_amount)

                # Update HP in database
                await session.execute(
                    update(Character).where(Character.id == character.id).values(current_hp=new_hp)
                )

                regenerated_count += 1

                logger.debug(
                    "player_regenerated",
                    character_id=char_id_str,
                    character_name=character.name,
                    old_hp=old_hp,
                    new_hp=new_hp,
                    regen_amount=regen_amount,
                )

        await session.commit()

    if regenerated_count > 0:
        logger.info(
            "regeneration_tick_completed",
            players_healed=regenerated_count,
        )

    return regenerated_count


def calculate_regen_amount(character: Character) -> int:
    """
    Calculate HP regeneration amount for a character.

    Base regen is 5% of max HP per tick, modified by:
    - CON modifier: +1 HP per 2 CON above 10
    - Position: resting (2x), sleeping (4x)
    - Weakened status: 50% regen

    Args:
        character: The character to calculate regen for

    Returns:
        HP to regenerate (minimum 1 if damaged)
    """
    # Base regen: 5% of max HP
    base_regen = int(character.max_hp * BASE_HP_REGEN_PERCENT)

    # CON modifier bonus: +1 HP per 2 CON above 10
    con_bonus = max(0, (character.constitution - 10) // 2)

    total_regen = base_regen + con_bonus

    # TODO: Apply position multipliers when rest/sleep system exists
    # TODO: Apply weakened status penalty when status system exists

    # Minimum of 1 HP if damaged
    return max(1, total_regen)


async def regenerate_npcs(engine: "GameEngine") -> int:
    """
    Regenerate HP for NPCs not in combat.

    NPCs regenerate faster than players (10% per tick) to ensure
    they're ready for the next fight.

    Args:
        engine: Game engine instance

    Returns:
        Number of NPCs who regenerated HP
    """
    from waystone.game.systems.npc_combat import get_all_npc_instances

    regenerated_count = 0
    npc_instances = get_all_npc_instances()

    for _room_id, npcs in npc_instances.items():
        for npc in npcs:
            if not npc.is_alive:
                continue

            if npc.current_hp >= npc.max_hp:
                continue

            # Skip if in combat
            combat = get_combat_for_entity(npc.instance_id)
            if combat:
                continue

            # NPCs regen 10% per tick
            regen_amount = max(1, int(npc.max_hp * 0.10))
            npc.current_hp = min(npc.max_hp, npc.current_hp + regen_amount)
            regenerated_count += 1

    if regenerated_count > 0:
        logger.debug(
            "npc_regeneration_completed",
            npcs_healed=regenerated_count,
        )

    return regenerated_count
