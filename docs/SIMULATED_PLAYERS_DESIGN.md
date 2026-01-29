# Simulated Players Architecture Design

**Author**: Architect Agent
**Date**: 2025-01-28
**Status**: Design Document (Refined with Codebase Review)
**Depends On**: waystone.agent, npc_poster system, game engine

---

## 0. Existing Systems Review

*This section documents what already exists in the Waystone codebase that this design should integrate with or reuse.*

### 0.1 Tick System (CONFIRMED)

The game engine has a fully functional tick system in `src/waystone/game/engine.py` via `_periodic_cleanup()`:

```python
# From engine.py lines 762-868
async def _periodic_cleanup(self) -> None:
    """Periodically clean up expired sessions and check for NPC respawns."""
    tick_count = 0
    while self._running:
        await asyncio.sleep(30)  # 30-second tick interval
        tick_count += 1

        # Clean up expired sessions (every 10 ticks = 5 minutes)
        if tick_count % 10 == 0:
            expired_count = self.session_manager.cleanup_expired()

        # Check for NPC respawns every tick
        respawned_count = await check_respawns(self)
        combat_respawned = await check_npc_respawns(self)

        # Regenerate HP
        players_healed = await regenerate_all_players(self)
        npcs_healed = await regenerate_npcs(self)

        # NPC bulletin board posts (every 60 ticks = 30 minutes)
        if tick_count % 60 == 0:
            posts_created = await check_npc_posts()
```

**Integration Point**: Simulated player ticks should be added here, similar to NPC posts:
```python
# Simulated player actions (every 2 ticks = 60 seconds)
if tick_count % 2 == 0:
    await sim_manager.tick(self)
```

### 0.2 NPC Poster System (Reusable Pattern)

Located in `src/waystone/game/systems/npc_poster.py`, this system provides an excellent template for simulated player chat:

```python
@dataclass
class NPCPostTemplate:
    subject_patterns: list[str]
    body_patterns: list[str]

    def generate_subject(self, **kwargs) -> str:
        pattern = random.choice(self.subject_patterns)
        return pattern.format(**kwargs)

    def generate_body(self, **kwargs) -> str:
        pattern = random.choice(self.body_patterns)
        return pattern.format(**kwargs)

@dataclass
class NPCPostingSchedule:
    npc_template_id: str
    npc_name: str
    board_id: str
    min_interval_hours: int = 24
    max_interval_hours: int = 72
    active_hours: tuple[int, int] = (6, 22)
    probability: float = 0.3
    templates: list[NPCPostTemplate]
```

**Reusable Patterns**:
- Template-based message generation with variable substitution
- Active hours scheduling
- Probability-based action triggers
- Per-NPC tracking with `_npc_post_state` dict

### 0.3 AI Agent System (External Telnet Connection)

Located in `src/waystone/agent/agent.py`, this is a sophisticated LLM-based agent that connects via telnet:

```python
@dataclass
class AgentConfig:
    host: str = "localhost"
    port: int = 1337
    username: str = ""
    password: str = ""
    character_name: str = ""
    use_haiku: bool = True
    action_delay: float = 2.0

class GoalType(Enum):
    EXPLORE = "explore"
    GATHER_MONEY = "gather_money"
    LEVEL_UP = "level_up"
    SOCIAL = "social"
    QUEST = "quest"
    TRADE = "trade"
    IDLE = "idle"
```

**Key Difference from Simulated Players**: The existing agent connects externally via telnet and uses LLM inference. Simulated players should integrate server-side using the CommandContext pattern for efficiency.

### 0.4 NPC Combat System (Instance Tracking Pattern)

Located in `src/waystone/game/systems/npc_combat.py`, provides the instance tracking pattern:

```python
@dataclass
class NPCInstance:
    id: str  # Unique instance ID
    template_id: str  # Reference to template
    room_id: str
    current_hp: int
    max_hp: int
    name: str
    level: int
    behavior: str = "passive"  # aggressive, passive, training_dummy
    is_alive: bool = True

# Global tracking
_npc_instances: dict[str, dict[str, NPCInstance]] = {}
_pending_respawns: list[tuple[datetime, str, str]] = []
```

**Reusable Patterns**:
- Template + Instance separation (config vs runtime state)
- Global dict tracking by room_id
- Respawn scheduling via pending list
- `spawn_npc()`, `get_npcs_in_room()` patterns

### 0.5 Command Execution System (CRITICAL)

Located in `src/waystone/game/commands/base.py`:

```python
@dataclass
class CommandContext:
    session: "Session"
    connection: "Connection"
    engine: "GameEngine"
    args: list[str]
    raw_input: str

class Command(ABC):
    name: str = ""
    aliases: list[str] = []
    help_text: str = ""
    min_args: int = 0
    requires_character: bool = True

    @abstractmethod
    async def execute(self, ctx: CommandContext) -> None:
        pass
```

**Design Implication**: Simulated players MUST execute commands through this system to maintain game consistency. The `SimulatedCommandContext` in the original design is correct.

### 0.6 Bulletin Board System

Located in `src/waystone/game/systems/bulletin.py`, the `BoardManager` provides:
- `post_npc_message()` - Already handles non-player posts
- Template-based message creation
- Read tracking per character

**Integration Point**: Simulated players can use `post_npc_message()` or post as real characters.

### 0.7 Session and Connection Management

The existing `Session` class tracks:
- `character_id: UUID | None`
- `state: SessionState` (PRE_AUTH, AUTHENTICATED, PLAYING)
- `current_board: str | None`

Simulated players will need a lightweight `SimulatedSession` that satisfies the `Session` interface.

### 0.8 Architecture Alignment Matrix

| Original Design Assumption | Reality in Codebase | Adjustment Needed |
|---------------------------|---------------------|-------------------|
| 30-second tick exists | ✅ Confirmed in `_periodic_cleanup()` | None |
| Can hook into game loop | ✅ Pattern exists (NPC posts) | Add sim tick call |
| CommandContext for execution | ✅ Confirmed in `base.py` | Create SimulatedCommandContext |
| Template-based chat | ✅ Pattern in `npc_poster.py` | Reuse NPCPostTemplate pattern |
| Instance tracking | ✅ Pattern in `npc_combat.py` | Follow same dict structure |
| External agent exists | ✅ LLM-based telnet agent | Different purpose, don't integrate |
| Real Character records | ✅ Character model exists | Add `is_simulated` flag |

---

## 1. System Overview

### 1.1 Problem Statement

Solo play in Waystone MUD feels empty. Even with NPCs present, the world lacks the dynamic, unpredictable energy that comes from other players exploring, chatting, and interacting with the game.

### 1.2 Proposed Solution

Create a **Simulated Player System** that spawns 2-4 virtual player characters exhibiting distinct Bartle player type behaviors. Unlike the sophisticated `waystone.agent` (which uses LLM-based decision making), these simulated players use lightweight **Behavior Trees** with templated actions and weighted randomness.

### 1.3 Design Principles

1. **Feel Real, Not Perfect**: Simulated players should make "human" decisions - occasionally suboptimal, with personality-driven quirks
2. **Lightweight Execution**: No LLM calls - pure rule-based behavior with randomized templates
3. **Integrated, Not Intrusive**: Use existing game systems (commands, rooms, chat) rather than bypassing them
4. **Observable Presence**: Players should see simulated players in `who`, room descriptions, and chat
5. **Distinct Personalities**: Each Bartle type behaves noticeably differently

