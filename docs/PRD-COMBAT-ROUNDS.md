# PRD: Unified Round-Based Combat System

**Project:** Waystone MUD
**Document Version:** 1.0
**Date:** 2025-12-10
**Author:** Atlas (Principal Software Architect)
**Status:** Draft for Implementation

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Feature Breakdown](#feature-breakdown)
4. [Implementation Specifications](#implementation-specifications)
5. [Database Changes](#database-changes)
6. [Migration Strategy](#migration-strategy)
7. [Test Scenarios](#test-scenarios)
8. [Implementation Phases](#implementation-phases)

---

## Executive Summary

### Project Overview

Waystone MUD currently has two separate combat systems with fundamentally different mechanics:
- **Player-vs-Player (PvP):** Turn-based with state machine, initiative rolls, turn timers (30 seconds)
- **Player-vs-NPC:** Direct function calls requiring repeated "kill" commands, no rounds, no NPC counterattacks

This creates a disjointed player experience and prevents classic MUD combat mechanics like automatic combat rounds, NPC AI behavior, and flee mechanics from working properly.

This PRD specifies a **unified round-based combat system** that:
1. Merges PvP and NPC combat into a single system
2. Implements automatic 3-second combat rounds (PULSE_VIOLENCE pattern from ROM/CircleMUD)
3. Enables NPC counterattacks and AI behavior
4. Provides classic MUD mechanics: flee, wimpy, combat skills, death handling
5. Maintains compatibility with existing attribute system (STR/DEX/CON/INT/WIS/CHA)

### Success Metrics

- **Player Experience:** Single "kill npc" command starts automatic combat rounds until flee/death
- **Combat Engagement:** NPCs actively fight back with same combat rules as players
- **System Performance:** 100+ simultaneous combats with 3-second round timer
- **Code Quality:** 90%+ test coverage, zero duplicate combat logic between PvP/NPC
- **Migration Success:** Existing PvP combat transitions without data loss

### Technical Stack

- **Language:** Python 3.14 with asyncio
- **Database:** PostgreSQL with SQLAlchemy async ORM
- **Architecture:** Event-driven round-based state machine
- **Combat Loop:** asyncio.create_task() with 3-second intervals
- **State Management:** Global combat registry with per-room combat instances

### Timeline Estimate

- **Phase 1 (Core Combat Loop):** 2-3 days
- **Phase 2 (NPC Integration):** 1-2 days
- **Phase 3 (Advanced Features):** 2-3 days
- **Phase 4 (Migration & Testing):** 1-2 days
- **Total:** 6-10 days for solo developer

### Resource Requirements

- **Backend Developer:** 1 (Python/asyncio expertise, MUD system knowledge)
- **QA Testing:** Manual testing of combat scenarios
- **Database Migration:** Schema changes to Character model

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        GAME ENGINE                              │
│  - Manages active_combats: dict[room_id, Combat]               │
│  - Periodic tick: check_combat_rounds(), check_npc_respawns()  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    UNIFIED COMBAT SYSTEM                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Combat (Room-Based State Machine)                        │  │
│  │ - state: CombatState (ACTIVE, ENDED)                     │  │
│  │ - participants: list[CombatParticipant]                  │  │
│  │ - round_number: int                                      │  │
│  │ - round_task: asyncio.Task (3-second loop)               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│         ┌────────────────────┼────────────────────┐            │
│         ▼                    ▼                    ▼            │
│  ┌─────────────┐     ┌─────────────┐      ┌─────────────┐    │
│  │   Player    │     │   Player    │      │     NPC     │    │
│  │ Participant │     │ Participant │      │ Participant │    │
│  │ - char_id   │     │ - char_id   │      │ - npc_inst  │    │
│  │ - target_id │     │ - target_id │      │ - target_id │    │
│  │ - is_npc=F  │     │ - is_npc=F  │      │ - is_npc=T  │    │
│  └─────────────┘     └─────────────┘      └─────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     COMBAT MECHANICS                            │
│  - roll_to_hit(attacker, defender) -> bool                     │
│  - calculate_damage(attacker, is_critical) -> int              │
│  - apply_damage(target, damage) -> int                         │
│  - check_death(target) -> bool                                 │
│  - attempt_flee(combatant) -> bool                             │
│  - npc_ai_choose_action(npc) -> Action                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE MODELS                              │
│  Character:                        NPCInstance:                │
│  - current_hp, max_hp              - current_hp, max_hp        │
│  - combat_state: CombatState       - last_hit_by               │
│  - combat_target_id                - fleeing                   │
│  - wimpy_threshold                 - in_combat                 │
│  - wait_state_until                                            │
└─────────────────────────────────────────────────────────────────┘
```

### Combat Round Flow (3-Second Automatic Loop)

```
START COMBAT
     │
     ▼
┌─────────────────────────────────────────┐
│ Combat.start()                          │
│ - Roll initiative for all participants  │
│ - Sort by initiative order              │
│ - Start round_task (asyncio loop)       │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ ROUND LOOP (every 3 seconds)            │◄─────────┐
│                                         │          │
│ 1. Increment round_number               │          │
│ 2. Broadcast "Round X begins"           │          │
│ 3. For each participant (by initiative):│          │
│    - Check if alive                     │          │
│    - Check if wait_state expired        │          │
│    - Execute auto_action():             │          │
│      • Player: attack current_target    │          │
│      • NPC: AI choose action            │          │
│    - Apply wait_state if needed         │          │
│ 4. Check combat end conditions:         │          │
│    - All on one side dead?              │          │
│    - All fled except one?               │          │
│ 5. Sleep 3 seconds                      │          │
└─────────────────────────────────────────┘          │
     │                                                │
     │ Combat continues                              │
     └────────────────────────────────────────────────┘
     │
     │ Combat ends (death/flee)
     ▼
┌─────────────────────────────────────────┐
│ Combat.end()                            │
│ - Cancel round_task                     │
│ - Clear combat_state for all            │
│ - Award XP                              │
│ - Generate loot                         │
│ - Handle corpses/respawns               │
└─────────────────────────────────────────┘
```

### State Machine

```
Character Combat State Transitions:

IDLE ────────────► COMBAT_ACTIVE ────────────► IDLE
      (attack cmd)                  (death/flee/victory)
                         │
                         │ (during combat)
                         ▼
                  WAIT_STATE (skill lag)
                         │
                         │ (timer expires)
                         ▼
                  COMBAT_ACTIVE


Combat Entity States:

SETUP ──────► ACTIVE ──────► ENDED
   (add         (start      (death/flee/
 participants)  rounds)      all escaped)
```

### Data Flow Diagrams

#### Initiating Combat

```
Player: "kill rat"
     │
     ▼
AttackCommand.execute()
     │
     ├──► Find target: find_npc_by_name("rat")
     │
     ├──► Check existing combat: get_combat_for_room(room_id)
     │         │
     │         ├──► None: create_combat(room_id)
     │         │         │
     │         │         ├──► add_participant(player_id, is_npc=False)
     │         │         ├──► add_participant(npc_instance, is_npc=True)
     │         │         └──► combat.start()
     │         │
     │         └──► Exists: combat.add_participant(player_id)
     │
     └──► Set player.combat_target_id = npc_instance.id
          Set npc_instance.combat_target_id = player_id
```

#### Combat Round Execution

```
Round Timer (3s) fires
     │
     ▼
Combat.execute_round()
     │
     ├──► For each participant (by initiative):
     │         │
     │         ├──► Check alive: current_hp > 0
     │         │         │
     │         │         ├──► Dead: remove_participant()
     │         │         └──► Alive: continue
     │         │
     │         ├──► Check wait_state: now >= wait_state_until
     │         │         │
     │         │         ├──► Waiting: skip turn, show "[Name] is recovering..."
     │         │         └──► Ready: continue
     │         │
     │         ├──► Execute auto_action():
     │         │         │
     │         │         ├──► Player: attack(target_id)
     │         │         │
     │         │         └──► NPC: npc_ai_action()
     │         │                   │
     │         │                   ├──► Check HP < wimpy: attempt_flee()
     │         │                   ├──► Has target: attack(target_id)
     │         │                   └──► No target: choose_target()
     │         │
     │         └──► Broadcast action result to room
     │
     ├──► Check combat end:
     │         │
     │         ├──► All enemies dead: end_combat(VICTORY)
     │         ├──► All allies dead: end_combat(DEFEAT)
     │         └──► Combat continues
     │
     └──► await asyncio.sleep(3)
```

### Integration Points

#### Existing Systems Integration

| System | Integration Point | Changes Required |
|--------|------------------|------------------|
| **Combat.py (PvP)** | Merge into unified Combat class | Refactor turn-based to round-based, remove turn timer |
| **NPC Combat** | Replace attack_npc() with unified system | NPCs become CombatParticipants with AI actions |
| **Death System** | Call on combat death | Add combat context tracking |
| **Experience** | Award XP on combat victory | Track participation, calculate XP shares |
| **Command System** | Kill, flee, wimpy commands | Route to unified combat API |
| **Game Engine** | Manage active_combats dict | Add periodic tick for round processing |

#### External API Dependencies

- **Database:** SQLAlchemy async sessions for HP updates, character state
- **Network Layer:** broadcast_to_room() for combat messages
- **World System:** Room.players list for targeting, movement

---

## Feature Breakdown

### 1. Unified Combat Participant System

**User Story:** As a developer, I need a single participant class that works for both players and NPCs, so combat logic is consistent.

**Functional Requirements:**

- `CombatParticipant` dataclass represents any combatant (player/NPC)
- Fields:
  - `entity_id: str` - Character UUID or NPC instance ID
  - `entity_name: str` - Display name
  - `is_npc: bool` - Entity type flag
  - `initiative: int` - Initiative roll (d20 + DEX)
  - `target_id: str | None` - Current target entity_id
  - `wait_state_until: datetime | None` - Skill lag timer
  - `is_defending: bool` - Defensive stance flag
  - `fled: bool` - Successfully fled flag
- Unified attribute access:
  - `get_hp(participant) -> tuple[int, int]` (current, max)
  - `get_attribute(participant, attr: str) -> int` (STR, DEX, etc.)
  - `apply_damage(participant, damage: int) -> int` (returns new HP)

**Non-Functional Requirements:**

- Performance: Lookup entity data in O(1) time (cache Character/NPC objects)
- Memory: < 1KB per participant
- Extensibility: Support future entity types (pets, summons)

**API Specifications:**

```python
@dataclass
class CombatParticipant:
    """Unified participant for players and NPCs."""
    entity_id: str
    entity_name: str
    is_npc: bool
    initiative: int
    target_id: str | None = None
    wait_state_until: datetime | None = None
    is_defending: bool = False
    fled: bool = False

    # Cached entity reference
    _entity_ref: Character | NPCInstance | None = None

async def get_participant_hp(p: CombatParticipant) -> tuple[int, int]:
    """Get (current_hp, max_hp) for participant."""

async def get_participant_attribute(p: CombatParticipant, attr: str) -> int:
    """Get attribute value (strength, dexterity, etc.)."""

async def apply_damage_to_participant(p: CombatParticipant, damage: int) -> int:
    """Apply damage, returns new HP. Updates DB for players."""
```

**Acceptance Criteria:**

- ✅ CombatParticipant works for Character objects
- ✅ CombatParticipant works for NPCInstance objects
- ✅ get_participant_hp() returns correct values for both types
- ✅ apply_damage_to_participant() persists to DB for players
- ✅ apply_damage_to_participant() updates in-memory for NPCs

**Testing Checklist:**

- [ ] Unit test: Create player participant, verify fields
- [ ] Unit test: Create NPC participant, verify fields
- [ ] Unit test: get_participant_hp() for player
- [ ] Unit test: get_participant_hp() for NPC
- [ ] Unit test: apply_damage persists to Character table
- [ ] Unit test: apply_damage updates NPCInstance.current_hp

---

### 2. Automatic Combat Round System

**User Story:** As a player, when I attack an enemy, combat automatically continues every 3 seconds until I flee or someone dies, so I don't spam "kill" commands.

**Functional Requirements:**

- Combat enters ACTIVE state on first attack
- `asyncio.Task` executes `_combat_round_loop()` every 3 seconds
- Each round:
  1. Increment `round_number`
  2. Broadcast "Round X" to room
  3. Process participants in initiative order
  4. Check combat end conditions
  5. Sleep 3 seconds
- Round loop cancels on combat end

**Non-Functional Requirements:**

- **Performance:** Support 100+ concurrent combat instances
- **Timing Accuracy:** ±0.1s variance on 3-second rounds
- **Reliability:** Gracefully handle participant disconnects
- **Resource Safety:** Cancel tasks on engine shutdown

**API Specifications:**

```python
class Combat:
    """Unified combat instance."""

    def __init__(self, room_id: str, engine: GameEngine):
        self.room_id = room_id
        self.engine = engine
        self.state = CombatState.SETUP
        self.participants: list[CombatParticipant] = []
        self.round_number = 0
        self.round_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Roll initiative and start round loop."""
        self._roll_initiative_for_all()
        self.participants.sort(key=lambda p: p.initiative, reverse=True)
        self.state = CombatState.ACTIVE
        self.round_task = asyncio.create_task(self._combat_round_loop())

    async def _combat_round_loop(self) -> None:
        """3-second round loop."""
        while self.state == CombatState.ACTIVE:
            self.round_number += 1
            await self._execute_round()

            if not self._check_combat_continues():
                await self.end_combat()
                break

            await asyncio.sleep(3)

    async def _execute_round(self) -> None:
        """Execute one combat round."""
        self.engine.broadcast_to_room(
            self.room_id,
            colorize(f"\n--- Round {self.round_number} ---", "CYAN")
        )

        for participant in self.participants:
            if participant.fled or await self._is_dead(participant):
                continue

            if self._is_waiting(participant):
                self._show_wait_message(participant)
                continue

            await self._auto_action(participant)

    async def _auto_action(self, p: CombatParticipant) -> None:
        """Execute participant's automatic action."""
        if p.is_npc:
            await self._npc_auto_action(p)
        else:
            await self._player_auto_action(p)

    async def end_combat(self) -> None:
        """End combat and cleanup."""
        self.state = CombatState.ENDED
        if self.round_task:
            self.round_task.cancel()
```

**Acceptance Criteria:**

- ✅ Combat starts 3-second round loop on first attack
- ✅ Each round broadcasts round number
- ✅ Each participant acts once per round in initiative order
- ✅ Round loop stops when combat ends
- ✅ Task cleanup on engine shutdown

**Testing Checklist:**

- [ ] Integration test: Start combat, verify 3-second intervals
- [ ] Integration test: Kill enemy, verify loop stops
- [ ] Integration test: All flee, verify loop stops
- [ ] Unit test: Initiative sorting (high to low)
- [ ] Stress test: 100 simultaneous combats, verify performance
- [ ] Edge case: Participant disconnects mid-combat

---

### 3. NPC Combat AI and Counterattacks

**User Story:** As a player, when I attack an NPC, it automatically fights back and makes tactical decisions, creating engaging combat.

**Functional Requirements:**

- NPCs join combat as `CombatParticipant` with `is_npc=True`
- Each round, NPC executes AI action:
  1. Check wimpy threshold: if HP < wimpy%, attempt flee
  2. Check aggression: aggressive NPCs attack, passive flee
  3. Choose target: prioritize last attacker, then nearest
  4. Execute action: attack, flee, or special skill
- NPC attacks use same combat mechanics as players:
  - To-hit: d20 + DEX modifier vs target defense
  - Damage: 1d6 + STR modifier (2d6 on crit)
  - Critical on nat 20, fumble on nat 1

**Non-Functional Requirements:**

- **Balance:** NPC damage equal to player damage at same level
- **Variety:** 3+ AI behaviors (aggressive, defensive, tactical)
- **Performance:** AI decision < 10ms per action

**API Specifications:**

```python
async def _npc_auto_action(self, npc: CombatParticipant) -> None:
    """NPC AI chooses and executes action."""
    npc_instance = await self._get_npc_instance(npc.entity_id)

    # Check wimpy threshold
    hp_percent = npc_instance.current_hp / npc_instance.max_hp
    wimpy_threshold = 0.2  # Default 20%

    if hp_percent < wimpy_threshold:
        await self._attempt_flee(npc)
        return

    # Choose action based on behavior
    if npc_instance.behavior == "aggressive":
        if not npc.target_id:
            npc.target_id = self._npc_choose_target(npc)

        if npc.target_id:
            await self._execute_attack(npc, npc.target_id)
        else:
            # No valid targets, flee
            await self._attempt_flee(npc)

    elif npc_instance.behavior == "passive":
        # Passive NPCs flee when attacked
        await self._attempt_flee(npc)

    elif npc_instance.behavior == "training_dummy":
        # Training dummies don't act
        pass

def _npc_choose_target(self, npc: CombatParticipant) -> str | None:
    """Choose target for NPC."""
    npc_instance = self._get_npc_instance(npc.entity_id)

    # Priority 1: Last attacker
    if npc_instance.last_hit_by:
        if any(p.entity_id == npc_instance.last_hit_by for p in self.participants):
            return npc_instance.last_hit_by

    # Priority 2: Player participants (NPCs prefer players over other NPCs)
    player_participants = [p for p in self.participants if not p.is_npc and not p.fled]
    if player_participants:
        return random.choice(player_participants).entity_id

    return None
```

**Acceptance Criteria:**

- ✅ NPC counterattacks when hit by player
- ✅ Aggressive NPCs attack every round
- ✅ Passive NPCs flee when attacked
- ✅ NPCs flee when HP < 20% (wimpy)
- ✅ Training dummies don't counterattack

**Testing Checklist:**

- [ ] Integration test: Attack aggressive NPC, verify counterattack
- [ ] Integration test: Attack passive NPC, verify flee attempt
- [ ] Integration test: Reduce NPC HP to 15%, verify flee
- [ ] Unit test: _npc_choose_target() prioritizes last_hit_by
- [ ] Unit test: Training dummy behavior (no action)

---

### 4. Flee Mechanics with Failure Chance

**User Story:** As a player, I can attempt to flee from combat, but it might fail, adding risk to escape decisions.

**Functional Requirements:**

- `flee` command available during combat
- Flee check: d20 + DEX modifier vs DC 12
- On success:
  - Remove from combat participants
  - Broadcast "[Name] flees!" to room
  - Move to random adjacent room (if available)
  - Set 3-second movement lag (wait_state)
- On failure:
  - Broadcast "[Name] tries to flee but fails!" to room
  - Remain in combat, lose action this round
  - Set 1-second flee cooldown (wait_state)
- NPCs can flee using same mechanics

**Non-Functional Requirements:**

- **Failure Rate:** ~40% at DEX 10 (balanced risk)
- **Movement:** Random exit selection, no backtracking preference
- **Anti-Spam:** 1-second cooldown between flee attempts

**API Specifications:**

```python
async def attempt_flee(self, participant: CombatParticipant) -> bool:
    """
    Attempt to flee from combat.

    Returns:
        True if flee succeeded, False if failed
    """
    # Get DEX modifier
    dex = await get_participant_attribute(participant, "dexterity")
    dex_mod = (dex - 10) // 2

    # Flee check: d20 + DEX vs DC 12
    roll = random.randint(1, 20)
    total = roll + dex_mod

    if total >= 12:
        # Success
        participant.fled = True

        self.engine.broadcast_to_room(
            self.room_id,
            colorize(f"{participant.entity_name} flees from combat!", "YELLOW")
        )

        # Move to random exit (if player)
        if not participant.is_npc:
            await self._flee_to_random_exit(participant)

        # Remove from combat
        self.participants.remove(participant)

        # Check if combat ends
        if len(self.participants) <= 1:
            await self.end_combat()

        return True
    else:
        # Failure
        self.engine.broadcast_to_room(
            self.room_id,
            colorize(
                f"{participant.entity_name} tries to flee but fails! (Rolled {total} vs DC 12)",
                "YELLOW"
            )
        )

        # Set 1-second flee cooldown
        participant.wait_state_until = datetime.now() + timedelta(seconds=1)

        return False

async def _flee_to_random_exit(self, participant: CombatParticipant) -> None:
    """Move fleeing player to random adjacent room."""
    room = self.engine.world.get(self.room_id)
    if not room or not room.exits:
        return

    # Choose random exit
    exit_dir = random.choice(list(room.exits.keys()))
    destination_id = room.exits[exit_dir]

    # Move character
    async with get_session() as session:
        char = await session.execute(
            select(Character).where(Character.id == UUID(participant.entity_id))
        )
        character = char.scalar_one_or_none()
        if character:
            character.current_room_id = destination_id
            await session.commit()

    # Update room tracking
    room.remove_player(participant.entity_id)
    dest_room = self.engine.world.get(destination_id)
    if dest_room:
        dest_room.add_player(participant.entity_id)

    # Broadcast arrival
    self.engine.broadcast_to_room(
        destination_id,
        colorize(
            f"{participant.entity_name} arrives, fleeing from combat!",
            "YELLOW"
        )
    )
```

**Acceptance Criteria:**

- ✅ Flee succeeds ~60% of time at DEX 10
- ✅ Successful flee removes from combat, moves to random exit
- ✅ Failed flee shows message, applies 1s cooldown
- ✅ NPCs can flee when HP low
- ✅ Combat ends if all but one participant flee

**Testing Checklist:**

- [ ] Unit test: Flee roll calculation (d20 + DEX vs DC 12)
- [ ] Integration test: Flee success, verify room movement
- [ ] Integration test: Flee failure, verify cooldown
- [ ] Integration test: NPC flee at low HP
- [ ] Integration test: All participants flee, combat ends
- [ ] Edge case: Flee from room with no exits (fail gracefully)

---

### 5. Wimpy (Auto-Flee Threshold)

**User Story:** As a player, I can set a wimpy threshold to automatically attempt flee when my HP drops below a percentage, preventing death.

**Functional Requirements:**

- `wimpy <percent>` command sets auto-flee threshold (0-99%)
- During combat, check wimpy after taking damage
- If `current_hp / max_hp * 100 < wimpy_threshold`, automatically attempt flee
- Wimpy flee uses same mechanics as manual flee (can fail)
- Broadcast "[Name] tries to flee (wimpy)!" on wimpy trigger
- `wimpy 0` or `wimpy off` disables wimpy

**Non-Functional Requirements:**

- **Persistence:** Wimpy threshold saved to character record
- **Clarity:** Show current wimpy in `score` command
- **Balance:** Wimpy flee has same failure chance as manual

**API Specifications:**

```python
# Database change
class Character(Base):
    # ... existing fields ...
    wimpy_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Auto-flee when HP% drops below this value (0-99)",
    )

async def check_wimpy(self, participant: CombatParticipant) -> None:
    """Check if participant should auto-flee due to wimpy."""
    if participant.is_npc:
        return  # NPCs have hard-coded wimpy behavior

    async with get_session() as session:
        char = await session.execute(
            select(Character).where(Character.id == UUID(participant.entity_id))
        )
        character = char.scalar_one_or_none()

        if not character or character.wimpy_threshold == 0:
            return

        hp_percent = (character.current_hp / character.max_hp) * 100

        if hp_percent < character.wimpy_threshold:
            self.engine.broadcast_to_room(
                self.room_id,
                colorize(f"{character.name} tries to flee (wimpy)!", "YELLOW")
            )
            await self.attempt_flee(participant)

class WimpyCommand(Command):
    """Set auto-flee HP threshold."""

    name = "wimpy"
    aliases = []
    help_text = "wimpy <percent> - Auto-flee when HP% drops below threshold (0-99, 0=off)"

    async def execute(self, ctx: CommandContext) -> None:
        if not ctx.args:
            # Show current wimpy
            async with get_session() as session:
                char = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = char.scalar_one_or_none()

                if character.wimpy_threshold > 0:
                    await ctx.connection.send_line(
                        f"Wimpy: {character.wimpy_threshold}% HP"
                    )
                else:
                    await ctx.connection.send_line("Wimpy: Off")
            return

        # Parse threshold
        threshold_str = ctx.args[0].lower()
        if threshold_str in ["off", "0"]:
            threshold = 0
        else:
            try:
                threshold = int(threshold_str)
                if threshold < 0 or threshold > 99:
                    await ctx.connection.send_line(
                        colorize("Wimpy threshold must be 0-99%.", "RED")
                    )
                    return
            except ValueError:
                await ctx.connection.send_line(
                    colorize("Usage: wimpy <percent> (0-99, or 'off')", "RED")
                )
                return

        # Save to database
        async with get_session() as session:
            char = await session.execute(
                select(Character).where(Character.id == UUID(ctx.session.character_id))
            )
            character = char.scalar_one_or_none()
            character.wimpy_threshold = threshold
            await session.commit()

        if threshold > 0:
            await ctx.connection.send_line(
                colorize(f"Wimpy set to {threshold}% HP.", "GREEN")
            )
        else:
            await ctx.connection.send_line(
                colorize("Wimpy disabled.", "GREEN")
            )
```

**Acceptance Criteria:**

- ✅ `wimpy 20` sets auto-flee at 20% HP
- ✅ Taking damage below wimpy triggers automatic flee attempt
- ✅ Wimpy flee can fail (same mechanics as manual flee)
- ✅ `wimpy off` disables auto-flee
- ✅ Wimpy threshold persists across sessions

**Testing Checklist:**

- [ ] Unit test: Set wimpy to 25%, verify DB update
- [ ] Integration test: Take damage to 24% HP, verify auto-flee
- [ ] Integration test: Wimpy flee fails, remain in combat
- [ ] Integration test: `wimpy off`, no auto-flee at low HP
- [ ] Unit test: `wimpy 100` rejects (invalid range)

---

### 6. Combat Skills with Cooldowns and Wait States

**User Story:** As a player, I can use special combat skills like bash, disarm, and kick, but they have cooldowns and cause lag, requiring tactical decisions.

**Functional Requirements:**

- Combat skills: `bash`, `kick`, `disarm`, `trip`
- Each skill has:
  - Success roll: skill check vs target defense
  - Damage/effect: varies by skill
  - Wait state: 1-3 rounds of lag after use
  - Cooldown: 10-30 seconds between uses
- Wait state prevents all actions (auto-attack, flee, skills)
- Skills fail if character is in wait_state or on cooldown
- Broadcast skill effects to room with descriptive messages

**Non-Functional Requirements:**

- **Balance:** Skills 20-30% more effective than basic attack
- **Skill Investment:** Success rate increases with skill rank
- **Cooldown Tracking:** Per-character, per-skill cooldowns

**API Specifications:**

```python
@dataclass
class CombatSkill:
    """Combat skill definition."""
    name: str
    wait_state_rounds: int  # Rounds of lag after use
    cooldown_seconds: int  # Cooldown between uses
    damage_dice: str  # e.g., "2d6"
    damage_modifier: str  # e.g., "STR"
    special_effect: str | None  # e.g., "knockdown", "disarm"
    success_dc: int  # Difficulty check

COMBAT_SKILLS: dict[str, CombatSkill] = {
    "bash": CombatSkill(
        name="bash",
        wait_state_rounds=2,
        cooldown_seconds=15,
        damage_dice="1d8",
        damage_modifier="STR",
        special_effect="knockdown",
        success_dc=14,
    ),
    "kick": CombatSkill(
        name="kick",
        wait_state_rounds=1,
        cooldown_seconds=10,
        damage_dice="1d6",
        damage_modifier="DEX",
        special_effect=None,
        success_dc=12,
    ),
    "disarm": CombatSkill(
        name="disarm",
        wait_state_rounds=1,
        cooldown_seconds=20,
        damage_dice="0d0",
        damage_modifier=None,
        special_effect="disarm",
        success_dc=16,
    ),
    "trip": CombatSkill(
        name="trip",
        wait_state_rounds=1,
        cooldown_seconds=12,
        damage_dice="0d0",
        damage_modifier="DEX",
        special_effect="knockdown",
        success_dc=13,
    ),
}

# Database change
class Character(Base):
    # ... existing fields ...
    skill_cooldowns: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Skill cooldowns: {skill_name: next_use_timestamp}",
    )

async def use_combat_skill(
    self,
    participant: CombatParticipant,
    skill_name: str,
    target_id: str,
) -> tuple[bool, str]:
    """
    Use a combat skill.

    Returns:
        (success, message)
    """
    skill = COMBAT_SKILLS.get(skill_name)
    if not skill:
        return False, f"Unknown skill: {skill_name}"

    # Check wait state
    if participant.wait_state_until and datetime.now() < participant.wait_state_until:
        return False, "You must wait before acting again!"

    # Check cooldown
    async with get_session() as session:
        char = await session.execute(
            select(Character).where(Character.id == UUID(participant.entity_id))
        )
        character = char.scalar_one_or_none()

        cooldowns = character.skill_cooldowns or {}
        if skill_name in cooldowns:
            next_use = datetime.fromisoformat(cooldowns[skill_name])
            if datetime.now() < next_use:
                wait_seconds = (next_use - datetime.now()).total_seconds()
                return False, f"{skill_name.capitalize()} is on cooldown ({int(wait_seconds)}s)."

        # Get target
        target_participant = next((p for p in self.participants if p.entity_id == target_id), None)
        if not target_participant:
            return False, "Target not in combat!"

        # Skill check: d20 + skill_rank vs DC
        skill_rank = character.skills.get(skill_name, {}).get("rank", 0)
        roll = random.randint(1, 20)
        total = roll + skill_rank

        if total < skill.success_dc:
            # Failure
            self.engine.broadcast_to_room(
                self.room_id,
                colorize(
                    f"{character.name} tries to {skill_name} {target_participant.entity_name} but fails! (Rolled {total} vs DC {skill.success_dc})",
                    "YELLOW"
                )
            )

            # Apply wait state and cooldown even on failure
            participant.wait_state_until = datetime.now() + timedelta(seconds=skill.wait_state_rounds * 3)
            cooldowns[skill_name] = (datetime.now() + timedelta(seconds=skill.cooldown_seconds)).isoformat()
            character.skill_cooldowns = cooldowns
            await session.commit()

            return True, f"Your {skill_name} failed!"

        # Success - calculate damage
        damage = 0
        if skill.damage_dice != "0d0":
            num_dice, die_size = map(int, skill.damage_dice.split("d"))
            for _ in range(num_dice):
                damage += random.randint(1, die_size)

            if skill.damage_modifier:
                modifier_value = getattr(character, skill.damage_modifier.lower())
                modifier = (modifier_value - 10) // 2
                damage += modifier

            damage = max(1, damage)

            # Apply damage
            await apply_damage_to_participant(target_participant, damage)

        # Apply special effect
        effect_msg = ""
        if skill.special_effect == "knockdown":
            target_participant.wait_state_until = datetime.now() + timedelta(seconds=6)  # 2 rounds
            effect_msg = f"{target_participant.entity_name} is knocked down!"
        elif skill.special_effect == "disarm":
            # TODO: Implement equipment drop
            effect_msg = f"{target_participant.entity_name} is disarmed!"

        # Broadcast success
        skill_msg = colorize(
            f"{character.name} {skill_name}s {target_participant.entity_name}!" +
            (f" ({damage} damage)" if damage > 0 else "") +
            (f" {effect_msg}" if effect_msg else ""),
            "CYAN"
        )
        self.engine.broadcast_to_room(self.room_id, skill_msg)

        # Apply wait state and cooldown
        participant.wait_state_until = datetime.now() + timedelta(seconds=skill.wait_state_rounds * 3)
        cooldowns[skill_name] = (datetime.now() + timedelta(seconds=skill.cooldown_seconds)).isoformat()
        character.skill_cooldowns = cooldowns
        await session.commit()

        # Check death
        if await self._is_dead(target_participant):
            await self._handle_death(target_participant)

        return True, f"Your {skill_name} succeeds!"
```

**Acceptance Criteria:**

- ✅ Bash skill: 1d8+STR damage, knockdown for 2 rounds, 2-round lag, 15s cooldown
- ✅ Kick skill: 1d6+DEX damage, 1-round lag, 10s cooldown
- ✅ Disarm skill: No damage, disarms weapon, 1-round lag, 20s cooldown
- ✅ Wait state prevents all actions during lag
- ✅ Cooldown prevents skill spam
- ✅ Skill rank increases success chance

**Testing Checklist:**

- [ ] Unit test: Bash skill damage calculation (1d8+STR)
- [ ] Integration test: Bash success, verify knockdown (2-round lag)
- [ ] Integration test: Use bash, wait 1 round, verify still lagged
- [ ] Integration test: Use bash, wait 14s, verify cooldown active
- [ ] Integration test: Use bash, wait 16s, verify cooldown expired
- [ ] Unit test: Kick skill damage (1d6+DEX)
- [ ] Integration test: Disarm skill, verify weapon drop

---

### 7. Death Handling and Corpse Creation

**User Story:** As a player, when I die in combat, I respawn at a safe location with penalties, and my items remain in a corpse at the death location.

**Functional Requirements:**

- On death (HP <= 0):
  1. End combat for dead participant
  2. Create corpse object in death room with inventory
  3. Apply death penalties:
     - 10% XP loss (existing system)
     - Weakened status: -20% stats for 5 minutes
  4. Respawn at University main hall with 1 HP
  5. Broadcast death/respawn messages
- Corpse persistence:
  - Corpse contains all equipped/inventory items
  - Corpse lasts 10 minutes before decay
  - Players can `get all from corpse` to recover items
- NPC death:
  - Award XP to killer (existing system)
  - Generate loot from loot_table_id
  - Schedule respawn based on respawn_time

**Non-Functional Requirements:**

- **Data Safety:** Inventory items never lost (always in corpse or player)
- **Balance:** Death penalty significant but not frustrating
- **Performance:** Corpse cleanup every 60 seconds (not per death)

**API Specifications:**

```python
async def _handle_death(self, participant: CombatParticipant) -> None:
    """Handle participant death."""
    if participant.is_npc:
        await self._handle_npc_death(participant)
    else:
        await self._handle_player_death(participant)

async def _handle_player_death(self, participant: CombatParticipant) -> None:
    """Handle player death with corpse creation."""
    async with get_session() as session:
        char = await session.execute(
            select(Character).where(Character.id == UUID(participant.entity_id))
        )
        character = char.scalar_one_or_none()

        # Create corpse
        corpse = await create_corpse(
            owner_id=character.id,
            room_id=self.room_id,
            character_name=character.name,
            session=session,
        )

        # Transfer inventory to corpse
        for item in character.items:
            item.location = "corpse"
            item.container_id = str(corpse.id)

        # Clear equipped items
        character.equipped = {}

        # Call existing death handler (XP penalty, respawn, weakened)
        from waystone.game.systems.death import handle_player_death
        await handle_player_death(
            character_id=character.id,
            death_location=self.room_id,
            engine=self.engine,
            session=session,
        )

        # Remove from combat
        self.participants.remove(participant)

        # Check combat end
        if len(self.participants) <= 1:
            await self.end_combat()

@dataclass
class Corpse:
    """Player corpse containing items."""
    id: str
    character_name: str
    room_id: str
    created_at: datetime
    decay_at: datetime  # 10 minutes from creation
    items: list[str]  # Item instance IDs

# Global corpse tracking
_corpses: dict[str, Corpse] = {}

async def create_corpse(
    owner_id: UUID,
    room_id: str,
    character_name: str,
    session: AsyncSession,
) -> Corpse:
    """Create a corpse object."""
    corpse = Corpse(
        id=str(uuid4()),
        character_name=character_name,
        room_id=room_id,
        created_at=datetime.now(),
        decay_at=datetime.now() + timedelta(minutes=10),
        items=[],
    )

    _corpses[corpse.id] = corpse

    logger.info(
        "corpse_created",
        corpse_id=corpse.id,
        character_name=character_name,
        room_id=room_id,
    )

    return corpse

async def check_corpse_decay(engine: GameEngine) -> int:
    """Remove decayed corpses. Call from engine tick."""
    now = datetime.now()
    decayed = []

    for corpse_id, corpse in _corpses.items():
        if now >= corpse.decay_at:
            # Decay corpse - items are lost
            engine.broadcast_to_room(
                corpse.room_id,
                colorize(
                    f"The corpse of {corpse.character_name} decays into dust.",
                    "YELLOW"
                )
            )

            # Delete items from database
            async with get_session() as session:
                for item_id in corpse.items:
                    await session.execute(
                        delete(ItemInstance).where(ItemInstance.id == UUID(item_id))
                    )
                await session.commit()

            decayed.append(corpse_id)

    for corpse_id in decayed:
        del _corpses[corpse_id]

    return len(decayed)
```

**Acceptance Criteria:**

- ✅ Player death creates corpse in death room
- ✅ Corpse contains all equipped and inventory items
- ✅ Player respawns at University with 1 HP, no items
- ✅ Player can retrieve items from corpse within 10 minutes
- ✅ Corpse decays after 10 minutes, items lost
- ✅ Death applies existing penalties (10% XP, weakened status)

**Testing Checklist:**

- [ ] Integration test: Die in combat, verify corpse created
- [ ] Integration test: Corpse contains all items
- [ ] Integration test: Get items from corpse
- [ ] Integration test: Wait 11 minutes, verify corpse decayed
- [ ] Integration test: Death removes from combat participants
- [ ] Unit test: create_corpse() returns valid Corpse object

---

### 8. Multiple Combatants and Target Switching

**User Story:** As a player, I can fight multiple enemies at once, switch targets, and coordinate with other players against tough NPCs.

**Functional Requirements:**

- Combat supports N participants (players + NPCs)
- Each participant has `target_id` tracking current enemy
- Target switching:
  - `kill <new_target>` in combat switches to new target
  - Next auto-attack targets new enemy
  - Broadcast "[Name] now attacks [Target]!" to room
- Combat ends when:
  - All participants on one side dead
  - All but one participant fled
  - Only one participant remains
- XP share:
  - All participants who damaged enemy get XP
  - XP split proportional to damage dealt

**Non-Functional Requirements:**

- **Scalability:** Support 10+ combatants per room
- **Targeting Clarity:** Clear messages showing who attacks whom
- **Fair XP:** Damage tracking per participant for fair rewards

**API Specifications:**

```python
async def switch_target(self, participant: CombatParticipant, new_target_id: str) -> bool:
    """
    Switch combat target.

    Returns:
        True if target switched, False if invalid
    """
    # Validate new target exists in combat
    new_target = next((p for p in self.participants if p.entity_id == new_target_id), None)
    if not new_target:
        return False

    # Can't target self
    if new_target_id == participant.entity_id:
        return False

    # Can't target fled participants
    if new_target.fled:
        return False

    # Switch target
    old_target_id = participant.target_id
    participant.target_id = new_target_id

    # Broadcast
    if old_target_id:
        old_target = next((p for p in self.participants if p.entity_id == old_target_id), None)
        if old_target:
            self.engine.broadcast_to_room(
                self.room_id,
                colorize(
                    f"{participant.entity_name} stops attacking {old_target.entity_name}!",
                    "YELLOW"
                )
            )

    self.engine.broadcast_to_room(
        self.room_id,
        colorize(
            f"{participant.entity_name} now attacks {new_target.entity_name}!",
            "CYAN"
        )
    )

    return True

# Track damage dealt for XP sharing
@dataclass
class DamageRecord:
    """Track damage dealt by each participant."""
    participant_id: str
    total_damage: int

class Combat:
    def __init__(self, room_id: str, engine: GameEngine):
        # ... existing fields ...
        self.damage_tracking: dict[str, list[DamageRecord]] = {}  # target_id -> damage records

async def _execute_attack(self, attacker: CombatParticipant, target_id: str) -> None:
    """Execute attack and track damage."""
    # ... existing attack logic ...

    # Track damage for XP sharing
    if target_id not in self.damage_tracking:
        self.damage_tracking[target_id] = []

    damage_record = next(
        (r for r in self.damage_tracking[target_id] if r.participant_id == attacker.entity_id),
        None
    )

    if damage_record:
        damage_record.total_damage += damage
    else:
        self.damage_tracking[target_id].append(
            DamageRecord(participant_id=attacker.entity_id, total_damage=damage)
        )

async def _handle_npc_death(self, npc: CombatParticipant) -> None:
    """Award XP to all participants who damaged NPC."""
    npc_instance = await self._get_npc_instance(npc.entity_id)

    # Get damage records for this NPC
    damage_records = self.damage_tracking.get(npc.entity_id, [])
    if not damage_records:
        return

    # Calculate total damage dealt
    total_damage = sum(r.total_damage for r in damage_records)

    # Award XP proportionally
    base_xp = 10 * npc_instance.level

    for record in damage_records:
        damage_percent = record.total_damage / total_damage
        xp_award = int(base_xp * damage_percent)

        if record.participant_id and not record.participant_id.startswith("npc_"):
            # Player participant
            await award_xp(
                UUID(record.participant_id),
                xp_award,
                f"defeating {npc_instance.name}",
            )
```

**Acceptance Criteria:**

- ✅ Combat supports 10+ simultaneous participants
- ✅ `kill <target>` switches target in combat
- ✅ Multiple players can attack same NPC
- ✅ XP awarded proportional to damage dealt
- ✅ Combat ends when all enemies defeated

**Testing Checklist:**

- [ ] Integration test: 3 players vs 2 NPCs, verify targeting
- [ ] Integration test: Switch target mid-combat
- [ ] Integration test: Kill NPC with 2 players, verify XP split
- [ ] Stress test: 15 participants in one combat
- [ ] Unit test: Damage tracking records correct totals

---

## Implementation Specifications

### Combat Round Loop Pseudocode

```python
class Combat:
    """Unified combat system."""

    async def start(self) -> None:
        """Initialize and start combat."""
        # Roll initiative for all participants
        for participant in self.participants:
            dex = await get_participant_attribute(participant, "dexterity")
            dex_mod = (dex - 10) // 2
            participant.initiative = random.randint(1, 20) + dex_mod

        # Sort by initiative (highest first)
        self.participants.sort(key=lambda p: p.initiative, reverse=True)

        # Broadcast initiative order
        self.engine.broadcast_to_room(
            self.room_id,
            self._format_initiative_order()
        )

        # Start combat
        self.state = CombatState.ACTIVE
        self.round_task = asyncio.create_task(self._combat_round_loop())

    async def _combat_round_loop(self) -> None:
        """Main 3-second round loop."""
        try:
            while self.state == CombatState.ACTIVE:
                self.round_number += 1

                # Execute round
                await self._execute_round()

                # Check combat end conditions
                if not self._should_continue_combat():
                    await self.end_combat()
                    break

                # Wait 3 seconds
                await asyncio.sleep(3)

        except asyncio.CancelledError:
            logger.info("combat_round_loop_cancelled", room_id=self.room_id)
        except Exception as e:
            logger.error(
                "combat_round_loop_error",
                room_id=self.room_id,
                error=str(e),
                exc_info=True
            )
            await self.end_combat()

    async def _execute_round(self) -> None:
        """Execute one combat round."""
        # Broadcast round start
        self.engine.broadcast_to_room(
            self.room_id,
            colorize(f"\n--- Round {self.round_number} ---", "CYAN")
        )

        # Process each participant in initiative order
        for participant in self.participants:
            # Skip dead participants
            if await self._is_dead(participant):
                continue

            # Skip fled participants
            if participant.fled:
                continue

            # Check wait state
            if self._is_in_wait_state(participant):
                self.engine.broadcast_to_room(
                    self.room_id,
                    colorize(
                        f"{participant.entity_name} is recovering...",
                        "YELLOW"
                    )
                )
                continue

            # Execute auto-action
            try:
                await self._auto_action(participant)
            except Exception as e:
                logger.error(
                    "auto_action_failed",
                    participant_id=participant.entity_id,
                    error=str(e),
                    exc_info=True
                )

    async def _auto_action(self, participant: CombatParticipant) -> None:
        """Execute participant's automatic action."""
        if participant.is_npc:
            await self._npc_auto_action(participant)
        else:
            await self._player_auto_action(participant)

    async def _player_auto_action(self, player: CombatParticipant) -> None:
        """Player auto-attacks current target."""
        # Check wimpy first
        await self._check_wimpy(player)

        # Check if still in combat (might have fled from wimpy)
        if player.fled:
            return

        # Attack current target
        if player.target_id:
            await self._execute_attack(player, player.target_id)
        else:
            # No target - choose first enemy
            enemy = self._find_enemy_target(player)
            if enemy:
                player.target_id = enemy.entity_id
                await self._execute_attack(player, player.target_id)

    async def _npc_auto_action(self, npc: CombatParticipant) -> None:
        """NPC AI action."""
        npc_instance = await self._get_npc_instance(npc.entity_id)

        # Check HP threshold for wimpy
        hp_percent = npc_instance.current_hp / npc_instance.max_hp
        wimpy_threshold = 0.2  # 20%

        if hp_percent < wimpy_threshold and npc_instance.behavior != "training_dummy":
            await self.attempt_flee(npc)
            return

        # Behavior-based actions
        if npc_instance.behavior == "aggressive":
            if not npc.target_id:
                npc.target_id = self._npc_choose_target(npc)

            if npc.target_id:
                await self._execute_attack(npc, npc.target_id)
            else:
                # No valid targets
                await self.attempt_flee(npc)

        elif npc_instance.behavior == "passive":
            # Passive NPCs flee when attacked
            await self.attempt_flee(npc)

        elif npc_instance.behavior == "training_dummy":
            # Training dummies don't act
            pass

    async def _execute_attack(
        self,
        attacker: CombatParticipant,
        target_id: str
    ) -> None:
        """Execute attack action."""
        # Get target
        target = next((p for p in self.participants if p.entity_id == target_id), None)
        if not target or target.fled:
            return

        # Get attacker attributes
        dex = await get_participant_attribute(attacker, "dexterity")
        strength = await get_participant_attribute(attacker, "strength")

        dex_mod = (dex - 10) // 2
        str_mod = (strength - 10) // 2

        # To-hit roll: d20 + DEX
        to_hit = random.randint(1, 20)
        is_critical = (to_hit == 20)
        is_fumble = (to_hit == 1)
        final_to_hit = to_hit + dex_mod

        # Target defense
        target_dex = await get_participant_attribute(target, "dexterity")
        target_dex_mod = (target_dex - 10) // 2
        target_defense = 10 + target_dex_mod

        if target.is_defending:
            target_defense += 5

        # Check hit
        if is_fumble or (final_to_hit < target_defense and not is_critical):
            # Miss
            self.engine.broadcast_to_room(
                self.room_id,
                colorize(
                    f"{attacker.entity_name} attacks {target.entity_name} but misses! (Rolled {final_to_hit} vs AC {target_defense})",
                    "YELLOW"
                )
            )
            return

        # Hit - calculate damage
        damage_dice = 1 if not is_critical else 2
        damage = sum(random.randint(1, 6) for _ in range(damage_dice))
        damage += str_mod
        damage = max(1, damage)

        # Apply damage
        new_hp = await apply_damage_to_participant(target, damage)

        # Track damage for XP
        self._track_damage(attacker.entity_id, target_id, damage)

        # Broadcast hit
        hit_color = "YELLOW" if is_critical else "RED"
        crit_text = "CRITICAL HIT! " if is_critical else ""

        self.engine.broadcast_to_room(
            self.room_id,
            colorize(
                f"{crit_text}{attacker.entity_name} hits {target.entity_name} for {damage} damage! ({target.entity_name}: {new_hp} HP)",
                hit_color
            )
        )

        # Check death
        if new_hp <= 0:
            await self._handle_death(target)
        else:
            # Check wimpy for target
            await self._check_wimpy(target)

    def _should_continue_combat(self) -> bool:
        """Check if combat should continue."""
        # Count active participants (not fled, not dead)
        active = [p for p in self.participants if not p.fled and not self._is_dead_sync(p)]

        if len(active) <= 1:
            return False

        # Check if any "sides" remain (simple: NPCs vs Players)
        has_players = any(not p.is_npc for p in active)
        has_npcs = any(p.is_npc for p in active)

        # Combat continues if both sides have active participants
        return has_players and has_npcs

    async def end_combat(self) -> None:
        """End combat and cleanup."""
        if self.state == CombatState.ENDED:
            return

        self.state = CombatState.ENDED

        # Cancel round task
        if self.round_task:
            self.round_task.cancel()
            try:
                await self.round_task
            except asyncio.CancelledError:
                pass

        # Clear combat state for all participants
        for participant in self.participants:
            if not participant.is_npc:
                # Clear player combat state in DB
                async with get_session() as session:
                    char = await session.execute(
                        select(Character).where(Character.id == UUID(participant.entity_id))
                    )
                    character = char.scalar_one_or_none()
                    if character:
                        character.combat_state = None
                        character.combat_target_id = None
                        await session.commit()

        # Broadcast combat end
        self.engine.broadcast_to_room(
            self.room_id,
            colorize("\n=== Combat has ended ===\n", "GREEN")
        )

        logger.info(
            "combat_ended",
            room_id=self.room_id,
            rounds=self.round_number
        )
```

---

## Database Changes

### Character Model Additions

```python
# File: src/waystone/database/models/character.py

class Character(Base, TimestampMixin):
    """Player character model."""

    # ... existing fields ...

    # Combat state tracking
    combat_state: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
        comment="Current combat state: 'active', 'waiting', or null if not in combat",
    )

    combat_target_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
        comment="Entity ID of current combat target (character or NPC)",
    )

    wimpy_threshold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Auto-flee when HP% drops below this value (0-99, 0=disabled)",
    )

    wait_state_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Timestamp when wait state (skill lag) expires",
    )

    skill_cooldowns: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Skill cooldowns: {skill_name: next_use_iso_timestamp}",
    )
