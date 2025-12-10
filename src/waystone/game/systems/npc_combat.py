"""NPC combat system for Waystone MUD.

Handles combat between players and NPCs, including:
- NPC instance tracking with HP
- Attack resolution
- XP rewards
- Training dummy special handling
- NPC death and respawn
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.cthaeh import get_curse_combat_bonuses
from waystone.game.systems.experience import award_xp
from waystone.network import colorize

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine
    from waystone.game.world.npc_loader import NPCTemplate

logger = structlog.get_logger(__name__)


@dataclass
class NPCInstance:
    """Runtime NPC instance with combat state."""

    id: str  # Unique instance ID
    template_id: str  # Reference to NPCTemplate
    room_id: str  # Current room
    current_hp: int  # Current HP
    max_hp: int  # Max HP from template
    name: str  # Display name
    level: int  # Level from template
    attributes: dict[str, int] = field(default_factory=dict)  # STR, DEX, etc.
    behavior: str = "passive"  # aggressive, passive, training_dummy
    is_alive: bool = True
    last_hit_by: str | None = None  # Character ID who last hit this NPC
    spawned_at: datetime = field(default_factory=datetime.now)
    keywords: list[str] = field(default_factory=list)  # Keywords for player targeting
    short_description: str = ""  # Used in action messages
    long_description: str = ""  # Shown in room descriptions
    equipment: dict[str, str] = field(default_factory=dict)  # Equipped items by slot
    inventory: list[str] = field(default_factory=list)  # Items this NPC carries


# Global NPC instance tracking: room_id -> {instance_id: NPCInstance}
_npc_instances: dict[str, dict[str, NPCInstance]] = {}

# Track pending respawns: (respawn_time, template_id, room_id)
_pending_respawns: list[tuple[datetime, str, str]] = []


def spawn_npc(template: "NPCTemplate", room_id: str) -> NPCInstance:
    """
    Spawn an NPC instance from a template.

    Args:
        template: The NPC template
        room_id: Room to spawn in

    Returns:
        New NPC instance
    """
    instance = NPCInstance(
        id=f"{template.id}_{uuid4().hex[:8]}",
        template_id=template.id,
        room_id=room_id,
        current_hp=template.max_hp,
        max_hp=template.max_hp,
        name=template.name,
        level=template.level,
        attributes=dict(template.attributes),
        behavior=template.behavior,
        keywords=list(template.keywords) if template.keywords else [],
        short_description=template.short_description or template.name,
        long_description=template.long_description or f"{template.name} is here.",
        equipment=dict(template.equipment) if template.equipment else {},
        inventory=list(template.inventory) if template.inventory else [],
    )

    if room_id not in _npc_instances:
        _npc_instances[room_id] = {}

    _npc_instances[room_id][instance.id] = instance

    logger.debug(
        "npc_spawned",
        npc_id=instance.id,
        template=template.id,
        room_id=room_id,
    )

    return instance


def get_npcs_in_room(room_id: str) -> list[NPCInstance]:
    """Get all alive NPC instances in a room."""
    if room_id not in _npc_instances:
        return []

    return [npc for npc in _npc_instances[room_id].values() if npc.is_alive]


def find_npc_by_name(room_id: str, name: str) -> NPCInstance | None:
    """
    Find an NPC in a room by name (partial match).

    Args:
        room_id: Room to search
        name: Name to search for (case insensitive)

    Returns:
        Matching NPC instance or None
    """
    name_lower = name.lower()

    for npc in get_npcs_in_room(room_id):
        if name_lower in npc.name.lower():
            return npc

    return None


def get_npc_defense(npc: NPCInstance) -> int:
    """Calculate NPC's defense value."""
    dex = npc.attributes.get("dexterity", 10)
    dex_mod = (dex - 10) // 2
    return 10 + dex_mod


