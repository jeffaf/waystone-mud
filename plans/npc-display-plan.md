# NPC Display Features - Architecture Plan

**Author:** Atlas (Principal Software Architect)
**Date:** 2025-12-09
**Project:** Waystone MUD
**Phase:** Feature Enhancement - NPC Display & Examination

---

## Executive Summary

This plan details the implementation of comprehensive NPC display features for Waystone MUD, including:
1. Automatic NPC listing when players enter or look at rooms
2. Enhanced `examine` and `look` commands for NPC inspection
3. Equipment display system for NPCs
4. Health condition descriptors based on HP percentage

### Success Metrics
- NPCs visible in room descriptions with color-coded threat levels
- Complete NPC examination showing description, equipment, and health
- Proper display of multiple identical NPCs (e.g., "Three giant rats are here")
- Equipment system that shows worn/wielded items on NPCs

### Technical Stack Justification
- **Existing Python codebase** - Continue with established patterns
- **Pydantic models** - Already used for NPCTemplate and Room validation
- **In-memory NPC instances** - Current system with `_npc_instances` dictionary
- **YAML-based data** - Maintain existing world/NPC data structure

### Timeline Estimate
- Phase 1 (Data Models): 2-3 hours
- Phase 2 (Display Logic): 3-4 hours
- Phase 3 (Commands): 2-3 hours
- Testing & Polish: 2-3 hours
- **Total:** 9-13 hours of development

### Resource Requirements
- 1 Backend Developer (Python, async/await patterns)
- Understanding of MUD conventions (room descriptions, NPC examination)
- Access to existing codebase patterns

---

## System Architecture Overview

### Current Architecture Analysis

**Existing Components:**
1. **NPCTemplate** (Pydantic model) - Blueprint defining NPC types
   - Location: `/src/waystone/game/world/npc_loader.py`
   - Contains: id, name, description, level, max_hp, attributes, behavior

2. **NPCInstance** (dataclass) - Runtime NPC with combat state
   - Location: `/src/waystone/game/systems/npc_combat.py`
   - Contains: instance tracking, current HP, room location

3. **Room** (Pydantic model) - Game world locations
   - Location: `/src/waystone/game/world/room.py`
   - Contains: description, exits, properties, player tracking

4. **LookCommand** - Current implementation shows NPCs
   - Location: `/src/waystone/game/commands/movement.py` (lines 318-411)
   - Already displays NPCs with basic health conditions

5. **ExamineNPCCommand** - Partial implementation exists
   - Location: `/src/waystone/game/commands/npc.py` (lines 139-234)
   - Shows description, behavior, level, health, dialogue

### Architecture Gaps

**Missing Components:**
1. **NPC Equipment System** - No current equipment tracking for NPCs
2. **Three-field NPC naming** - Missing `keywords` and `short_description` fields
3. **Long descriptions for rooms** - No `long_description` field for room presence
4. **Equipment display formatter** - No system to show worn/wielded items
5. **Health condition generator** - Basic version exists but needs standardization

---

## Data Model Changes

### 1. NPCTemplate Model Enhancements

**File:** `/src/waystone/game/world/npc_loader.py`

**New Fields Required:**

```python
class NPCTemplate(BaseModel):
    # ... existing fields ...

    # NEW: Three-field naming system
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for player commands (e.g., ['rat', 'giant', 'sewer'])"
    )
    short_description: str = Field(
        default="",
        description="Used in action messages (e.g., 'a giant sewer rat')"
    )
    long_description: str = Field(
        default="",
        description="Shown in room when present (e.g., 'A giant sewer rat is here, sniffing for food.')"
    )

    # NEW: Equipment system
    equipment: dict[str, str] = Field(
        default_factory=dict,
        description="Equipped items by slot: {'weapon': 'rusty_shortsword', 'body': 'leather_armor'}"
    )

    # NEW: Inventory for drops (optional)
    inventory: list[str] = Field(
        default_factory=list,
        description="Item template IDs this NPC carries"
    )
```

**Backward Compatibility:**
- All new fields have defaults
- Existing YAML files work without modification
- `short_description` defaults to `name` if not provided
- `long_description` auto-generated if missing

**Migration Strategy:**
1. Add fields with defaults to Pydantic model
2. Update NPCLoader validation to handle optional fields
3. Gradually enhance NPC YAML files with new fields
4. No database migration needed (template-based system)

---

### 2. NPCInstance Runtime Enhancements

**File:** `/src/waystone/game/systems/npc_combat.py`

**New Fields Required:**