```

### Migration Script

```python
# File: migrations/versions/xxxx_add_combat_fields.py

"""Add combat state tracking fields to Character model.

Revision ID: xxxx
Revises: yyyy
Create Date: 2025-12-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'xxxx'
down_revision = 'yyyy'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Add combat fields to characters table."""
    op.add_column(
        'characters',
        sa.Column('combat_state', sa.String(20), nullable=True, comment='Current combat state')
    )
    op.add_column(
        'characters',
        sa.Column('combat_target_id', sa.String(100), nullable=True, comment='Entity ID of combat target')
    )
    op.add_column(
        'characters',
        sa.Column('wimpy_threshold', sa.Integer(), nullable=False, server_default='0', comment='Auto-flee HP threshold')
    )
    op.add_column(
        'characters',
        sa.Column('wait_state_until', sa.DateTime(timezone=True), nullable=True, comment='Wait state expiration')
    )
    op.add_column(
        'characters',
        sa.Column('skill_cooldowns', postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default='{}', comment='Skill cooldowns')
    )

def downgrade() -> None:
    """Remove combat fields from characters table."""
    op.drop_column('characters', 'skill_cooldowns')
    op.drop_column('characters', 'wait_state_until')
    op.drop_column('characters', 'wimpy_threshold')
    op.drop_column('characters', 'combat_target_id')
    op.drop_column('characters', 'combat_state')