### 1.4 Key Insight: Players vs NPCs

The fundamental difference between simulated players and NPCs:

| Aspect | NPCs | Simulated Players |
|--------|------|-------------------|
| Purpose | Game content (quests, combat, merchants) | Ambient life (make world feel populated) |
| Location | Fixed spawn points | Roam freely like real players |
| Communication | Scripted dialogue on interaction | Proactive chat, emotes, reactions |
| Visibility | Shown as NPCs in room | Shown as players in `who` list |
| Behavior | Reactive (respond to player actions) | Proactive (initiate actions independently) |
| Persistence | Respawn on death | "Log off" and "log on" like players |

---

## 2. Architecture

### 2.1 Component Overview

```
+---------------------------+
|      Game Engine          |
|   (_periodic_cleanup)     |
+-------------+-------------+
              |
              | tick every 30s
              v
+---------------------------+
|  SimulatedPlayerManager   |
|  - manages active sims    |
|  - handles login/logout   |
|  - dispatches AI ticks    |
+-------------+-------------+
              |
              | for each active sim
              v
+---------------------------+
|   SimulatedPlayer         |
|   - personality config    |
|   - behavior tree         |
|   - state machine         |
|   - action queue          |
+-------------+-------------+
              |
              | executes via
              v
+---------------------------+
|   CommandContext (fake)   |
|   - routes through real   |
|     command system        |
+---------------------------+
```

### 2.2 Key Components

#### 2.2.1 SimulatedPlayerManager

Central coordinator that:
- Maintains pool of simulated player configurations
- Schedules "login" and "logout" based on time-of-day patterns
- Distributes game ticks to active simulated players
- Tracks global state (prevents all sims from doing same thing)

```python
# Conceptual structure
class SimulatedPlayerManager:
    sim_pool: list[SimulatedPlayerConfig]  # All possible sims
    active_sims: dict[str, SimulatedPlayer]  # Currently "online"

    async def tick(self, engine: GameEngine) -> None:
        """Called from game loop every 30 seconds."""
        await self._check_logins_logouts()
        for sim in self.active_sims.values():
            await sim.tick(engine)
```

#### 2.2.2 SimulatedPlayer

Individual simulated player instance:
- Wraps a real Character database record
- Contains behavior tree for decision making
- Maintains short-term memory (recent actions, conversations)
- Executes actions through command system

#### 2.2.3 Behavior Tree

Lightweight decision engine using priority-based selection:

```
Root (Selector)
|-- [Priority 1] Survival
|   |-- If HP < 25%: Flee or Rest
|   |-- If in combat: Fight or Flee
|
|-- [Priority 2] Social (if Socializer)
|   |-- If player in room: Greet/Chat
|   |-- If recent chat: Respond
|
|-- [Priority 3] Achievement (if Achiever)
|   |-- If quest available: Progress quest
|   |-- If can level: Train/Fight
|
|-- [Priority 4] Exploration (if Explorer)
|   |-- If unvisited exits: Move
|   |-- If interesting item: Examine
|
|-- [Priority 5] Combat (if Killer)
|   |-- If hostile nearby: Attack
|   |-- If player nearby: Challenge/Compete
|
|-- [Priority 6] Idle
    |-- Random emote
    |-- Wander
    |-- Rest
```

### 2.3 Integration Points

#### 2.3.1 Game Engine Integration

Add to `_periodic_cleanup()` in `engine.py`:

```python
# Check simulated player actions (every tick = 30 seconds)
from waystone.game.systems.simulated_players import get_sim_manager

sim_manager = get_sim_manager()
await sim_manager.tick(self)
```

#### 2.3.2 Command Execution

Simulated players execute commands through a fake `CommandContext`:

```python
class SimulatedCommandContext:
    """Mimics CommandContext for simulated player command execution."""

    def __init__(self, sim: SimulatedPlayer, engine: GameEngine):
        self.session = SimulatedSession(sim)  # Fake session
        self.connection = SimulatedConnection(sim)  # Captures output
        self.engine = engine
```

#### 2.3.3 Presence in `who` List

Modify `WhoCommand` to include simulated players:

```python
# In info.py WhoCommand.execute()
sim_manager = get_sim_manager()
for sim in sim_manager.get_active():
    # Append to player list with marker (or not, for immersion)
    players.append(sim.character_name)
```

#### 2.3.4 Room Presence

Simulated players added to `room.players` set just like real players, so they appear in room descriptions and can be interacted with.

---

## 3. Bartle Type Implementation

### 3.1 Achiever ("Grindmaster")

**Core Drive**: Progress, levels, completion

**Behavior Weights**:
- Combat (hostile NPCs): 40%
- Quest progression: 30%
- Training/skills: 20%
- Social: 10%

**Distinctive Actions**:
```python
ACHIEVER_CHAT_TEMPLATES = [
    "Finally hit level {level}!",
    "Anyone know where to find {quest_item}?",
    "Just cleared {area}, decent XP.",
    "LFG for {difficult_area}",
    "How much XP to {next_level}?",
]

ACHIEVER_EMOTES = [
    "checks their stats thoughtfully",
    "counts their coins",
    "polishes their {equipped_weapon}",
    "studies a tattered map",
]
```

**Movement Pattern**: Purposeful - heads toward known combat/quest areas, rarely backtracks

### 3.2 Explorer ("Wanderer")

**Core Drive**: Discovery, secrets, understanding

**Behavior Weights**:
- Movement to unvisited rooms: 50%
- Examine everything: 25%
- Read boards/signs: 15%
- Social: 10%

**Distinctive Actions**:
```python
EXPLORER_CHAT_TEMPLATES = [
    "Has anyone been to {obscure_room}?",
    "Found a hidden path near {landmark}!",
    "What's behind the {mysterious_door}?",
    "This area feels different...",
    "I wonder what happens if you {unusual_action}",
]

EXPLORER_EMOTES = [
    "peers curiously at the surroundings",
    "runs their hand along the wall",
    "looks up at the ceiling thoughtfully",
    "examines something on the ground",
]
```

**Movement Pattern**: Breadth-first - prefers unvisited exits, interested in dead ends

### 3.3 Socializer ("Chatterbox")

**Core Drive**: Connection, conversation, community

**Behavior Weights**:
- Chat/emote when players present: 50%
- Help other players: 20%
- Hang out in social areas: 20%
- Light exploration: 10%

**Distinctive Actions**:
```python
SOCIALIZER_CHAT_TEMPLATES = [
    "Hey {player_name}! How's it going?",
    "Anyone need help with anything?",
    "lol that's great",
    "Welcome to Waystone, {new_player}!",
    "This is a great spot to hang out",
    "brb getting snacks",
]

SOCIALIZER_EMOTES = [
    "waves at everyone",
    "settles in for a chat",
    "laughs warmly",
    "nods in agreement",
    "offers a friendly smile",
]
```

**Movement Pattern**: Social gravity - gravitates toward rooms with other players, stays in common areas

### 3.4 Killer ("Challenger")

**Core Drive**: Competition, dominance, PvP

**Behavior Weights**:
- Combat (any valid target, **including real players**): 45%
- Competitive chat: 25%
- Patrol combat areas: 20%
- Boast about victories: 10%