async def attack_npc(
    attacker_id: UUID,
    npc: NPCInstance,
    engine: "GameEngine",
) -> tuple[bool, str, int]:
    """
    Attack an NPC.

    Args:
        attacker_id: UUID of attacking character
        npc: Target NPC instance
        engine: Game engine

    Returns:
        Tuple of (hit, message, damage)
    """
    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(select(Character).where(Character.id == attacker_id))
        attacker = result.scalar_one_or_none()

        if not attacker:
            return False, "Character not found!", 0

        # Get curse bonuses (if any)
        curse_bonuses = get_curse_combat_bonuses(attacker)
        crit_bonus = curse_bonuses.get("crit_bonus", 0)
        damage_bonus = curse_bonuses.get("damage_bonus", 0)

        # Calculate to-hit: d20 + DEX modifier
        to_hit_roll = random.randint(1, 20)
        dex_mod = (attacker.dexterity - 10) // 2
        # Crit on natural 20 OR curse crit bonus (10% extra chance if cursed)
        is_critical = to_hit_roll == 20 or (crit_bonus > 0 and random.random() < crit_bonus)
        is_fumble = to_hit_roll == 1

        # NPC defense
        npc_defense = get_npc_defense(npc)

        # Check hit (fumble always misses, critical always hits)
        final_roll = to_hit_roll + dex_mod

        if is_fumble or (final_roll < npc_defense and not is_critical):
            # Miss - varied messages
            miss_msgs = [
                f"You swing at {npc.name} but miss!",
                f"Your attack goes wide, missing {npc.name}.",
                f"{npc.name} dodges your attack!",
                f"You lunge at {npc.name} but strike only air.",
            ]
            if is_fumble:
                miss_msg = colorize("FUMBLE! ", "RED") + random.choice(miss_msgs)
            else:
                miss_msg = random.choice(miss_msgs)
            return False, f"{miss_msg} (Roll: {final_roll} vs AC {npc_defense})", 0

        # Hit - calculate damage: 1d6 + STR modifier (2x for critical)
        str_mod = (attacker.strength - 10) // 2
        damage_roll = random.randint(1, 6)
        if is_critical:
            damage_roll += random.randint(1, 6)  # Double dice on crit
        base_damage = max(1, damage_roll + str_mod)
        # Apply curse damage bonus (+15% if cursed)
        total_damage = int(base_damage * (1 + damage_bonus))
        total_damage = max(1, total_damage)  # Minimum 1 damage

        # Apply damage
        npc.current_hp = max(0, npc.current_hp - total_damage)
        npc.last_hit_by = str(attacker_id)

        # Varied hit messages based on damage
        if is_critical:
            hit_desc = (
                colorize("CRITICAL HIT! ", "YELLOW")
                + f"You strike {npc.name} with devastating force"
            )
        elif total_damage >= 8:
            hit_desc = f"You land a powerful blow on {npc.name}"
        elif total_damage >= 5:
            hit_desc = f"You strike {npc.name} solidly"
        elif total_damage >= 3:
            hit_desc = f"You hit {npc.name}"
        else:
            hit_desc = f"You land a glancing blow on {npc.name}"

        # NPC condition based on HP percentage
        hp_pct = (npc.current_hp / npc.max_hp) * 100 if npc.max_hp > 0 else 0
        if hp_pct >= 75:
            condition = "looks healthy"
        elif hp_pct >= 50:
            condition = "has some wounds"
        elif hp_pct >= 25:
            condition = "is badly wounded"
        elif hp_pct > 0:
            condition = "is near death"
        else:
            condition = "collapses"

        hit_msg = (
            f"{hit_desc} for {colorize(str(total_damage), 'RED')} damage!\n"
            f"  {npc.name} {condition}. ({npc.current_hp}/{npc.max_hp} HP)"
        )

        # Check for death
        if npc.current_hp <= 0:
            if npc.behavior == "training_dummy":
                # Training dummy resets instead of dying
                npc.current_hp = npc.max_hp
                return (
                    True,
                    f"{hit_msg}\n"
                    f"{colorize('The training dummy resets to its starting position.', 'YELLOW')}\n"
                    f"{colorize('+5 XP for practice!', 'GREEN')}",
                    total_damage,
                )
            else:
                # NPC dies
                await handle_npc_death(npc, attacker, engine, session)
                return True, hit_msg, total_damage

        return True, hit_msg, total_damage


async def handle_npc_death(
    npc: NPCInstance,
    killer: Character,
    engine: "GameEngine",
    session: Any,
) -> None:
    """
    Handle NPC death.

    Args:
        npc: The dead NPC
        killer: Character who killed it
        engine: Game engine
        session: Database session
    """
    npc.is_alive = False

    # Calculate XP reward: base 10 * level * (1 + level difference bonus)
    level_diff = max(0, npc.level - killer.level)
    base_xp = 10 * npc.level
    xp_bonus = 1 + (level_diff * 0.1)  # 10% more XP per level above player
    xp_reward = int(base_xp * xp_bonus)

    # Award XP
    await award_xp(killer.id, xp_reward, f"defeating {npc.name}", session)

    # Broadcast death
    death_msg = colorize(
        f"\n{npc.name} has been defeated!",
        "RED",
    )
    engine.broadcast_to_room(npc.room_id, death_msg)

    xp_msg = colorize(
        f"{killer.name} gains {xp_reward} experience!",
        "GREEN",
    )
    engine.broadcast_to_room(npc.room_id, xp_msg)

    # Remove from room
    if npc.room_id in _npc_instances and npc.id in _npc_instances[npc.room_id]:
        del _npc_instances[npc.room_id][npc.id]

    # Schedule respawn (if template has respawn time)
    template = engine.npc_templates.get(npc.template_id)
    if template and template.respawn_time > 0:
        from datetime import timedelta

        respawn_at = datetime.now() + timedelta(seconds=template.respawn_time)
        _pending_respawns.append((respawn_at, npc.template_id, npc.room_id))

        logger.info(
            "npc_respawn_scheduled",
            template_id=npc.template_id,
            room_id=npc.room_id,
            respawn_at=respawn_at.isoformat(),
        )


async def check_npc_respawns(engine: "GameEngine") -> int:
    """
    Check for and process NPC respawns.

    Args:
        engine: Game engine

    Returns:
        Number of NPCs respawned
    """
    now = datetime.now()
    respawned = 0

    # Process pending respawns
    still_pending = []
    for respawn_at, template_id, room_id in _pending_respawns:
        if now >= respawn_at:
            # Time to respawn
            template = engine.npc_templates.get(template_id)
            if template:
                spawn_npc(template, room_id)
                respawned += 1

                logger.debug(
                    "npc_respawned",
                    template_id=template_id,
                    room_id=room_id,
                )
        else:
            still_pending.append((respawn_at, template_id, room_id))

    _pending_respawns.clear()
    _pending_respawns.extend(still_pending)

    return respawned


def initialize_room_npcs(engine: "GameEngine") -> int:
    """
    Initialize NPC instances for all spawned NPCs.

    Should be called after engine.spawn_npcs().

    Args:
        engine: Game engine

    Returns:
        Total NPCs spawned
    """
    total = 0

    for room_id, template_ids in engine.room_npcs.items():
        for template_id in template_ids:
            template = engine.npc_templates.get(template_id)
            if template:
                spawn_npc(template, room_id)
                total += 1

    logger.info("npc_instances_initialized", total=total)
    return total


def reset_all_npcs() -> None:
    """Reset all NPC instances (for testing)."""
    _npc_instances.clear()
    _pending_respawns.clear()