```

---

## Migration Strategy

### Phase 1: Parallel System Development

**Objective:** Build unified combat system alongside existing PvP/NPC systems without breaking functionality.

**Steps:**

1. **Create new module:** `src/waystone/game/systems/unified_combat.py`
   - Implement `Combat`, `CombatParticipant`, combat mechanics
   - No changes to existing `combat.py` or `npc_combat.py`

2. **Add feature flag:** `ENABLE_UNIFIED_COMBAT = False` in settings
   - Old commands route to old system when flag is False
   - New commands (or flag=True) route to new system

3. **Database migration:** Run Alembic migration to add Character fields
   - Non-breaking: All new fields nullable or have defaults
   - Old system ignores new fields

**Testing:**
- ✅ Old PvP combat still works with flag=False
- ✅ Old NPC combat still works with flag=False
- ✅ New unified combat functional with flag=True
- ✅ Database migration applies without errors

**Timeline:** 2-3 days

---

### Phase 2: Feature Parity Testing

**Objective:** Ensure unified system matches old system functionality.

**Steps:**

1. **PvP feature parity:**
   - Initiative rolls match old system
   - Damage calculations identical
   - Flee mechanics equivalent
   - Death handling matches

2. **NPC feature parity:**
   - NPC attacks work like old attack_npc()
   - XP awards match old system
   - Loot generation compatible
   - Respawn timing preserved

3. **Parallel testing:**
   - Run both systems on test server
   - Compare combat outcomes
   - Validate XP, damage, death handling

**Testing:**
- ✅ 10 PvP combats in each system, compare results
- ✅ 20 NPC combats in each system, compare XP/loot
- ✅ Edge cases: disconnects, multi-combatant, flee spam

**Timeline:** 1-2 days

---

### Phase 3: Gradual Rollout

**Objective:** Replace old systems with unified combat.

**Steps:**

1. **Enable unified combat for NPCs:**
   - Set `ENABLE_UNIFIED_COMBAT = True` for NPC attacks only
   - PvP still uses old system
   - Monitor for 24 hours

2. **Enable unified combat for PvP:**
   - Route all combat to unified system
   - Deprecate old `combat.py` (don't delete yet)
   - Monitor for 48 hours

3. **Cleanup old code:**
   - Archive `combat.py` and `npc_combat.py` to `deprecated/`
   - Remove feature flag
   - Update documentation

**Testing:**
- ✅ Monitor error logs for combat exceptions
- ✅ Player feedback: combat feels responsive
- ✅ Performance: no degradation in round timing

**Timeline:** 1 week (with monitoring)

---

### Phase 4: Advanced Features

**Objective:** Add new features only possible with unified system.

**Steps:**

1. **Implement combat skills:**
   - Bash, kick, disarm, trip commands
   - Wait states and cooldowns
   - Skill progression integration

2. **Implement wimpy:**
   - Auto-flee threshold command
   - Persistence in Character model
   - Testing with various thresholds

3. **Implement multi-combatant:**
   - Target switching
   - Damage tracking for XP share
   - 5+ participant combat testing

**Testing:**
- ✅ Each skill tested with success/failure cases
- ✅ Wimpy triggers at correct HP thresholds
- ✅ Multi-combatant XP sharing accurate

**Timeline:** 2-3 days

---

### Rollback Plan

If critical issues arise:

1. **Immediate rollback:**
   - Set `ENABLE_UNIFIED_COMBAT = False`
   - Old system resumes within 1 minute (config change)

2. **Data integrity:**
   - New Character fields don't affect old system
   - No data loss from rollback

3. **Fix and retry:**
   - Identify issue in unified system
   - Fix in development
   - Re-test and redeploy

---

## Test Scenarios

### Unit Tests

#### Test Suite: Combat Participant

```python
# File: tests/unit/test_combat_participant.py