**IMPORTANT**: Killer types should initiate PvP combat with real players to create competitive dynamics. This requires proper consent/flag checking based on game PvP rules.

**Distinctive Actions**:
```python
KILLER_CHAT_TEMPLATES = [
    "Anyone want to duel?",
    "Just took down {npc} in {seconds} seconds",
    "This area is mine now",
    "{player_name} think you can take me?",
    "GG easy",
    "Who's next?",
]

KILLER_EMOTES = [
    "cracks their knuckles menacingly",
    "eyes everyone in the room",
    "tests the edge of their blade",
    "stretches, ready for action",
]
```

**Movement Pattern**: Predatory - moves toward combat areas, follows players occasionally

---

## 4. AI/Behavior Patterns

### 4.1 Decision Making (No LLM)

Each tick, the behavior tree evaluates conditions and selects an action:

```python
class BehaviorTree:
    def evaluate(self, context: SimContext) -> Action | None:
        """Return highest-priority valid action."""
        for node in self.nodes:  # Ordered by priority
            if node.condition(context):
                return node.select_action(context)
        return IdleAction()
```

### 4.2 Action Selection with Personality

Actions are selected using weighted randomness based on Bartle type:

```python
def select_action(self, context: SimContext) -> Action:
    """Select action based on personality weights."""
    available = self.get_available_actions(context)
    weights = self.personality.get_weights(available)
    return random.choices(available, weights=weights)[0]
```

### 4.3 State Machine

Each simulated player has a simple state machine:

```
IDLE --> EXPLORING --> IDLE
  |          |
  v          v
COMBAT <--> FLEEING
  |
  v
RESTING --> IDLE
  |
  v
SOCIALIZING --> IDLE
```

### 4.4 Short-Term Memory

Prevents repetitive/robotic behavior:

```python
class SimMemory:
    recent_rooms: deque[str]  # Last 10 rooms (avoid backtracking)
    recent_actions: deque[str]  # Last 5 actions (avoid repetition)
    recent_chats: deque[str]  # Last 3 chat messages (context)
    last_interaction: dict[str, datetime]  # Track who we talked to
```

### 4.5 Timing and Delays

Simulated players don't act instantly - they have human-like delays:

```python
class ActionTiming:
    min_action_delay: float = 3.0  # Minimum seconds between actions
    max_action_delay: float = 15.0  # Maximum seconds between actions
    typing_delay_per_char: float = 0.05  # Simulate typing speed

    # Bartle-specific modifiers
    achiever_speed_modifier: float = 0.8  # Achievers act faster
    socializer_speed_modifier: float = 1.2  # Socializers take time
```

---

## 5. Data Models

### 5.1 SimulatedPlayerConfig

Stored configuration for a simulated player (YAML or database):

```python
@dataclass
class SimulatedPlayerConfig:
    """Configuration for a simulated player personality."""

    # Identity
    id: str  # Unique ID (e.g., "sim_achiever_01")
    name: str  # Character name (e.g., "Korvin")
    background: CharacterBackground

    # Bartle Type
    bartle_type: BartleType  # ACHIEVER, EXPLORER, SOCIALIZER, KILLER

    # Behavior weights (override defaults)
    behavior_weights: dict[str, float] = field(default_factory=dict)

    # Personality traits
    chattiness: float = 0.5  # 0-1, how often they chat
    helpfulness: float = 0.5  # 0-1, how likely to help others
    aggression: float = 0.5  # 0-1, how combat-focused
    curiosity: float = 0.5  # 0-1, how exploration-focused

    # Schedule
    active_hours: tuple[int, int] = (8, 22)  # When they're "online"
    session_duration_hours: tuple[int, int] = (1, 4)  # How long per session
```

### 5.2 SimulatedPlayer (Runtime)

Active simulated player state:

```python
@dataclass
class SimulatedPlayer:
    """Active simulated player instance."""

    config: SimulatedPlayerConfig
    character: Character  # Real database character

    # State
    state: SimState = SimState.IDLE
    current_goal: Goal | None = None

    # Memory
    memory: SimMemory = field(default_factory=SimMemory)

    # Timing
    last_action_time: datetime | None = None
    next_action_time: datetime | None = None

    # Session
    logged_in_at: datetime | None = None
    will_logout_at: datetime | None = None
```

### 5.3 Database Schema

Simulated players use **real Character records** but are marked:

```python
# Add to Character model
is_simulated: Mapped[bool] = mapped_column(
    Boolean,
    nullable=False,
    default=False,
    server_default="false",
    comment="Whether this is a simulated player character",
)

# Config stored separately
class SimulatedPlayerConfigDB(Base):
    """Persistent config for simulated players."""

    __tablename__ = "simulated_player_configs"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"))
    bartle_type: Mapped[str] = mapped_column(String(20))
    config_json: Mapped[dict] = mapped_column(JSON)  # Full config
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
```

---

## 6. Differences from NPCs

### 6.1 Technical Differences

| Feature | NPCs | Simulated Players |
|---------|------|-------------------|
| Data Model | `NPCTemplate` + `NPC` | `Character` + `SimulatedPlayerConfig` |
| Location | `engine.room_npcs` | `room.players` |
| Commands | Direct function calls | Through `CommandContext` |
| Chat | `dialogue` dict lookups | Template-based generation |
| Combat | `npc_combat` system | Same as real players |
| Death | Respawn timer | "Log out" and create new session |

### 6.2 Behavioral Differences

| Behavior | NPCs | Simulated Players |
|----------|------|-------------------|
| Movement | Wander within zone or stationary | Full world traversal |
| Initiative | Reactive (wait for player) | Proactive (initiate interactions) |
| Chat | On keyword trigger | Spontaneous and contextual |
| Goals | None (just exist) | Dynamic goals based on Bartle type |
| Learning | None | Remembers recent history |

### 6.3 Immersion Factors

What makes simulated players feel like players:

1. **Appear in `who` list** - NPCs don't
2. **Use chat channel** - NPCs only use `say`
3. **Have login/logout patterns** - NPCs are always there
4. **Make mistakes** - Sometimes go wrong direction, die to mobs
5. **React to real players** - Greet, help, challenge
6. **Progress over time** - Level up, get gear, complete quests
7. **Have opinions** - Comment on game content via chat

---

## 7. Sample Configurations

### 7.1 Korvin the Achiever

```yaml
id: sim_achiever_korvin
name: Korvin
background: Scholar
bartle_type: ACHIEVER

behavior_weights:
  combat: 0.4
  quests: 0.3
  training: 0.2
  social: 0.1

traits:
  chattiness: 0.3
  helpfulness: 0.4
  aggression: 0.5
  curiosity: 0.2

schedule:
  active_hours: [6, 14]  # Early bird grinder
  session_duration: [2, 6]
```

### 7.2 Lyra the Explorer

```yaml
id: sim_explorer_lyra
name: Lyra
background: Wayfarer
bartle_type: EXPLORER

behavior_weights:
  exploration: 0.5
  examine: 0.25
  reading: 0.15
  social: 0.1

traits:
  chattiness: 0.4
  helpfulness: 0.3
  aggression: 0.1
  curiosity: 0.9

schedule:
  active_hours: [10, 2]  # Night owl explorer
  session_duration: [1, 3]
```

### 7.3 Denna the Socializer