```python
@dataclass
class NPCInstance:
    # ... existing fields ...

    # NEW: Copy from template for easy access
    keywords: list[str] = field(default_factory=list)
    short_description: str = ""
    long_description: str = ""
    equipment: dict[str, str] = field(default_factory=dict)
    inventory: list[str] = field(default_factory=list)

    # NEW: NPC state for equipment changes
    dropped_items: set[str] = field(default_factory=set)  # Track dropped equipment
```

**Update spawn_npc() function:**
```python
def spawn_npc(template: "NPCTemplate", room_id: str) -> NPCInstance:
    instance = NPCInstance(
        # ... existing fields ...
        keywords=list(template.keywords) if template.keywords else [],
        short_description=template.short_description or template.name,
        long_description=template.long_description or f"{template.name} is here.",
        equipment=dict(template.equipment) if template.equipment else {},
        inventory=list(template.inventory) if template.inventory else [],
    )
    # ... rest of spawn logic ...
```

---

## NPC YAML Schema Additions

### Example Enhanced NPC Definition

**File:** `/data/world/npcs/enemies.yaml`

```yaml
npcs:
  - id: bandit
    name: "a scrappy bandit"  # Display name (fallback)

    # NEW: Three-field naming system
    keywords:
      - bandit
      - scrappy
      - thief
    short_description: "a scrappy bandit"  # Used in actions
    long_description: "A scrappy bandit lurks here, eyeing you suspiciously."

    description: |
      A rough-looking bandit with weathered features and suspicious eyes.
      Dressed in mismatched leather armor, they carry a rusty shortsword
      and a hungry look.

    level: 2
    max_hp: 30
    attributes:
      strength: 12
      dexterity: 14
      constitution: 12
      intelligence: 8
      wisdom: 10
      charisma: 8

    # NEW: Equipment system
    equipment:
      main_hand: rusty_shortsword
      body: leather_armor_worn

    # NEW: Inventory for drops
    inventory:
      - rusty_shortsword
      - leather_armor_worn
      - small_pouch

    behavior: aggressive
    loot_table_id: bandit_loot
    dialogue: null
    respawn_time: 300
```

### Merchant NPC Example

```yaml
  - id: merchant_imre
    name: "Devi, the merchant"
    keywords:
      - devi
      - merchant
      - shopkeeper
    short_description: "Devi, the merchant"
    long_description: "Devi stands behind her counter, watching customers with keen eyes."

    description: |
      A shrewd merchant woman with sharp eyes and a calculating smile.
      Devi runs a profitable business in Imre, buying and selling all
      manner of goods.

    # ... rest of merchant config ...

    equipment:
      body: fine_merchants_robe
      accessory: silver_ledger_pin

    inventory:
      - merchants_ledger
      - coin_purse
```

---

## Room Display Integration

### 1. Enhanced LookCommand Output

**File:** `/src/waystone/game/commands/movement.py`

**Current Implementation:** Lines 318-411 already show NPCs

**Enhancement Plan:**

```python
class LookCommand(Command):
    async def execute(self, ctx: CommandContext) -> None:
        # ... existing room description logic ...

        # ENHANCED: Show NPCs with long_description
        npcs = get_npcs_in_room(character.current_room_id)
        if npcs:
            await ctx.connection.send_line("")

            # Group identical NPCs
            npc_groups = _group_npcs_by_template(npcs)

            for template_id, npc_list in npc_groups.items():
                count = len(npc_list)
                npc = npc_list[0]  # Get first for display info

                # Determine color based on behavior/aggression
                color = _get_npc_color(npc)

                # Use long_description with count pluralization
                display_text = _format_npc_room_presence(npc, count)

                await ctx.connection.send_line(
                    colorize(display_text, color)
                )

        # ... existing player display logic ...
```

**New Helper Functions:**

```python
def _group_npcs_by_template(npcs: list[NPCInstance]) -> dict[str, list[NPCInstance]]:
    """Group NPCs by template for count display."""
    groups: dict[str, list[NPCInstance]] = {}
    for npc in npcs:
        if npc.template_id not in groups:
            groups[npc.template_id] = []
        groups[npc.template_id].append(npc)
    return groups

def _get_npc_color(npc: NPCInstance) -> str:
    """Determine display color based on NPC behavior."""
    if npc.behavior == "aggressive":
        return "RED"
    elif npc.behavior == "training_dummy":
        return "YELLOW"
    elif npc.behavior == "merchant":
        return "CYAN"
    elif npc.behavior in ("passive", "stationary"):
        return "GREEN"
    else:
        return "WHITE"

def _format_npc_room_presence(npc: NPCInstance, count: int) -> str:
    """Format NPC presence line with count pluralization."""
    if count == 1:
        return npc.long_description
    elif count == 2:
        # Simple pluralization
        return npc.long_description.replace(" is here", " are here (x2)")
    else:
        # Numeric count
        name_plural = _pluralize_npc_name(npc.short_description)
        return f"{count.title()} {name_plural} are here."

def _pluralize_npc_name(name: str) -> str:
    """Simple pluralization for NPC names."""
    # Basic rules (can be enhanced)
    if name.endswith('s'):
        return name
    elif name.endswith('y'):
        return name[:-1] + 'ies'
    elif name.endswith(('sh', 'ch')):
        return name + 'es'
    else:
        return name + 's'
```