import pytest
from waystone.game.systems.unified_combat import CombatParticipant, get_participant_hp

@pytest.mark.asyncio
async def test_create_player_participant(test_character):
    """Test creating a participant from a player character."""
    participant = CombatParticipant(
        entity_id=str(test_character.id),
        entity_name=test_character.name,
        is_npc=False,
        initiative=15,
    )

    assert participant.entity_id == str(test_character.id)
    assert participant.is_npc is False
    assert participant.initiative == 15
    assert participant.target_id is None

@pytest.mark.asyncio
async def test_get_participant_hp_player(test_character):
    """Test getting HP for player participant."""
    participant = CombatParticipant(
        entity_id=str(test_character.id),
        entity_name=test_character.name,
        is_npc=False,
        initiative=10,
    )

    current_hp, max_hp = await get_participant_hp(participant)
    assert current_hp == test_character.current_hp
    assert max_hp == test_character.max_hp

@pytest.mark.asyncio
async def test_apply_damage_to_player(test_character):
    """Test applying damage to player participant."""
    participant = CombatParticipant(
        entity_id=str(test_character.id),
        entity_name=test_character.name,
        is_npc=False,
        initiative=10,
    )

    initial_hp = test_character.current_hp
    new_hp = await apply_damage_to_participant(participant, 5)

    assert new_hp == initial_hp - 5
    # Verify database updated
    assert test_character.current_hp == new_hp
