"""Cthaeh curse system for Waystone MUD.

Handles:
- The Cthaeh's curse/pact mechanics
- Combat buffs for cursed players
- Daily bidding (kill targets) system
- Curse status tracking
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm.attributes import flag_modified

if TYPE_CHECKING:
    from waystone.database.models import Character
    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)

# Curse buff values
CURSE_DAMAGE_BONUS = 0.15  # +15% damage
CURSE_CRIT_BONUS = 0.10  # +10% crit chance
CURSE_STAT_BONUS = 3  # +3 to STR, DEX, CON

# Bidding settings
BIDDING_COOLDOWN_HOURS = 20  # Minimum hours between biddings
BIDDING_DURATION_HOURS = 24  # Hours to complete a bidding
BIDDING_XP_BONUS = 0.50  # +50% bonus XP for kill
BIDDING_FAILURE_DEBUFF_HOURS = 4  # Hours of debuff after failure
BIDDING_FAILURE_STAT_PENALTY = 0.10  # -10% all stats during debuff

# Possible NPC targets for bidding (weighted by difficulty)
BIDDING_NPC_TARGETS = [
    # Easy targets
    {"id": "sewer_rat", "name": "a sewer rat", "weight": 30},
    {"id": "student", "name": "a University student", "weight": 20},
    # Medium targets
    {"id": "bandit", "name": "a bandit on the north road", "weight": 25},
    {"id": "training_dummy", "name": "a training dummy", "weight": 15},
    # Hard targets (Masters - symbolic, they're invulnerable)
    {"id": "scriv", "name": "a scriv in the Archives", "weight": 10},
]


@dataclass
class CthaehStatus:
    """Complete Cthaeh curse status for a character."""

    character_id: str
    cursed: bool = False
    curse_accepted_at: datetime | None = None
    last_bidding_time: datetime | None = None
    current_target: str | None = None  # NPC id or player name
    target_type: str = "npc"  # "npc" or "player"
    target_display_name: str | None = None
    target_expires_at: datetime | None = None
    completed_biddings: int = 0
    failed_biddings: int = 0
    failure_debuff_until: datetime | None = None

    def is_cursed(self) -> bool:
        """Check if character is cursed."""
        return self.cursed

    def has_active_bidding(self) -> bool:
        """Check if there's an active bidding target."""
        if not self.current_target:
            return False
        if not self.target_expires_at:
            return False
        return datetime.now(UTC) < self.target_expires_at

    def is_bidding_expired(self) -> bool:
        """Check if current bidding has expired (failed)."""
        if not self.current_target:
            return False
        if not self.target_expires_at:
            return False
        return datetime.now(UTC) >= self.target_expires_at

    def can_receive_new_bidding(self) -> bool:
        """Check if character can receive a new bidding."""
        if not self.cursed:
            return False
        if self.has_active_bidding():
            return False
        if not self.last_bidding_time:
            return True
        cooldown_end = self.last_bidding_time + timedelta(hours=BIDDING_COOLDOWN_HOURS)
        return datetime.now(UTC) >= cooldown_end

    def has_failure_debuff(self) -> bool:
        """Check if character has the failure debuff active."""
        if not self.failure_debuff_until:
            return False
        return datetime.now(UTC) < self.failure_debuff_until

    def get_stat_modifier(self) -> float:
        """Get the stat modifier from curse effects."""
        if not self.cursed:
            return 1.0
        if self.has_failure_debuff():
            return 1.0 - BIDDING_FAILURE_STAT_PENALTY  # -10% during debuff
        return 1.0  # Base stats handled separately

    def get_damage_modifier(self) -> float:
        """Get the damage modifier from curse."""
        if not self.cursed:
            return 1.0
        if self.has_failure_debuff():
            return 1.0 - BIDDING_FAILURE_STAT_PENALTY
        return 1.0 + CURSE_DAMAGE_BONUS  # +15% damage