---

## Look/Examine NPC Command Implementation

### 1. Enhanced ExamineCommand Routing

**File:** `/src/waystone/game/commands/inventory.py`

**Current:** ExamineCommand tries to find items, falls back to generic message

**Enhancement:**

```python
class ExamineCommand(Command):
    """Examine an item or NPC in detail."""

    name = "examine"
    aliases = ["ex", "look"]
    help_text = "examine <target> - Examine an item or NPC in detail"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute examine command with NPC support."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        target_name = " ".join(ctx.args).lower()

        # Get character and room
        async with get_session() as session:
            character = await _get_character(session, ctx.session.character_id)
            if not character:
                return

            room_id = character.current_room_id

            # PRIORITY 1: Try to find NPC in room
            npc = find_npc_by_keywords(room_id, target_name)
            if npc:
                await _display_npc_examination(ctx, npc)
                return

            # PRIORITY 2: Try to find item in inventory
            # ... existing item examination logic ...

            # PRIORITY 3: Try to find item in room
            # ... existing room item logic ...

            # PRIORITY 4: Not found
            await ctx.connection.send_line(
                colorize(f"You don't see '{target_name}' here.", "YELLOW")
            )
```

### 2. New NPC Examination Display Function

**File:** `/src/waystone/game/commands/npc.py` (enhance existing ExamineNPCCommand)

```python
async def _display_npc_examination(
    ctx: CommandContext,
    npc: NPCInstance
) -> None:
    """
    Display detailed NPC examination output.

    Format follows MUD conventions:
    - Name header
    - Full description
    - Health condition (descriptive, not numeric)
    - Equipment display (worn/wielded items)
    - Carrying (inventory items visible)
    """
    conn = ctx.connection

    # Header with name
    await conn.send_line("")
    await conn.send_line(colorize(npc.name.title(), "CYAN"))
    await conn.send_line("-" * len(npc.name))

    # Get full description from template
    template = ctx.engine.npc_templates.get(npc.template_id)
    if template:
        await conn.send_line(template.description.strip())
    await conn.send_line("")

    # Health condition (descriptive)
    health_text = _get_health_condition(npc)
    await conn.send_line(health_text)
    await conn.send_line("")

    # Equipment display
    if npc.equipment:
        await conn.send_line(colorize("Equipment:", "YELLOW"))
        await _display_npc_equipment(ctx, npc)
        await conn.send_line("")

    # Inventory (carrying)
    if npc.inventory:
        await conn.send_line(colorize("Carrying:", "YELLOW"))
        for item_id in npc.inventory:
            item_name = _get_item_display_name(item_id)
            await conn.send_line(f"  {item_name}")
        await conn.send_line("")

    # Special behavior notes
    if npc.behavior == "merchant":
        await conn.send_line(
            colorize("Type 'trade' to see what they're buying and selling.", "CYAN")
        )
    elif npc.behavior == "aggressive":
        await conn.send_line(
            colorize("This creature looks dangerous!", "RED")
        )
```

---

## Health Condition Text Generator

### Standardized Health Descriptor System

**File:** `/src/waystone/game/systems/npc_display.py` (NEW FILE)