```

#### Test Suite: Combat Mechanics

```python
# File: tests/unit/test_combat_mechanics.py

import pytest
from waystone.game.systems.unified_combat import Combat, CombatState

@pytest.mark.asyncio
async def test_combat_initialization(test_room, test_engine):
    """Test combat initializes correctly."""
    combat = Combat(test_room.id, test_engine)

    assert combat.room_id == test_room.id
    assert combat.state == CombatState.SETUP
    assert combat.round_number == 0
    assert len(combat.participants) == 0

@pytest.mark.asyncio
async def test_roll_initiative(test_character, test_engine, test_room):
    """Test initiative rolling."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))

    participant = combat.participants[0]
    assert participant.initiative >= 1  # d20 + DEX mod (min 1)
    assert participant.initiative <= 30  # d20(20) + max DEX mod(10)

@pytest.mark.asyncio
async def test_initiative_sorting(test_character, test_character2, test_engine, test_room):
    """Test participants sorted by initiative."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.add_participant(str(test_character2.id))

    await combat.start()

    # Verify sorted high to low
    for i in range(len(combat.participants) - 1):
        assert combat.participants[i].initiative >= combat.participants[i + 1].initiative
```

#### Test Suite: Flee Mechanics

```python
# File: tests/unit/test_flee.py