def load_cthaeh_status(character: "Character") -> CthaehStatus:
    """Load Cthaeh status from a Character model."""
    status = CthaehStatus(character_id=str(character.id))

    data = character.cthaeh_data or {}
    status.cursed = data.get("cursed", False)

    # Parse datetime fields
    if data.get("curse_accepted_at"):
        status.curse_accepted_at = datetime.fromisoformat(data["curse_accepted_at"])
    if data.get("last_bidding_time"):
        status.last_bidding_time = datetime.fromisoformat(data["last_bidding_time"])
    if data.get("target_expires_at"):
        status.target_expires_at = datetime.fromisoformat(data["target_expires_at"])
    if data.get("failure_debuff_until"):
        status.failure_debuff_until = datetime.fromisoformat(data["failure_debuff_until"])

    status.current_target = data.get("current_target")
    status.target_type = data.get("target_type", "npc")
    status.target_display_name = data.get("target_display_name")
    status.completed_biddings = data.get("completed_biddings", 0)
    status.failed_biddings = data.get("failed_biddings", 0)

    return status


def save_cthaeh_status(character: "Character", status: CthaehStatus) -> None:
    """Save Cthaeh status to a Character model."""
    data: dict[str, Any] = {
        "cursed": status.cursed,
        "current_target": status.current_target,
        "target_type": status.target_type,
        "target_display_name": status.target_display_name,
        "completed_biddings": status.completed_biddings,
        "failed_biddings": status.failed_biddings,
    }

    # Serialize datetime fields
    if status.curse_accepted_at:
        data["curse_accepted_at"] = status.curse_accepted_at.isoformat()
    if status.last_bidding_time:
        data["last_bidding_time"] = status.last_bidding_time.isoformat()
    if status.target_expires_at:
        data["target_expires_at"] = status.target_expires_at.isoformat()
    if status.failure_debuff_until:
        data["failure_debuff_until"] = status.failure_debuff_until.isoformat()

    character.cthaeh_data = data
    flag_modified(character, "cthaeh_data")


def accept_curse(character: "Character") -> CthaehStatus:
    """Accept the Cthaeh's curse. This is irreversible."""
    status = load_cthaeh_status(character)

    if status.cursed:
        return status  # Already cursed

    status.cursed = True
    status.curse_accepted_at = datetime.now(UTC)
    status.completed_biddings = 0
    status.failed_biddings = 0

    save_cthaeh_status(character, status)

    logger.info(
        "cthaeh_curse_accepted",
        character_id=str(character.id),
        character_name=character.name,
    )

    return status


def generate_bidding_target(
    character: "Character",
    engine: "GameEngine",
    prefer_player: bool = False,
) -> tuple[str, str, str]:
    """
    Generate a new bidding target for the cursed character.

    Args:
        character: The cursed character
        engine: Game engine for accessing online players
        prefer_player: If True, prioritize player targets

    Returns:
        Tuple of (target_id, target_type, display_name)
    """
    # Check if we should target a player (20% chance if players online)
    online_players = [
        conn
        for conn in engine.connections.values()
        if conn.session
        and conn.session.character_id
        and conn.session.character_id != str(character.id)
    ]

    if online_players and (prefer_player or random.random() < 0.20):
        # Target a random online player
        target_conn = random.choice(online_players)
        return (
            target_conn.session.character_id,
            "player",
            target_conn.session.character_name or "an unknown player",
        )

    # Target an NPC (weighted random)
    total_weight = sum(t["weight"] for t in BIDDING_NPC_TARGETS)
    roll = random.randint(1, total_weight)

    cumulative = 0
    for target in BIDDING_NPC_TARGETS:
        cumulative += target["weight"]
        if roll <= cumulative:
            return (target["id"], "npc", target["name"])

    # Fallback
    return ("sewer_rat", "npc", "a sewer rat")


def assign_new_bidding(
    character: "Character",
    engine: "GameEngine",
) -> CthaehStatus | None:
    """
    Assign a new bidding target to a cursed character.

    Returns:
        Updated status if bidding assigned, None if not eligible
    """
    status = load_cthaeh_status(character)

    if not status.can_receive_new_bidding():
        return None

    # Check for expired bidding first
    if status.is_bidding_expired():
        # Mark previous bidding as failed
        status.failed_biddings += 1
        status.failure_debuff_until = datetime.now(UTC) + timedelta(
            hours=BIDDING_FAILURE_DEBUFF_HOURS
        )
        logger.info(
            "cthaeh_bidding_failed",
            character_id=str(character.id),
            target=status.current_target,
        )

    # Generate new target
    target_id, target_type, display_name = generate_bidding_target(character, engine)

    status.current_target = target_id
    status.target_type = target_type
    status.target_display_name = display_name
    status.last_bidding_time = datetime.now(UTC)
    status.target_expires_at = datetime.now(UTC) + timedelta(hours=BIDDING_DURATION_HOURS)

    save_cthaeh_status(character, status)

    logger.info(
        "cthaeh_bidding_assigned",
        character_id=str(character.id),
        target_id=target_id,
        target_type=target_type,
    )

    return status