```python
"""NPC display utilities for Waystone MUD."""

from waystone.game.systems.npc_combat import NPCInstance
from waystone.network import colorize


def get_health_condition(npc: NPCInstance) -> str:
    """
    Generate descriptive health condition text based on HP percentage.

    Args:
        npc: NPC instance to check

    Returns:
        Formatted health condition string with appropriate color

    Health Condition Scale:
    - 100%: "in perfect health"
    - 75-99%: "slightly wounded"
    - 50-74%: "wounded"
    - 25-49%: "badly wounded"
    - 10-24%: "near death"
    - <10%: "mortally wounded"
    """
    if npc.max_hp <= 0:
        return colorize("Health unknown.", "DIM")

    hp_percent = (npc.current_hp / npc.max_hp) * 100

    if hp_percent >= 100:
        condition = "in perfect health"
        color = "GREEN"
    elif hp_percent >= 75:
        condition = "slightly wounded"
        color = "GREEN"
    elif hp_percent >= 50:
        condition = "wounded"
        color = "YELLOW"
    elif hp_percent >= 25:
        condition = "badly wounded"
        color = "ORANGE"
    elif hp_percent >= 10:
        condition = "near death"
        color = "RED"
    else:
        condition = "mortally wounded"
        color = "RED"

    # Use third-person for NPCs
    pronoun = _get_npc_pronoun(npc)

    return f"{pronoun.capitalize()} {_get_verb_form(pronoun)} {colorize(condition, color)}."


def _get_npc_pronoun(npc: NPCInstance) -> str:
    """Determine appropriate pronoun for NPC."""
    # Check if NPC is humanoid (simple heuristic)
    humanoid_keywords = ["merchant", "bandit", "guard", "scholar"]

    for keyword in humanoid_keywords:
        if keyword in npc.template_id.lower():
            return "they"  # Gender-neutral for humanoids

    # Animals/creatures use "it"
    return "it"


def _get_verb_form(pronoun: str) -> str:
    """Get proper verb form for pronoun."""
    if pronoun in ("he", "she", "it"):
        return "is"
    else:  # they
        return "are"


def get_short_health_status(npc: NPCInstance) -> str:
    """
    Get short health status for room descriptions.

    Returns simple text like "looks healthy", "has some wounds", etc.
    Used in look command when showing NPCs in room.
    """
    if npc.max_hp <= 0:
        return "looks strange"

    hp_percent = (npc.current_hp / npc.max_hp) * 100

    if hp_percent >= 75:
        return "looks healthy"
    elif hp_percent >= 50:
        return "has some wounds"
    elif hp_percent >= 25:
        return "is badly wounded"
    else:
        return "is near death"
```

---

## Equipment Display Formatter

### Equipment Display System

**File:** `/src/waystone/game/systems/npc_display.py` (continued)

```python
from waystone.game.commands.base import CommandContext


EQUIPMENT_SLOTS = {
    "head": "worn on head",
    "body": "worn on body",
    "hands": "worn on hands",
    "legs": "worn on legs",
    "feet": "worn on feet",
    "main_hand": "wielded",
    "off_hand": "worn on off-hand",
    "accessory": "worn as accessory",
}

SLOT_ORDER = [
    "head",
    "body",
    "hands",
    "legs",
    "feet",
    "main_hand",
    "off_hand",
    "accessory",
]


async def display_npc_equipment(ctx: CommandContext, npc: NPCInstance) -> None:
    """
    Display NPC equipment in formatted slot layout.

    Format:
    <worn on body>      grey robes of the Archives
    <worn on head>      a small silver pin
    <wielded>           rusty shortsword
    <off-hand>          nothing

    Args:
        ctx: Command context for output
        npc: NPC instance to display equipment for
    """
    if not npc.equipment:
        await ctx.connection.send_line("  Nothing equipped.")
        return

    # Display equipped items in standard slot order
    for slot in SLOT_ORDER:
        slot_label = EQUIPMENT_SLOTS.get(slot, slot)
        item_id = npc.equipment.get(slot)

        if item_id:
            # Get item display name from template
            item_name = get_item_display_name(item_id)

            # Format: <slot label> padded to 20 chars, then item name
            await ctx.connection.send_line(
                f"  <{slot_label:.<18}> {colorize(item_name, 'YELLOW')}"
            )
        else:
            # Show "nothing" for key slots (weapon, body armor)
            if slot in ("main_hand", "off_hand", "body"):
                await ctx.connection.send_line(
                    f"  <{slot_label:.<18}> {colorize('nothing', 'DIM')}"
                )


def get_item_display_name(item_id: str) -> str:
    """
    Get display name for an item from its template ID.

    Args:
        item_id: Item template identifier

    Returns:
        Human-readable item name

    Examples:
        "rusty_shortsword" -> "a rusty shortsword"
        "leather_armor_worn" -> "worn leather armor"
    """
    # TODO: Load from item templates when implemented
    # For now, use simple conversion

    # Remove underscores, convert to words
    words = item_id.replace('_', ' ')

    # Add article if not present
    if not words.startswith(('a ', 'an ', 'the ')):
        # Simple article logic (can be enhanced)
        if words[0].lower() in 'aeiou':
            words = f"an {words}"
        else:
            words = f"a {words}"

    return words


def find_npc_by_keywords(room_id: str, search_term: str) -> NPCInstance | None:
    """
    Find NPC in room by matching keywords.

    Uses fuzzy matching against NPC keywords field.
    More flexible than exact name matching.

    Args:
        room_id: Room to search
        search_term: Player's search input

    Returns:
        Matching NPC or None
    """
    from waystone.game.systems.npc_combat import get_npcs_in_room

    search_lower = search_term.lower()

    for npc in get_npcs_in_room(room_id):
        # Check keywords first (best match)
        if npc.keywords:
            for keyword in npc.keywords:
                if keyword.lower() == search_lower:
                    return npc  # Exact keyword match

        # Fall back to name matching
        if search_lower in npc.name.lower():
            return npc

        # Check short description
        if search_lower in npc.short_description.lower():
            return npc

    return None
```