```yaml
id: sim_socializer_denna
name: Denna
background: Performer
bartle_type: SOCIALIZER

behavior_weights:
  social: 0.5
  helping: 0.2
  hangout: 0.2
  exploration: 0.1

traits:
  chattiness: 0.9
  helpfulness: 0.8
  aggression: 0.1
  curiosity: 0.3

schedule:
  active_hours: [16, 24]  # Evening socializer
  session_duration: [2, 4]
```

### 7.4 Devi the Killer

```yaml
id: sim_killer_devi
name: Devi
background: Noble
bartle_type: KILLER

behavior_weights:
  combat: 0.45
  competitive: 0.25
  patrol: 0.2
  boast: 0.1

traits:
  chattiness: 0.6
  helpfulness: 0.1
  aggression: 0.9
  curiosity: 0.2

schedule:
  active_hours: [18, 2]  # Peak hours predator
  session_duration: [1, 3]
```

---

## 8. File Structure

```
src/waystone/game/systems/
    simulated_players/
        __init__.py           # Public API
        manager.py            # SimulatedPlayerManager
        player.py             # SimulatedPlayer class
        behavior.py           # Behavior tree implementation
        personality.py        # Bartle types and traits
        templates.py          # Chat/emote templates
        memory.py             # Short-term memory
        context.py            # Fake CommandContext

data/simulated_players/
    korvin.yaml              # Achiever config
    lyra.yaml                # Explorer config
    denna.yaml               # Socializer config
    devi.yaml                # Killer config
```

---

## 9. Trade-offs and Decisions

### 9.1 Why Behavior Trees over State Machines?

Behavior trees provide:
- Natural priority ordering
- Easy to add new behaviors
- Composable and debuggable
- Industry standard for game AI

### 9.2 Why Real Characters, Not Fake Sessions?

Using real `Character` records:
- Consistent with all game systems
- Proper combat, inventory, progression
- Can be inspected by real players
- Simplifies integration

### 9.3 Why Template-Based Chat, Not LLM?

Templates are:
- Fast and predictable
- Zero cost per action
- Easy to tune personality
- Sufficient for ambient presence

LLM (like `waystone.agent`) would be:
- Expensive at scale (4 sims * many actions/hour)
- Slower response time
- Overkill for background presence

### 9.4 Why Login/Logout Simulation?

Creates the illusion of:
- Real player schedules
- Server population changes
- Natural comings and goings

Without it, simulated players would feel like always-on bots.

---

## 10. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Simulated players feel robotic | Medium | High | Varied timing, templates, mistakes |
| Performance impact | Low | Medium | Lightweight behavior trees, rate limiting |
| Confusing real players | Medium | Low | Optional [SIM] tag in admin view |
| Chat spam | Medium | Medium | Chattiness limits, cooldowns |
| Breaking game systems | Low | High | Use real CommandContext, extensive testing |

---

## 11. Success Criteria

The system is successful when:

1. A solo player feels less alone in the world
2. Simulated players are sometimes mistaken for real players
3. Each Bartle type has noticeably different behavior
4. Performance impact is negligible (<1% CPU overhead)
5. No game-breaking bugs from simulated player actions

---

## 12. Future Enhancements

Not in initial scope, but possible later:

1. **Guilds/Groups**: Simulated players form groups, do content together
2. **Economy Participation**: Buy/sell at merchants, create market activity
3. **Quest Board Interaction**: Post and take jobs on bulletin boards
4. **Reputation System**: Remember player interactions, build relationships
5. **Seasonal Behavior**: Different patterns during events/holidays
6. **LLM Upgrade Path**: Optional Haiku backend for richer conversation

---

---

## 13. Implementation Phases

This section breaks the implementation into logical, independently testable phases. Each phase builds on the previous and delivers incremental value. The Explorer Bartle type is used as the MVP proof-of-concept since exploration behavior is:
1. Simplest to implement (movement + examine)
2. Easily observable (player can watch sim move around)
3. Low risk (no combat interactions to debug)

### Phase 1: Core Infrastructure (Foundation)

**Goal**: Establish the basic framework for simulated players without any behavior logic.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    __init__.py           # Public API exports
    manager.py            # SimulatedPlayerManager skeleton
    player.py             # SimulatedPlayer class (state only)
    context.py            # SimulatedCommandContext for command execution
```

**Files to Modify**:
```
src/waystone/database/models/character.py  # Add is_simulated field
src/waystone/database/models/__init__.py   # Export if needed
alembic/versions/xxx_add_simulated_flag.py # Database migration
```

**Implementation Details**:

1. **Database Schema Change**
   ```python
   # In character.py - add field
   is_simulated: Mapped[bool] = mapped_column(
       Boolean,
       nullable=False,
       default=False,
       server_default="false",
       comment="Whether this is a simulated player character",
   )
   ```

2. **SimulatedPlayerManager** (skeleton)
   ```python
   class SimulatedPlayerManager:
       """Manages simulated player lifecycle and ticks."""

       def __init__(self) -> None:
           self.active_sims: dict[str, SimulatedPlayer] = {}
           self._enabled = True

       async def tick(self, engine: GameEngine) -> None:
           """Called from game loop - placeholder for now."""
           pass

       def get_active(self) -> list[SimulatedPlayer]:
           """Return list of active simulated players."""
           return list(self.active_sims.values())
   ```

3. **SimulatedCommandContext**
   ```python
   # Mirror CommandContext but capture output instead of sending to connection
   @dataclass
   class SimulatedCommandContext:
       session: "SimulatedSession"
       connection: "SimulatedConnection"
       engine: "GameEngine"
       args: list[str]
       raw_input: str

   class SimulatedConnection:
       """Captures output instead of sending to network."""

       def __init__(self) -> None:
           self.output_buffer: list[str] = []
           self.is_closed = False

       async def send_line(self, message: str) -> None:
           self.output_buffer.append(message)

       async def send(self, message: str) -> None:
           self.output_buffer.append(message)
   ```

**Tests to Write** (tests/game/systems/test_simulated_players/):
```
test_manager.py:
    - test_manager_initialization()
    - test_manager_get_active_empty()
    - test_manager_tick_does_not_crash()

test_context.py:
    - test_simulated_connection_captures_output()
    - test_simulated_session_has_character_id()
    - test_simulated_context_creation()

test_character_flag.py:
    - test_character_is_simulated_default_false()
    - test_character_can_be_marked_simulated()
```

**Acceptance Criteria**:
- [ ] Database migration runs without errors
- [ ] Character model has `is_simulated` field
- [ ] SimulatedPlayerManager can be instantiated
- [ ] SimulatedCommandContext captures output to buffer
- [ ] All unit tests pass
- [ ] No impact on existing game functionality

---

### Phase 2: Simulated Player Lifecycle (Login/Logout)

**Goal**: Simulated players can "log in" and "log out", appearing in the `who` list.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    config.py             # SimulatedPlayerConfig dataclass
    session.py            # SimulatedSession class
data/simulated_players/
    lyra.yaml             # First test sim (Explorer)
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/manager.py  # Add login/logout
src/waystone/game/systems/simulated_players/player.py   # Add lifecycle state
src/waystone/game/commands/info.py                      # Modify WhoCommand
src/waystone/game/engine.py                             # Add manager to tick
```

**Implementation Details**:

1. **SimulatedPlayerConfig** (YAML-loadable)
   ```python
   @dataclass
   class SimulatedPlayerConfig:
       id: str
       name: str
       background: CharacterBackground
       bartle_type: BartleType
       active_hours: tuple[int, int] = (8, 22)
       session_duration_hours: tuple[int, int] = (1, 4)

   def load_sim_configs(data_dir: Path) -> list[SimulatedPlayerConfig]:
       """Load all simulated player configs from YAML files."""
   ```

2. **Login/Logout Logic**
   ```python
   class SimulatedPlayerManager:
       async def _check_logins_logouts(self) -> None:
           """Check if any sims should login or logout based on schedule."""
           current_hour = datetime.now().hour

           for config in self.sim_pool:
               if config.id in self.active_sims:
                   # Check if should logout
                   sim = self.active_sims[config.id]
                   if sim.will_logout_at and datetime.now() >= sim.will_logout_at:
                       await self._logout_sim(sim)
               else:
                   # Check if should login
                   if self._is_active_hour(config, current_hour):
                       if random.random() < 0.1:  # 10% chance each tick
                           await self._login_sim(config)
   ```

3. **WhoCommand Integration**
   ```python
   # In info.py WhoCommand.execute()
   from waystone.game.systems.simulated_players import get_sim_manager

   # After listing real players...
   sim_manager = get_sim_manager()
   for sim in sim_manager.get_active():
       # Add to player list (indistinguishable from real players)
       output_lines.append(f"  {sim.character.name} (idle)")
   ```

4. **Engine Integration**
   ```python
   # In engine.py _periodic_cleanup()
   # After NPC poster check...
   from waystone.game.systems.simulated_players import get_sim_manager

   sim_manager = get_sim_manager()
   await sim_manager.tick(self)
   ```

**Tests to Write**:
```
test_config.py:
    - test_load_sim_config_from_yaml()
    - test_config_default_values()
    - test_config_active_hours_validation()

test_lifecycle.py:
    - test_sim_can_login()
    - test_sim_appears_in_who_list_after_login()
    - test_sim_can_logout()
    - test_sim_disappears_from_who_list_after_logout()
    - test_sim_respects_active_hours()
    - test_multiple_sims_can_be_active()

test_engine_integration.py:
    - test_engine_tick_calls_sim_manager()
```

**Acceptance Criteria**:
- [ ] Can load simulated player config from YAML
- [ ] Simulated player can "login" and appear in `who` list
- [ ] Simulated player can "logout" and disappear from `who` list
- [ ] Login respects configured active hours
- [ ] Game engine tick includes simulated player tick
- [ ] Real gameplay unaffected

---

### Phase 3: Basic Movement (Explorer MVP)

**Goal**: Explorer simulated player can move through the world autonomously.

**Duration Estimate**: 2-3 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    behavior.py           # BehaviorTree base classes
    behaviors/
        __init__.py
        movement.py       # Movement behavior nodes
    memory.py             # SimMemory for tracking visited rooms
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/player.py   # Add behavior tree
src/waystone/game/systems/simulated_players/manager.py  # Execute behaviors
src/waystone/game/world/room.py                         # Add sim to room.players
```

**Implementation Details**:

1. **Behavior Tree Framework**
   ```python
   class BehaviorNode(ABC):
       """Base class for behavior tree nodes."""

       @abstractmethod
       def evaluate(self, context: SimContext) -> BehaviorResult:
           """Evaluate this node and return result."""
           pass

   class SelectorNode(BehaviorNode):
       """Try children in order until one succeeds."""

       def __init__(self, children: list[BehaviorNode]):
           self.children = children

       def evaluate(self, context: SimContext) -> BehaviorResult:
           for child in self.children:
               result = child.evaluate(context)
               if result.status == BehaviorStatus.SUCCESS:
                   return result
           return BehaviorResult(BehaviorStatus.FAILURE)
   ```

2. **Explorer Movement Behavior**
   ```python
   class ExplorerMovementNode(BehaviorNode):
       """Move to unexplored rooms, prefer breadth-first exploration."""

       def evaluate(self, context: SimContext) -> BehaviorResult:
           room = context.engine.world.get(context.sim.character.current_room_id)
           if not room:
               return BehaviorResult(BehaviorStatus.FAILURE)

           # Get available exits
           exits = list(room.exits.keys())
           if not exits:
               return BehaviorResult(BehaviorStatus.FAILURE)

           # Prefer unvisited rooms
           unvisited = [
               direction for direction in exits
               if room.exits[direction] not in context.sim.memory.recent_rooms
           ]

           target_direction = random.choice(unvisited if unvisited else exits)
           return BehaviorResult(
               BehaviorStatus.SUCCESS,
               action=MovementAction(direction=target_direction)
           )
   ```

3. **SimMemory Implementation**
   ```python
   @dataclass
   class SimMemory:
       """Short-term memory for simulated player."""

       recent_rooms: deque = field(default_factory=lambda: deque(maxlen=10))
       recent_actions: deque = field(default_factory=lambda: deque(maxlen=5))

       def record_room(self, room_id: str) -> None:
           self.recent_rooms.append(room_id)

       def record_action(self, action: str) -> None:
           self.recent_actions.append(action)
   ```

4. **Room Presence**
   ```python
   # When sim moves to room, add to room.players
   async def _move_sim_to_room(self, sim: SimulatedPlayer, target_room_id: str) -> None:
       # Remove from old room
       old_room = self.engine.world.get(sim.character.current_room_id)
       if old_room and sim.character.name in old_room.players:
           old_room.players.remove(sim.character.name)

       # Add to new room
       new_room = self.engine.world.get(target_room_id)
       if new_room:
           new_room.players.add(sim.character.name)
           sim.character.current_room_id = target_room_id
   ```

**Tests to Write**:
```
test_behavior_tree.py:
    - test_selector_node_tries_children_in_order()
    - test_selector_node_stops_on_success()
    - test_behavior_result_contains_action()

test_movement.py:
    - test_explorer_movement_selects_exit()
    - test_explorer_prefers_unvisited_rooms()
    - test_explorer_avoids_recent_rooms()
    - test_movement_updates_room_players()
    - test_movement_updates_character_location()

test_memory.py:
    - test_memory_records_rooms()
    - test_memory_has_max_size()
    - test_memory_records_actions()

test_explorer_integration.py:
    - test_explorer_moves_over_multiple_ticks()
    - test_explorer_visible_in_room_description()
    - test_real_player_sees_explorer_arrive()
```

**Acceptance Criteria**:
- [ ] Explorer sim moves to new rooms autonomously
- [ ] Explorer prefers unexplored exits
- [ ] Explorer appears in room descriptions
- [ ] Real players see "Lyra has arrived" messages
- [ ] Explorer's location persists to database
- [ ] Memory prevents ping-pong movement

---

### Phase 4: Templated Communication (Explorer)

**Goal**: Explorer simulated player speaks, emotes, and uses chat appropriately.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    templates.py          # Chat/emote templates per Bartle type
    behaviors/
        communication.py  # Communication behavior nodes
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/player.py   # Add chat behavior
src/waystone/game/systems/simulated_players/behavior.py # Add to tree
data/simulated_players/lyra.yaml                        # Add personality traits
```

**Implementation Details**:

1. **Explorer Templates** (from design doc Section 3.2)
   ```python
   EXPLORER_CHAT_TEMPLATES = [
       "Has anyone been to {room_name}?",
       "Found a hidden path near {landmark}!",
       "What's behind the {mysterious_door}?",
       "This area feels different...",
       "I wonder what happens if you {unusual_action}",
   ]

   EXPLORER_EMOTES = [
       "peers curiously at the surroundings",
       "runs their hand along the wall",
       "looks up at the ceiling thoughtfully",
       "examines something on the ground",
   ]
   ```

2. **Communication Behavior Node**
   ```python
   class ChatBehaviorNode(BehaviorNode):
       """Decide whether to chat based on context."""

       def __init__(self, chattiness: float, templates: list[str]):
           self.chattiness = chattiness
           self.templates = templates

       def evaluate(self, context: SimContext) -> BehaviorResult:
           # Don't spam - check last chat time
           if context.sim.memory.last_chat_time:
               elapsed = datetime.now() - context.sim.memory.last_chat_time
               if elapsed.seconds < 60:  # At least 1 min between chats
                   return BehaviorResult(BehaviorStatus.FAILURE)

           # Roll against chattiness
           if random.random() > self.chattiness:
               return BehaviorResult(BehaviorStatus.FAILURE)

           # Generate message
           template = random.choice(self.templates)
           message = self._fill_template(template, context)

           return BehaviorResult(
               BehaviorStatus.SUCCESS,
               action=ChatAction(channel="chat", message=message)
           )
   ```

3. **Template Variable Filling**
   ```python
   def _fill_template(self, template: str, context: SimContext) -> str:
       """Fill in template variables from context."""
       room = context.engine.world.get(context.sim.character.current_room_id)

       variables = {
           "room_name": room.name if room else "somewhere",
           "landmark": random.choice(LANDMARKS),
           "mysterious_door": random.choice(MYSTERIOUS_OBJECTS),
           "unusual_action": random.choice(UNUSUAL_ACTIONS),
       }

       try:
           return template.format(**variables)
       except KeyError:
           return template
   ```

**Tests to Write**:
```
test_templates.py:
    - test_explorer_chat_templates_exist()
    - test_explorer_emote_templates_exist()
    - test_template_variable_filling()
    - test_template_with_missing_variable_doesnt_crash()

test_communication.py:
    - test_chat_behavior_respects_chattiness()
    - test_chat_behavior_respects_cooldown()
    - test_emote_behavior_selects_from_templates()
    - test_chat_appears_to_other_players()

test_explorer_communication.py:
    - test_explorer_uses_explorer_templates()
    - test_explorer_emotes_in_interesting_rooms()
```

**Acceptance Criteria**:
- [ ] Explorer says things from template list
- [ ] Explorer emotes appropriately
- [ ] Chat respects chattiness setting
- [ ] Cooldown prevents chat spam
- [ ] Real players see chat/emotes
- [ ] Template variables fill correctly

---

### Phase 5: Room Interaction (Explorer)

**Goal**: Explorer examines objects, reads signs, and interacts with rooms.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    behaviors/
        interaction.py    # Room interaction behavior nodes
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/player.py   # Add interaction tree
src/waystone/game/systems/simulated_players/memory.py   # Track examined objects
```

**Implementation Details**:

1. **Examine Behavior**
   ```python
   class ExamineBehaviorNode(BehaviorNode):
       """Examine interesting objects in the room."""

       def evaluate(self, context: SimContext) -> BehaviorResult:
           room = context.engine.world.get(context.sim.character.current_room_id)
           if not room:
               return BehaviorResult(BehaviorStatus.FAILURE)

           # Get items in room not yet examined
           items = room.items - context.sim.memory.examined_items
           if not items:
               return BehaviorResult(BehaviorStatus.FAILURE)

           target = random.choice(list(items))
           context.sim.memory.examined_items.add(target)

           return BehaviorResult(
               BehaviorStatus.SUCCESS,
               action=ExamineAction(target=target)
           )
   ```

2. **Explorer-Specific Curiosity**
   ```python
   # Explorer has high curiosity - examines more often
   def build_explorer_tree(config: SimulatedPlayerConfig) -> BehaviorTree:
       return BehaviorTree(
           root=SelectorNode([
               # High priority: examine if curious (Explorer specialty)
               WeightedNode(ExamineBehaviorNode(), weight=0.25),
               # Medium priority: move to unexplored areas
               WeightedNode(ExplorerMovementNode(), weight=0.50),
               # Low priority: idle emotes
               WeightedNode(IdleEmoteNode(EXPLORER_EMOTES), weight=0.15),
               # Fallback: chat
               WeightedNode(ChatBehaviorNode(0.10, EXPLORER_CHAT), weight=0.10),
           ])
       )
   ```

**Tests to Write**:
```
test_interaction.py:
    - test_examine_behavior_selects_item()
    - test_examine_behavior_avoids_already_examined()
    - test_examine_executes_examine_command()
    - test_explorer_examines_more_than_other_types()

test_explorer_complete.py:
    - test_explorer_full_behavior_cycle()
    - test_explorer_explores_then_examines_then_chats()
    - test_explorer_feels_natural_over_time()
```

**Acceptance Criteria**:
- [ ] Explorer examines items in rooms
- [ ] Explorer doesn't re-examine same item repeatedly
- [ ] Examine output visible to players in room
- [ ] Explorer behavior feels curious and exploratory

---

### Phase 6: Additional Bartle Types

**Goal**: Implement remaining Bartle types (Achiever, Socializer, Killer).

**Duration Estimate**: 3-4 days (1 day per type + integration)

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    behaviors/
        combat.py         # Combat behaviors (Achiever, Killer)
        social.py         # Social behaviors (Socializer)
        achievement.py    # Achievement behaviors (Achiever)
    personality.py        # BartleType enum and trait mappings

data/simulated_players/
    korvin.yaml           # Achiever config
    denna.yaml            # Socializer config
    devi.yaml             # Killer config
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/player.py   # Type-specific trees
src/waystone/game/systems/simulated_players/manager.py  # Load all configs
src/waystone/game/systems/simulated_players/templates.py # All type templates
```

**Implementation by Type**:

1. **Achiever (Korvin)**
   - Combat behavior targeting hostile NPCs
   - Quest progression (if quests exist)
   - Training/skill-related actions
   - Templates from Section 3.1

2. **Socializer (Denna)**
   - Gravitates toward rooms with players
   - High chat frequency
   - Help-oriented behaviors
   - Templates from Section 3.3

3. **Killer (Devi)**
   - Combat-seeking behavior
   - Competitive chat
   - Patrolling combat zones
   - Templates from Section 3.4

**Tests to Write**:
```
test_achiever.py:
    - test_achiever_attacks_hostile_npcs()
    - test_achiever_prioritizes_combat()
    - test_achiever_uses_achiever_templates()

test_socializer.py:
    - test_socializer_moves_toward_players()
    - test_socializer_chats_frequently()
    - test_socializer_greets_new_players()

test_killer.py:
    - test_killer_seeks_combat_areas()
    - test_killer_competitive_chat()
    - test_killer_uses_killer_templates()

test_all_types.py:
    - test_each_type_behaves_distinctly()
    - test_multiple_types_active_simultaneously()
```

**Acceptance Criteria**:
- [ ] All four Bartle types implemented
- [ ] Each type has distinct, observable behavior
- [ ] Templates match personality
- [ ] Can run multiple different types simultaneously

---

### Phase 7: State Machine & Combat Integration