import pytest
from waystone.game.systems.unified_combat import Combat

@pytest.mark.asyncio
async def test_flee_success(test_character, test_npc, test_engine, test_room):
    """Test successful flee."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.start()

    participant = combat.participants[0]

    # Mock d20 roll to guarantee success (roll 20)
    with patch('random.randint', return_value=20):
        success = await combat.attempt_flee(participant)

    assert success is True
    assert participant.fled is True
    assert participant not in combat.participants

@pytest.mark.asyncio
async def test_flee_failure(test_character, test_npc, test_engine, test_room):
    """Test failed flee."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.start()

    participant = combat.participants[0]

    # Mock d20 roll to guarantee failure (roll 1)
    with patch('random.randint', return_value=1):
        success = await combat.attempt_flee(participant)

    assert success is False
    assert participant.fled is False
    assert participant in combat.participants
    assert participant.wait_state_until is not None
```

---

### Integration Tests

#### Test Suite: Combat Flow

```python
# File: tests/integration/test_combat_flow.py

import pytest
import asyncio
from waystone.game.systems.unified_combat import Combat, CombatState

@pytest.mark.asyncio
async def test_full_combat_npc_death(test_character, test_npc_instance, test_engine, test_room):
    """Test complete combat flow ending in NPC death."""
    # Start combat
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.add_npc_participant(test_npc_instance)
    await combat.start()

    assert combat.state == CombatState.ACTIVE

    # Mock high damage to kill NPC in one round
    test_character.strength = 20  # +5 modifier
    test_npc_instance.current_hp = 3  # Low HP

    # Execute one round
    await combat._execute_round()

    # Verify NPC died and combat ended
    assert test_npc_instance.current_hp <= 0
    assert combat.state == CombatState.ENDED