---

## Implementation Checklists

### Phase 1: Data Model Updates

**Development Checklist:**
- [ ] Add new fields to `NPCTemplate` Pydantic model
  - [ ] `keywords: list[str]`
  - [ ] `short_description: str`
  - [ ] `long_description: str`
  - [ ] `equipment: dict[str, str]`
  - [ ] `inventory: list[str]`
- [ ] Add new fields to `NPCInstance` dataclass
  - [ ] Copy template fields for runtime access
  - [ ] Add `dropped_items: set[str]`
- [ ] Update `spawn_npc()` function to copy new fields
- [ ] Update NPCLoader validation to handle new optional fields

**Testing Checklist:**
- [ ] Test NPCTemplate creation with all new fields
- [ ] Test NPCTemplate creation without new fields (backward compat)
- [ ] Test spawn_npc() copies fields correctly
- [ ] Verify existing YAML files still load
- [ ] Test empty/null values for new fields

**Documentation Checklist:**
- [ ] Document new NPCTemplate fields in docstrings
- [ ] Add YAML schema examples to documentation
- [ ] Update NPC creation guide with new fields

---

### Phase 2: Display Logic Implementation

**Development Checklist:**
- [ ] Create new file: `/src/waystone/game/systems/npc_display.py`
- [ ] Implement `get_health_condition()` function
  - [ ] HP percentage calculation
  - [ ] Condition text mapping
  - [ ] Color coding by severity
  - [ ] Pronoun and verb agreement
- [ ] Implement `get_short_health_status()` for room display
- [ ] Implement `display_npc_equipment()` function
  - [ ] Slot ordering
  - [ ] Item name formatting
  - [ ] "Nothing" display for empty key slots
- [ ] Implement `get_item_display_name()` helper
- [ ] Implement `find_npc_by_keywords()` matching function
- [ ] Create NPC grouping helper: `_group_npcs_by_template()`
- [ ] Create NPC color helper: `_get_npc_color()`
- [ ] Create presence formatter: `_format_npc_room_presence()`
- [ ] Create pluralization helper: `_pluralize_npc_name()`

**Testing Checklist:**
- [ ] Test health conditions at all HP percentages (0%, 25%, 50%, 75%, 100%)
- [ ] Test pronoun selection (humanoid vs creature)
- [ ] Test equipment display with full/partial/no equipment
- [ ] Test item name conversion from template IDs
- [ ] Test NPC keyword matching (exact, partial, fallback)
- [ ] Test NPC grouping (1, 2, 3+ identical NPCs)
- [ ] Test pluralization for various NPC names

**Performance Checklist:**
- [ ] Profile NPC grouping with 10+ NPCs in room
- [ ] Verify keyword matching is O(n) not O(n²)
- [ ] Check memory usage with large equipment dictionaries

---

### Phase 3: Command Integration

**Development Checklist:**
- [ ] Enhance `LookCommand` in `/src/waystone/game/commands/movement.py`
  - [ ] Call `_group_npcs_by_template()` for NPC grouping
  - [ ] Use `_format_npc_room_presence()` for display
  - [ ] Apply `_get_npc_color()` for color coding
  - [ ] Show NPCs after room description, before players
- [ ] Enhance `ExamineCommand` in `/src/waystone/game/commands/inventory.py`
  - [ ] Add NPC priority in target resolution
  - [ ] Call `find_npc_by_keywords()` before item search
  - [ ] Route to `_display_npc_examination()` if NPC found
- [ ] Enhance `ExamineNPCCommand` in `/src/waystone/game/commands/npc.py`
  - [ ] Implement `_display_npc_examination()` function
  - [ ] Call `get_health_condition()` for health display
  - [ ] Call `display_npc_equipment()` for equipment section
  - [ ] Show inventory items
  - [ ] Add behavior-specific hints (merchant, aggressive, etc.)
- [ ] Update `look` alias to route through enhanced ExamineCommand