def complete_bidding(character: "Character", killed_id: str) -> tuple[bool, int]:
    """
    Check if a kill completes the current bidding.

    Args:
        character: The cursed character
        killed_id: ID of the killed entity (NPC template ID or player character ID)

    Returns:
        Tuple of (completed, bonus_xp)
    """
    status = load_cthaeh_status(character)

    if not status.cursed or not status.has_active_bidding():
        return (False, 0)

    if status.current_target != killed_id:
        return (False, 0)

    # Bidding completed!
    status.completed_biddings += 1
    status.current_target = None
    status.target_type = "npc"
    status.target_display_name = None
    status.target_expires_at = None

    save_cthaeh_status(character, status)

    logger.info(
        "cthaeh_bidding_completed",
        character_id=str(character.id),
        completed_count=status.completed_biddings,
    )

    # Return bonus XP (caller should calculate based on base XP)
    return (True, 1)  # Return 1 to signal completion, actual XP calculated by caller


def get_curse_combat_bonuses(character: "Character") -> dict[str, float]:
    """
    Get the combat bonuses from the Cthaeh's curse.

    Returns:
        Dict with damage_bonus, crit_bonus, stat_bonus keys
    """
    status = load_cthaeh_status(character)

    if not status.cursed:
        return {"damage_bonus": 0, "crit_bonus": 0, "stat_bonus": 0}

    if status.has_failure_debuff():
        # Debuff active - negative modifiers
        return {
            "damage_bonus": -BIDDING_FAILURE_STAT_PENALTY,
            "crit_bonus": -BIDDING_FAILURE_STAT_PENALTY,
            "stat_bonus": -CURSE_STAT_BONUS,
        }

    return {
        "damage_bonus": CURSE_DAMAGE_BONUS,
        "crit_bonus": CURSE_CRIT_BONUS,
        "stat_bonus": CURSE_STAT_BONUS,
    }


def format_curse_status(character: "Character") -> list[str]:
    """Format the curse status for display."""
    status = load_cthaeh_status(character)
    lines = []

    if not status.cursed:
        return ["You are not touched by the Cthaeh's shadow."]

    lines.append("The Cthaeh's shadow lies upon you.")
    lines.append("")

    # Show buffs/debuffs
    if status.has_failure_debuff():
        remaining = status.failure_debuff_until - datetime.now(UTC)
        hours = int(remaining.total_seconds() / 3600)
        minutes = int((remaining.total_seconds() % 3600) / 60)
        lines.append(f"DEBUFF ACTIVE: -{int(BIDDING_FAILURE_STAT_PENALTY * 100)}% all stats")
        lines.append(f"  Expires in: {hours}h {minutes}m")
    else:
        lines.append(f"Combat Bonus: +{int(CURSE_DAMAGE_BONUS * 100)}% damage")
        lines.append(f"Crit Bonus: +{int(CURSE_CRIT_BONUS * 100)}% critical chance")
        lines.append(f"Stat Bonus: +{CURSE_STAT_BONUS} STR, DEX, CON")

    lines.append("")
    lines.append(f"Biddings Completed: {status.completed_biddings}")
    lines.append(f"Biddings Failed: {status.failed_biddings}")

    # Show current bidding
    if status.has_active_bidding():
        remaining = status.target_expires_at - datetime.now(UTC)
        hours = int(remaining.total_seconds() / 3600)
        minutes = int((remaining.total_seconds() % 3600) / 60)
        lines.append("")
        lines.append("CURRENT BIDDING:")
        lines.append(f"  Target: {status.target_display_name}")
        lines.append(f"  Time remaining: {hours}h {minutes}m")
    elif status.can_receive_new_bidding():
        lines.append("")
        lines.append("The Cthaeh whispers... a new task awaits you.")
        lines.append("Return to the Cthaeh's clearing to receive your bidding.")

    return lines