@pytest.mark.asyncio
async def test_automatic_round_timing(test_character, test_npc_instance, test_engine, test_room):
    """Test 3-second automatic rounds."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.add_npc_participant(test_npc_instance)
    await combat.start()

    # Record round numbers over time
    rounds_at_times = []
    for _ in range(3):
        rounds_at_times.append(combat.round_number)
        await asyncio.sleep(3.1)  # Slightly over 3 seconds

    # Should have incremented each time
    assert rounds_at_times[0] < rounds_at_times[1] < rounds_at_times[2]

    # Cleanup
    await combat.end_combat()
```

#### Test Suite: Multi-Combatant

```python
# File: tests/integration/test_multi_combatant.py

@pytest.mark.asyncio
async def test_multiple_players_vs_npc(
    test_character,
    test_character2,
    test_npc_instance,
    test_engine,
    test_room
):
    """Test two players fighting one NPC."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.add_participant(str(test_character2.id))
    await combat.add_npc_participant(test_npc_instance)
    await combat.start()

    assert len(combat.participants) == 3

    # Both players attack NPC
    combat.participants[0].target_id = test_npc_instance.id
    combat.participants[1].target_id = test_npc_instance.id

    # Execute round
    await combat._execute_round()

    # Verify damage tracking for XP share
    assert test_npc_instance.id in combat.damage_tracking
    damage_records = combat.damage_tracking[test_npc_instance.id]
    assert len(damage_records) >= 1  # At least one hit

@pytest.mark.asyncio
async def test_xp_sharing(test_character, test_character2, test_npc_instance, test_engine, test_room):
    """Test XP shared between multiple attackers."""
    combat = Combat(test_room.id, test_engine)
    await combat.add_participant(str(test_character.id))
    await combat.add_participant(str(test_character2.id))
    await combat.add_npc_participant(test_npc_instance)
    await combat.start()

    # Mock damage tracking
    combat.damage_tracking[test_npc_instance.id] = [
        DamageRecord(participant_id=str(test_character.id), total_damage=10),
        DamageRecord(participant_id=str(test_character2.id), total_damage=10),
    ]

    initial_xp1 = test_character.experience
    initial_xp2 = test_character2.experience

    # Kill NPC
    test_npc_instance.current_hp = 0
    await combat._handle_npc_death(test_npc_instance)

    # Both should receive XP (50/50 split)
    assert test_character.experience > initial_xp1
    assert test_character2.experience > initial_xp2
    assert test_character.experience == test_character2.experience  # Equal damage = equal XP