**Testing Checklist:**
- [ ] Test `look` in empty room (no NPCs)
- [ ] Test `look` with 1 NPC
- [ ] Test `look` with multiple different NPCs
- [ ] Test `look` with multiple identical NPCs (grouping)
- [ ] Test `examine npc` with exact name
- [ ] Test `examine keyword` with keyword match
- [ ] Test `examine npc` with no equipment
- [ ] Test `examine npc` with full equipment
- [ ] Test `examine npc` with partial equipment
- [ ] Test `examine merchant` shows trade hint
- [ ] Test `examine aggressive` shows danger warning
- [ ] Test `look npc` (alias for examine)

**Integration Testing:**
- [ ] Test entering new room shows NPCs automatically
- [ ] Test NPCs persist across look commands
- [ ] Test NPC HP changes reflected in health condition
- [ ] Test equipment changes reflected in examine output
- [ ] Test NPC death removes from room display
- [ ] Test NPC respawn adds back to room display

---

### Phase 4: YAML Data Enhancement

**Development Checklist:**
- [ ] Update `/data/world/npcs/enemies.yaml`
  - [ ] Add keywords to all enemy NPCs
  - [ ] Add short_description to all enemies
  - [ ] Add long_description to all enemies
  - [ ] Add equipment to appropriate enemies (bandit, robber)
- [ ] Update `/data/world/npcs/merchants.yaml`
  - [ ] Add keywords to all merchants
  - [ ] Add short_description to all merchants
  - [ ] Add long_description to all merchants
  - [ ] Add equipment (robes, aprons, etc.)
- [ ] Update `/data/world/npcs/university.yaml` (if exists)
  - [ ] Add full display fields to University NPCs

**Testing Checklist:**
- [ ] Verify all YAML files parse without errors
- [ ] Test loading all NPC templates
- [ ] Verify keywords are searchable in-game
- [ ] Test long_description display in rooms
- [ ] Test equipment display for each NPC type

**Documentation Checklist:**
- [ ] Add YAML template examples to world builder guide
- [ ] Document keyword selection best practices
- [ ] Document equipment slot naming conventions

---

## Technical Specifications

### NPC Color Coding by Behavior

```python
COLOR_MAP = {
    "aggressive": "RED",        # Hostile NPCs
    "training_dummy": "YELLOW", # Practice targets
    "merchant": "CYAN",          # Shop NPCs
    "passive": "GREEN",          # Friendly NPCs
    "stationary": "GREEN",       # Non-aggressive
    "wander": "GREEN",           # Ambient NPCs
}
```

### Equipment Slot Specifications

```python
VALID_EQUIPMENT_SLOTS = {
    "head",      # Helmets, hats, circlets
    "body",      # Armor, robes, shirts
    "hands",     # Gloves, gauntlets
    "legs",      # Pants, greaves
    "feet",      # Boots, shoes
    "main_hand", # Primary weapon
    "off_hand",  # Shield, secondary weapon
    "accessory", # Rings, amulets, pins
}
```

### Health Condition HP Thresholds

```python
HEALTH_THRESHOLDS = [
    (100, "in perfect health", "GREEN"),
    (75, "slightly wounded", "GREEN"),
    (50, "wounded", "YELLOW"),
    (25, "badly wounded", "ORANGE"),
    (10, "near death", "RED"),
    (0, "mortally wounded", "RED"),
]
```

---

## Security & Performance Considerations

### Security Requirements

1. **Input Validation**
   - Sanitize NPC keywords for injection attacks
   - Validate equipment slot names against whitelist
   - Limit keyword list length (max 10 keywords per NPC)
   - Validate item_id references before display

2. **Access Control**
   - No special permissions needed (read-only display)
   - All players can examine all NPCs
   - Equipment display shows only visible items

3. **Data Integrity**
   - Validate NPC template IDs before spawning
   - Handle missing item templates gracefully
   - Prevent null pointer exceptions in equipment display

### Performance Optimization

1. **Caching Strategy**
   - NPCTemplate objects cached at engine startup
   - Item display names can be cached (TODO: implement when item system ready)
   - No database queries for NPC display (all in-memory)

2. **Scalability Targets**
   - Support 50+ NPCs in a single room without lag
   - Keyword matching in <1ms per NPC
   - Room display generation in <10ms total

3. **Memory Management**
   - NPCInstance objects are lightweight (< 1KB each)
   - Equipment dicts use interned strings for keys
   - Keywords lists share common strings

---

## Integration Points

### 1. Item System Integration (Future)

**When item templates are implemented:**
- Replace `get_item_display_name()` stub with real item template lookup
- Load item templates in GameEngine
- Add item description display in equipment section
- Support item properties display (damage, armor value, etc.)

**Interface:**
```python
# Future item integration
from waystone.game.world.item_loader import get_item_template

def get_item_display_name(item_id: str) -> str:
    template = get_item_template(item_id)
    if template:
        return template.name
    return _format_fallback_name(item_id)
```