**Goal**: Simulated players handle combat, fleeing, and resting appropriately.

**Duration Estimate**: 2-3 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    state_machine.py      # SimState enum and transitions
    behaviors/
        survival.py       # Survival behaviors (flee, rest)
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/player.py   # Add state machine
src/waystone/game/systems/simulated_players/behavior.py # Priority behaviors
src/waystone/game/systems/npc_combat.py                 # Handle sim combat
```

**Implementation Details**:

1. **State Machine**
   ```python
   class SimState(Enum):
       IDLE = "idle"
       EXPLORING = "exploring"
       COMBAT = "combat"
       FLEEING = "fleeing"
       RESTING = "resting"
       SOCIALIZING = "socializing"

   VALID_TRANSITIONS = {
       SimState.IDLE: {SimState.EXPLORING, SimState.COMBAT, SimState.SOCIALIZING},
       SimState.EXPLORING: {SimState.IDLE, SimState.COMBAT},
       SimState.COMBAT: {SimState.FLEEING, SimState.IDLE, SimState.RESTING},
       SimState.FLEEING: {SimState.IDLE, SimState.RESTING},
       SimState.RESTING: {SimState.IDLE},
       SimState.SOCIALIZING: {SimState.IDLE, SimState.COMBAT},
   }
   ```

2. **Survival Behaviors (Highest Priority)**
   ```python
   class SurvivalBehaviorNode(BehaviorNode):
       """Check if sim needs to flee or rest."""

       def evaluate(self, context: SimContext) -> BehaviorResult:
           hp_percent = context.sim.character.current_hp / context.sim.character.max_hp

           # Critical: flee immediately
           if hp_percent < 0.25 and context.sim.state == SimState.COMBAT:
               return BehaviorResult(
                   BehaviorStatus.SUCCESS,
                   action=FleeAction(),
                   state_transition=SimState.FLEEING
               )

           # Low: rest if safe
           if hp_percent < 0.50 and context.sim.state != SimState.COMBAT:
               return BehaviorResult(
                   BehaviorStatus.SUCCESS,
                   action=RestAction(),
                   state_transition=SimState.RESTING
               )

           return BehaviorResult(BehaviorStatus.FAILURE)
   ```

**Tests to Write**:
```
test_state_machine.py:
    - test_valid_state_transitions()
    - test_invalid_state_transitions_rejected()
    - test_state_persists_between_ticks()

test_survival.py:
    - test_sim_flees_at_low_hp()
    - test_sim_rests_when_damaged()
    - test_sim_resumes_activity_after_healing()

test_combat_integration.py:
    - test_sim_can_enter_combat()
    - test_sim_attacks_in_combat_state()
    - test_sim_receives_damage()
    - test_sim_death_logs_out()
```

**Acceptance Criteria**:
- [ ] State machine controls behavior priority
- [ ] Sims flee when health is critical
- [ ] Sims rest to recover health
- [ ] Combat integrates with existing NPC combat system
- [ ] Sim "death" causes logout (respects design doc)

---

### Phase 8: Timing, Polish & Tuning

**Goal**: Make simulated players feel natural with human-like timing.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/game/systems/simulated_players/
    timing.py             # ActionTiming configuration
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/manager.py  # Timing integration
src/waystone/game/systems/simulated_players/player.py   # Per-action delays
data/simulated_players/*.yaml                           # Tune timing values
```

**Implementation Details**:

1. **Action Timing**
   ```python
   @dataclass
   class ActionTiming:
       min_action_delay: float = 3.0
       max_action_delay: float = 15.0
       typing_delay_per_char: float = 0.05

       # Personality modifiers
       achiever_speed_modifier: float = 0.8
       socializer_speed_modifier: float = 1.2
       explorer_speed_modifier: float = 1.0
       killer_speed_modifier: float = 0.9

   def get_next_action_delay(self, bartle_type: BartleType) -> float:
       base_delay = random.uniform(self.min_action_delay, self.max_action_delay)
       modifier = getattr(self, f"{bartle_type.value}_speed_modifier", 1.0)
       return base_delay * modifier
   ```

2. **"Typing" Simulation for Chat**
   ```python
   async def _execute_chat_with_typing(self, sim: SimulatedPlayer, message: str) -> None:
       # Calculate "typing" time
       typing_time = len(message) * self.timing.typing_delay_per_char
       await asyncio.sleep(typing_time)

       # Execute chat command
       await self._execute_command(sim, f"chat {message}")
   ```

**Tests to Write**:
```
test_timing.py:
    - test_action_delay_within_bounds()
    - test_personality_affects_timing()
    - test_typing_delay_proportional_to_message()

test_naturalness.py:
    - test_sim_doesnt_act_every_tick()
    - test_actions_have_variable_delays()
    - test_long_messages_take_longer()
```

**Acceptance Criteria**:
- [ ] Actions have variable delays
- [ ] Different Bartle types move at different speeds
- [ ] Chat messages have typing simulation
- [ ] Behavior feels natural, not robotic

---

### Phase 9: Admin Tools & Observability

**Goal**: Admins can monitor, control, and debug simulated players.

**Duration Estimate**: 1 day

**Files to Create**:
```
src/waystone/game/commands/admin_sim.py  # Admin commands for sims
```

**Files to Modify**:
```
src/waystone/game/engine.py              # Register admin commands
src/waystone/game/commands/info.py       # Optional [SIM] tag for admins
```

**Implementation Details**:

1. **Admin Commands**
   ```python
   class SimStatusCommand(Command):
       """Show status of all simulated players."""
       name = "simstatus"
       requires_admin = True

       async def execute(self, ctx: CommandContext) -> None:
           sim_manager = get_sim_manager()
           for sim in sim_manager.get_active():
               await ctx.connection.send_line(
                   f"{sim.config.name} ({sim.config.bartle_type.value}): "
                   f"State={sim.state.value}, Room={sim.character.current_room_id}"
               )

   class SimForceLoginCommand(Command):
       """Force a specific sim to login."""
       name = "simlogin"
       requires_admin = True

   class SimForceLogoutCommand(Command):
       """Force a specific sim to logout."""
       name = "simlogout"
       requires_admin = True
   ```

2. **Optional [SIM] Tag**
   ```python
   # In WhoCommand, for admin sessions
   if session.is_admin and sim_manager.is_simulated(character_name):
       display_name = f"{character_name} [SIM]"
   ```

**Tests to Write**:
```
test_admin_commands.py:
    - test_simstatus_shows_active_sims()
    - test_simlogin_activates_sim()
    - test_simlogout_deactivates_sim()
    - test_admin_sees_sim_tag()
    - test_non_admin_doesnt_see_sim_tag()
```

**Acceptance Criteria**:
- [ ] Admins can view sim status
- [ ] Admins can force login/logout
- [ ] Optional [SIM] tag visible to admins only
- [ ] Logging captures sim actions for debugging

---

### Phase 10: Database Persistence & Production Readiness

**Goal**: Simulated player state persists across server restarts.

**Duration Estimate**: 1-2 days

**Files to Create**:
```
src/waystone/database/models/simulated_player.py  # SimulatedPlayerConfigDB
alembic/versions/xxx_simulated_player_config.py   # Migration
```

**Files to Modify**:
```
src/waystone/game/systems/simulated_players/manager.py  # Load from DB
src/waystone/game/systems/simulated_players/config.py   # DB integration
src/waystone/database/models/__init__.py                # Export model
```