```

---

### Manual Test Scenarios

#### Scenario 1: Basic NPC Combat

**Setup:**
- Player in room with aggressive NPC (level 1 rat)
- Player at full HP

**Steps:**
1. Player types: `kill rat`
2. Wait 3 seconds
3. Observe round messages
4. Wait until combat ends (death or flee)

**Expected:**
- ✅ "Round 1" message appears
- ✅ Player auto-attacks rat each round
- ✅ Rat counterattacks player each round
- ✅ Combat continues until rat dies
- ✅ Player receives XP message
- ✅ Rat corpse/loot appears

---

#### Scenario 2: Flee from Combat

**Setup:**
- Player in combat with NPC
- Player at moderate HP (50%)

**Steps:**
1. Player types: `flee`
2. Observe result message
3. If failed, wait 1 second and retry

**Expected:**
- ✅ ~60% success rate (DEX dependent)
- ✅ On success: Player moves to random adjacent room
- ✅ On failure: "You try to flee but fail!" message
- ✅ On failure: 1-second cooldown before next flee
- ✅ Combat ends when flee succeeds

---

#### Scenario 3: Wimpy Auto-Flee

**Setup:**
- Player not in combat
- Player types: `wimpy 30`

**Steps:**
1. Start combat with NPC
2. Let NPC damage player below 30% HP
3. Observe automatic flee attempt

**Expected:**
- ✅ "[Name] tries to flee (wimpy)!" message when HP < 30%
- ✅ Automatic flee attempt (can succeed or fail)
- ✅ If failed, retry next round when HP still low
- ✅ `score` command shows "Wimpy: 30%"

---

#### Scenario 4: Combat Skills

**Setup:**
- Player in combat with NPC
- Player has bash skill

**Steps:**
1. Player types: `bash rat`
2. Observe result
3. Wait 2 rounds (6 seconds)
4. Try `bash rat` again

**Expected:**
- ✅ Success: "You bash the rat! (X damage) The rat is knocked down!"
- ✅ Player cannot act for 2 rounds (wait state)
- ✅ Second bash attempt fails with "Bash is on cooldown (Xs)"
- ✅ After 15 seconds, bash available again

---

#### Scenario 5: Multi-Combatant

**Setup:**
- Two players in same room
- One aggressive NPC

**Steps:**
1. Player 1 types: `kill orc`
2. Player 2 types: `kill orc`
3. Observe combat

**Expected:**
- ✅ Both players join combat
- ✅ Initiative order shown
- ✅ Each round: both players attack, orc counterattacks
- ✅ Orc targets last attacker
- ✅ When orc dies, both players receive XP (split by damage)

---

## Implementation Phases

### Phase 1: Core Combat Loop (2-3 days)

**Objective:** Unified combat system with automatic 3-second rounds.

**Deliverables:**
- [x] `CombatParticipant` dataclass (player + NPC support)
- [x] `Combat` class with round loop
- [x] Initiative rolling and sorting
- [x] Basic attack mechanics (to-hit, damage, HP tracking)
- [x] Combat start/end logic
- [x] Round timer (3-second asyncio loop)

**Acceptance Criteria:**
- ✅ `kill npc` starts combat with automatic rounds
- ✅ Combat continues every 3 seconds until end
- ✅ Players and NPCs can participate
- ✅ Basic attacks work with d20 + DEX vs AC

**Testing:**
- Unit tests: CombatParticipant, initiative, attack mechanics
- Integration test: Full combat from start to NPC death

---

### Phase 2: NPC Integration (1-2 days)

**Objective:** NPCs counterattack and use AI behavior.

**Deliverables:**
- [x] NPC auto-action logic
- [x] NPC AI: aggressive, passive, training_dummy behaviors
- [x] NPC target selection (prioritize last_hit_by)
- [x] NPC wimpy flee (20% HP threshold)
- [x] Integration with existing NPCInstance system

**Acceptance Criteria:**
- ✅ Aggressive NPCs counterattack every round
- ✅ Passive NPCs flee when attacked
- ✅ NPCs flee when HP < 20%
- ✅ Training dummies don't counterattack

**Testing:**
- Unit tests: NPC AI logic, target selection
- Integration test: Attack aggressive NPC, verify counterattack
- Integration test: Reduce NPC HP to 15%, verify flee

---

### Phase 3: Advanced Features (2-3 days)

**Objective:** Flee mechanics, wimpy, combat skills, multi-combatant.

**Deliverables:**
- [x] Flee command with success/failure (d20+DEX vs DC 12)
- [x] Wimpy auto-flee threshold
- [x] Combat skills: bash, kick, disarm, trip
- [x] Wait states and cooldowns
- [x] Target switching
- [x] Damage tracking for XP sharing
- [x] Multi-combatant support

**Acceptance Criteria:**
- ✅ Flee succeeds ~60% of time at DEX 10
- ✅ Wimpy triggers auto-flee at threshold
- ✅ Bash skill: knockdown effect, 2-round lag, 15s cooldown
- ✅ Multiple players can attack same NPC
- ✅ XP split proportional to damage

**Testing:**
- Unit tests: Flee roll, wimpy check, skill mechanics
- Integration test: Multi-player combat with XP sharing
- Manual test: All combat skills

---

### Phase 4: Migration & Testing (1-2 days)

**Objective:** Migrate from old systems, polish, bug fixes.

**Deliverables:**
- [x] Database migration (Character combat fields)
- [x] Deprecate old combat.py and npc_combat.py
- [x] Update command routing to unified system
- [x] Feature parity validation
- [x] Performance testing (100+ combats)
- [x] Documentation updates

**Acceptance Criteria:**
- ✅ Database migration applies without errors
- ✅ All old combat functionality preserved
- ✅ No performance degradation
- ✅ Zero data loss during migration

**Testing:**
- Regression test: PvP combat matches old behavior
- Regression test: NPC combat matches old XP/loot
- Stress test: 100 simultaneous combats
- Manual test: All scenarios from Test Scenarios section

---

## Appendix: Classic MUD Combat Reference

### ROM MUD Combat Constants

```c
// ROM 2.4 combat.c
#define PULSE_VIOLENCE    (3 * PULSE_PER_SECOND)  // 3-second combat rounds

// Damage message table
const char *attack_table[] = {
    "hit",      // 1-4 damage
    "slash",    // 5-8
    "pound",    // 9-12
    "maul",     // 13-16
    "decimate", // 17-20
    "devastate",// 21-24
    "MASSACRE", // 25-28
    "OBLITERATE"// 29+
};

// Position affects damage
#define POS_DEAD        0  // Can't act
#define POS_MORTAL      1  // Near death
#define POS_INCAP       2  // Incapacitated
#define POS_STUNNED     3  // Stunned, can't act
#define POS_SLEEPING    4  // -4 AC penalty
#define POS_RESTING     5  // Regenerating
#define POS_SITTING     6  // -2 AC penalty
#define POS_FIGHTING    7  // In combat
#define POS_STANDING    8  // Normal
```

### CircleMUD Combat Loop

```c
// CircleMUD combat.c
void perform_violence(void) {
    struct char_data *ch;

    // Iterate all fighting characters
    for (ch = combat_list; ch; ch = next_combat_list) {
        next_combat_list = ch->next_fighting;

        if (FIGHTING(ch) == NULL || IN_ROOM(ch) != IN_ROOM(FIGHTING(ch))) {
            stop_fighting(ch);
            continue;
        }

        if (IS_NPC(ch)) {
            // NPC AI chooses action
            if (GET_MOB_WAIT(ch) > 0) {
                GET_MOB_WAIT(ch)--;
                continue;
            }

            npc_combat_ai(ch);
        }

        // Execute attack
        hit(ch, FIGHTING(ch), TYPE_UNDEFINED);

        // Check if anyone died
        if (GET_POS(ch) == POS_DEAD)
            continue;
    }
}
```

### DikuMUD To-Hit Calculation

```c
// DikuMUD fight.c
int calculate_thac0(struct char_data *ch) {
    int thac0;

    // Base THAC0 by class and level
    thac0 = thac0_table[GET_CLASS(ch)][GET_LEVEL(ch)];

    // Strength bonus for warriors
    if (GET_CLASS(ch) == CLASS_WARRIOR)
        thac0 -= str_app[GET_STR(ch)].tohit;

    // Dexterity bonus for thieves
    if (GET_CLASS(ch) == CLASS_THIEF)
        thac0 -= dex_app[GET_DEX(ch)].reaction;

    return thac0;
}

bool check_hit(struct char_data *attacker, struct char_data *victim) {
    int roll = number(1, 20);
    int thac0 = calculate_thac0(attacker);
    int victim_ac = GET_AC(victim);

    // Natural 20 always hits, natural 1 always misses
    if (roll == 20)
        return TRUE;
    if (roll == 1)
        return FALSE;

    // THAC0: lower is better
    return (roll + thac0 >= 20 - victim_ac);
}
```

---

## Document Change Log

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-10 | Atlas | Initial PRD creation |

---

**END OF DOCUMENT**