### 2. Combat System Integration (Existing)

**Current integration points:**
- `get_npcs_in_room()` used by look command
- `NPCInstance.current_hp` updated by combat system
- Health condition reflects combat damage
- NPC death removes from display

**No changes needed** - system already compatible

### 3. Loot System Integration (Future)

**When NPCs drop equipment:**
- Remove item from `npc.equipment` on death
- Add to `npc.dropped_items` set
- Display "The bandit's sword clatters to the ground"
- Update equipment display to show dropped slots

### 4. Dialogue System Integration (Existing)

**Current dialogue support:**
- ExamineNPCCommand already checks `npc.dialogue`
- Merchants show trade hint
- Can be enhanced with dialogue preview in examine

---

## Risk Assessment & Mitigation

### Technical Risks

**Risk 1: YAML Migration Complexity**
- **Severity:** Low
- **Probability:** Low
- **Impact:** Existing NPCs display without enhanced features
- **Mitigation:** All new fields have defaults, backward compatible
- **Contingency:** Gradual migration, old format works fine

**Risk 2: Performance with Many NPCs**
- **Severity:** Medium
- **Probability:** Low
- **Impact:** Room display lag with 50+ NPCs
- **Mitigation:** Efficient grouping algorithm, in-memory operations
- **Contingency:** Add NPC display limit per room, pagination

**Risk 3: Keyword Conflicts**
- **Severity:** Low
- **Probability:** Medium
- **Impact:** Player examines wrong NPC with ambiguous keywords
- **Mitigation:** First-match priority, exact match preferred
- **Contingency:** Add disambiguation prompt, use numeric targeting

**Risk 4: Missing Item Templates**
- **Severity:** Low
- **Probability:** Medium
- **Impact:** Equipment shows as template IDs instead of names
- **Mitigation:** Fallback formatting, clear error logging
- **Contingency:** Display works with template IDs, enhance later

### Implementation Risks

**Risk 5: Integration Bugs with Existing Commands**
- **Severity:** Medium
- **Probability:** Medium
- **Impact:** Look/examine commands break for some users
- **Mitigation:** Comprehensive testing, gradual rollout
- **Contingency:** Feature flag to disable NPC display enhancements

**Risk 6: Incomplete Equipment Data**
- **Severity:** Low
- **Probability:** High
- **Impact:** Many NPCs show "Nothing equipped"
- **Mitigation:** Progressive enhancement, empty equipment valid
- **Contingency:** Add equipment to high-priority NPCs first

---

## Deployment Strategy

### Phase 1: Core Infrastructure (Week 1)
1. Implement data model changes
2. Add new fields to NPCTemplate and NPCInstance
3. Test backward compatibility
4. Deploy to development environment

### Phase 2: Display Functions (Week 1-2)
1. Implement `npc_display.py` module
2. Create health condition generator
3. Create equipment display formatter
4. Unit test all display functions

### Phase 3: Command Integration (Week 2)
1. Enhance LookCommand for NPC display
2. Enhance ExamineCommand for NPC targeting
3. Integration testing with existing systems
4. Deploy to staging environment

### Phase 4: Data Enhancement (Week 2-3)
1. Update enemy NPC YAML files
2. Update merchant NPC YAML files
3. Test all NPCs display correctly
4. Deploy to production

### Phase 5: Polish & Optimization (Week 3)
1. Performance testing with many NPCs
2. User feedback collection
3. Bug fixes and refinements
4. Documentation updates

---

## Testing Strategy

### Unit Tests Required

```python
# test_npc_display.py

def test_health_condition_perfect_health():
    """Test health condition for 100% HP."""
    npc = create_test_npc(current_hp=100, max_hp=100)
    condition = get_health_condition(npc)
    assert "perfect health" in condition.lower()

def test_health_condition_wounded():
    """Test health condition for 50% HP."""
    npc = create_test_npc(current_hp=50, max_hp=100)
    condition = get_health_condition(npc)
    assert "wounded" in condition.lower()

def test_equipment_display_full():
    """Test equipment display with all slots filled."""
    # ... test implementation

def test_equipment_display_empty():
    """Test equipment display with no equipment."""
    # ... test implementation

def test_npc_keyword_matching():
    """Test keyword-based NPC search."""
    # ... test implementation

def test_npc_grouping():
    """Test grouping identical NPCs."""
    # ... test implementation
```

### Integration Tests Required

```python
# test_npc_commands.py

async def test_look_command_shows_npcs():
    """Test look command displays NPCs in room."""
    # ... test implementation

async def test_examine_npc_by_keyword():
    """Test examining NPC by keyword."""
    # ... test implementation

async def test_examine_npc_shows_equipment():
    """Test NPC examination displays equipment."""
    # ... test implementation

async def test_multiple_identical_npcs():
    """Test multiple rats display as 'Three rats are here'."""
    # ... test implementation
```