**Implementation Details**:

1. **Database Model**
   ```python
   class SimulatedPlayerConfigDB(Base):
       __tablename__ = "simulated_player_configs"

       id: Mapped[str] = mapped_column(String(50), primary_key=True)
       character_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("characters.id"))
       bartle_type: Mapped[str] = mapped_column(String(20))
       config_json: Mapped[dict] = mapped_column(JSON)
       is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

       # Runtime state (optional persistence)
       last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
       last_logout: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
   ```

2. **Startup Loading**
   ```python
   async def _load_sim_pool(self) -> None:
       """Load simulated player configs from database."""
       async with get_session() as db:
           result = await db.execute(
               select(SimulatedPlayerConfigDB).where(
                   SimulatedPlayerConfigDB.is_enabled == True
               )
           )
           configs = result.scalars().all()

           for config_db in configs:
               self.sim_pool.append(
                   SimulatedPlayerConfig.from_db(config_db)
               )
   ```

**Tests to Write**:
```
test_persistence.py:
    - test_sim_config_saves_to_db()
    - test_sim_config_loads_from_db()
    - test_disabled_sims_not_loaded()
    - test_sim_state_persists_across_restart()
```

**Acceptance Criteria**:
- [ ] Sim configs stored in database
- [ ] Server restart doesn't lose sim state
- [ ] Can enable/disable sims via database
- [ ] Character records persist for sims

---

## Implementation Summary

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| 1. Core Infrastructure | 1-2 days | Basic framework, no behavior |
| 2. Lifecycle | 1-2 days | Login/logout, who list |
| 3. Movement (Explorer) | 2-3 days | Autonomous exploration |
| 4. Communication | 1-2 days | Chat and emotes |
| 5. Interaction | 1-2 days | Examine objects |
| 6. All Bartle Types | 3-4 days | Achiever, Socializer, Killer |
| 7. State Machine | 2-3 days | Combat, flee, rest |
| 8. Timing | 1-2 days | Human-like delays |
| 9. Admin Tools | 1 day | Monitoring and control |
| 10. Persistence | 1-2 days | Database storage |

**Total Estimated Time**: 15-23 days

**Recommended MVP Milestone**: Phases 1-5 (Explorer fully functional)
- Estimated time: 7-11 days
- Delivers a working simulated player that explores, talks, and examines
- Validates architecture before building remaining types

---

## Appendix A: Refined Implementation Notes Based on Codebase Review

### A.1 Tick Integration (Specific Code Location)

Add to `src/waystone/game/engine.py` in `_periodic_cleanup()` after the NPC poster check (~line 860):

```python
# Simulated player actions (every 2 ticks = 60 seconds for active sims)
if tick_count % 2 == 0:
    from waystone.game.systems.simulated_players import get_sim_manager
    sim_manager = get_sim_manager()
    if sim_manager:
        actions_taken = await sim_manager.tick(self)
        if actions_taken > 0:
            logger.debug("simulated_player_tick", actions=actions_taken)
```

### A.2 Reuse Existing Patterns

**Template Pattern** (from `npc_poster.py`):
```python
# Simulated players should use the same pattern
@dataclass
class SimChatTemplate:
    patterns: list[str]
    variables: dict[str, list[str]]  # Variable -> possible values

    def generate(self, context: SimContext) -> str:
        pattern = random.choice(self.patterns)
        filled = {}
        for var, values in self.variables.items():
            filled[var] = random.choice(values)
        # Add context-specific variables
        filled["room_name"] = context.room.name if context.room else "somewhere"
        return pattern.format(**filled)
```

**Instance Tracking** (from `npc_combat.py`):
```python
# Global tracking mirrors NPC combat pattern
_sim_instances: dict[str, SimulatedPlayer] = {}  # sim_id -> SimulatedPlayer
_sim_by_room: dict[str, set[str]] = {}  # room_id -> set of sim_ids

def get_sims_in_room(room_id: str) -> list[SimulatedPlayer]:
    """Get all active simulated players in a room."""
    if room_id not in _sim_by_room:
        return []
    return [_sim_instances[sid] for sid in _sim_by_room[room_id]
            if sid in _sim_instances and _sim_instances[sid].is_active]
```

### A.3 SimulatedSession Implementation

The simulated session must satisfy the interface expected by commands:

```python
@dataclass
class SimulatedSession:
    """Lightweight session for simulated players."""

    id: str  # Unique session ID
    character_id: UUID  # Real character from database
    character: Character  # Cached character object
    state: SessionState = SessionState.PLAYING
    current_board: str | None = None
    last_activity: datetime = field(default_factory=datetime.now)

    # Not used but required for interface
    account_id: UUID | None = None

    @property
    def is_simulated(self) -> bool:
        return True
```

### A.4 Files to Create (Final List)

```
src/waystone/game/systems/simulated_players/
    __init__.py           # Public API: get_sim_manager(), SimulatedPlayer
    manager.py            # SimulatedPlayerManager (tick, login/logout)
    player.py             # SimulatedPlayer dataclass
    config.py             # SimulatedPlayerConfig (YAML-loadable)
    session.py            # SimulatedSession, SimulatedConnection
    context.py            # SimulatedCommandContext
    behavior/
        __init__.py
        tree.py           # BehaviorTree, BehaviorNode base classes
        movement.py       # Movement behaviors
        communication.py  # Chat, emote behaviors
        interaction.py    # Examine, read behaviors
        combat.py         # Attack, flee behaviors
        social.py         # Player-reactive behaviors
    templates/
        __init__.py
        explorer.py       # Explorer chat/emote templates
        achiever.py       # Achiever templates
        socializer.py     # Socializer templates
        killer.py         # Killer templates
    memory.py             # SimMemory (short-term tracking)
    timing.py             # ActionTiming configuration

data/simulated_players/
    explorer_lyra.yaml
    achiever_korvin.yaml
    socializer_denna.yaml
    killer_devi.yaml

alembic/versions/
    xxx_add_character_is_simulated.py  # Migration for Character.is_simulated
```

### A.5 Key Implementation Order

Based on existing patterns, the recommended implementation order:

1. **SimulatedSession + SimulatedConnection** - Must satisfy Command interface first
2. **SimulatedPlayerConfig** - YAML loading (follow npc_poster pattern)
3. **SimulatedPlayerManager** - Basic lifecycle (follow session_manager pattern)
4. **Engine integration** - Add tick call (one line in `_periodic_cleanup`)
5. **BehaviorTree** - Basic framework
6. **Explorer behaviors** - MVP functionality
7. **Templates** - Reuse npc_poster pattern
8. **Additional Bartle types** - Build on Explorer

### A.6 Differences from waystone.agent

The existing `waystone.agent` is **not** suitable for simulated players because:

| Aspect | waystone.agent | Simulated Players |
|--------|---------------|-------------------|
| Connection | External telnet | Server-side integration |
| Decision Making | LLM inference (expensive) | Behavior trees (free) |
| Latency | Network + API calls | Instant |
| Scale | 1-2 agents max | 4+ simultaneous |
| Purpose | Testing, demo | Ambient presence |

The two systems serve different purposes and should remain separate.

---

*This design provides the architectural foundation for creating believable simulated players that make Waystone MUD feel alive during solo play. The Engineer should add implementation phases based on priority and available development time.*