### Manual Testing Checklist

- [ ] Enter room with single NPC - verify display
- [ ] Enter room with multiple different NPCs - verify all shown
- [ ] Enter room with 3 identical rats - verify "Three rats are here"
- [ ] Examine NPC by full name - verify full examination output
- [ ] Examine NPC by keyword - verify keyword matching works
- [ ] Examine NPC with equipment - verify equipment section
- [ ] Examine NPC with no equipment - verify graceful handling
- [ ] Damage NPC in combat - verify health condition updates
- [ ] Kill NPC - verify removal from room display
- [ ] Wait for respawn - verify NPC reappears in room

---

## Documentation Requirements

### Developer Documentation

1. **NPC Display System Guide**
   - Architecture overview
   - Data flow diagrams
   - API reference for display functions

2. **YAML Schema Documentation**
   - Complete field reference
   - Example NPC definitions
   - Equipment slot reference

3. **Integration Guide**
   - How to add new equipment slots
   - How to extend health conditions
   - How to customize display formatting

### Player Documentation

1. **Updated PLAYER_GUIDE.md**
   - Explain NPC display in rooms
   - Explain examine command for NPCs
   - Show example outputs

2. **Updated COMMANDS.md**
   - Document `examine <npc>` command
   - Document `look <npc>` alias
   - Show example usage

---

## Success Criteria

### Feature Completeness
- ✅ NPCs automatically shown when entering rooms
- ✅ NPCs shown when using `look` command
- ✅ `examine <npc>` shows full NPC details
- ✅ `look <npc>` works as alias for examine
- ✅ Equipment display shows worn/wielded items
- ✅ Health condition shows descriptive text (not numbers)
- ✅ Multiple identical NPCs grouped intelligently
- ✅ Color coding by NPC behavior/threat level

### Quality Metrics
- ✅ All unit tests passing (>95% coverage)
- ✅ All integration tests passing
- ✅ No performance degradation in room display (<10ms)
- ✅ Backward compatible with existing NPCs
- ✅ Zero database migrations required
- ✅ Documentation complete and accurate

### User Experience
- ✅ Room descriptions feel alive with NPC presence
- ✅ NPC examination provides useful information
- ✅ Equipment display is clear and readable
- ✅ Health conditions are intuitive
- ✅ Keyword matching feels natural
- ✅ No confusing error messages

---

## Future Enhancements

### Phase 2 Features (Not in Current Scope)

1. **Dynamic NPC Actions**
   - NPCs perform actions visible in room descriptions
   - "A merchant counts coins behind the counter."
   - Actions based on NPC behavior and state

2. **NPC Mood/Status**
   - Emotional state affects descriptions
   - "The merchant looks pleased with recent sales."
   - Affects dialogue options and prices

3. **Time-Based Descriptions**
   - NPCs change behavior by time of day
   - "The guard yawns, tired from the night watch."
   - Supports day/night cycle integration

4. **NPC Relationships**
   - Track NPC opinions of players
   - Reflected in examination descriptions
   - "The merchant eyes you with suspicion."

5. **Advanced Equipment Display**
   - Show item condition (damaged, pristine)
   - Show magical auras/enchantments
   - Show combat bonuses from equipment

---

## Conclusion

This architecture plan provides a comprehensive, implementable design for NPC display features in Waystone MUD. The system is designed to be:

- **Backward Compatible** - Existing NPCs work without modification
- **Performant** - All operations in-memory, <10ms display time
- **Extensible** - Easy to add new equipment slots, health conditions
- **Maintainable** - Clean separation of concerns, well-documented
- **Player-Friendly** - Follows MUD conventions, intuitive UX

### Key Design Decisions

1. **Three-field naming system** - Supports flexible targeting and rich descriptions
2. **Template-based equipment** - Equipment defined in YAML, easy to modify
3. **In-memory NPC instances** - No database overhead for display
4. **Descriptive health conditions** - Player-friendly, no numeric HP shown
5. **Keyword-based targeting** - More intuitive than exact name matching

### Implementation Order

1. Data models (foundational)
2. Display functions (core logic)
3. Command integration (user-facing)
4. YAML enhancement (content)
5. Testing and polish (quality)

The system can be implemented incrementally with each phase delivering value independently. Estimated total development time: **9-13 hours**.

---

**Plan Status:** Ready for Implementation
**Review Date:** 2025-12-09
**Next Step:** Begin Phase 1 - Data Model Updates
