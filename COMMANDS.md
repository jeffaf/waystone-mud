# Waystone MUD - Command Reference

A comprehensive list of all commands available in Waystone MUD.

## Movement Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `north` | `n` | Move north |
| `south` | `s` | Move south |
| `east` | `e` | Move east |
| `west` | `w` | Move west |
| `up` | `u` | Move up |
| `down` | `d` | Move down |
| `northeast` | `ne` | Move northeast |
| `northwest` | `nw` | Move northwest |
| `southeast` | `se` | Move southeast |
| `southwest` | `sw` | Move southwest |
| `go <direction>` | | Move in specified direction |
| `look` | `l` | View current room details |
| `exits` | | List available exits |
| `enter <portal>` | | Enter portals or special passages |

## Combat Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `attack <target>` | `kill`, `hit` | Attack an NPC |
| `defend` | `def` | Take defensive stance (+2 AC, -2 attack) |
| `flee` | `run`, `escape` | Attempt to flee from combat |
| `consider <npc>` | `con` | Assess enemy difficulty before fighting |
| `combatstatus` | `cs` | View detailed combat status |

## Information Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `score` | `stats`, `sc` | Display character stats, XP, level |
| `who` | | List online players |
| `time` | | Display server/game time |
| `help [command]` | `?` | Show help for commands |
| `guide [topic]` | `manual`, `tutorial` | View player guide |
| `wealth` | `worth`, `money`, `gold` | Display current money |

## Inventory & Equipment

| Command | Aliases | Description |
|---------|---------|-------------|
| `inventory` | `i`, `inv` | List items in inventory |
| `equipment` | `eq` | Show equipped items |
| `get <item>` | `take`, `pick` | Pick up item from ground |
| `drop <item>` | | Drop item on ground |
| `examine <item>` | `ex`, `x` | Look at item details |
| `equip <item>` | `wield`, `wear` | Equip weapon or armor |
| `unequip <slot>` | `remove` | Remove equipped item |
| `give <item> to <player>` | | Give item to another player |

### Equipment Slots
- `weapon` - Primary weapon
- `off_hand` - Shield or secondary item
- `head` - Helmets, hats
- `body` - Armor, robes
- `hands` - Gloves, gauntlets
- `feet` - Boots, shoes
- `ring` - Rings
- `neck` - Amulets, necklaces

## Communication Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `say <message>` | `'<message>` | Speak to the room |
| `emote <action>` | `:<action>` | Perform an emote/action |
| `chat <message>` | `ooc` | Global chat channel |
| `tell <player> <message>` | `whisper`, `msg` | Private message |

## Character Management

| Command | Aliases | Description |
|---------|---------|-------------|
| `characters` | `chars` | List your characters |
| `create <name>` | | Create new character |
| `play <name>` | `select` | Enter game as character |
| `delete <name>` | | Delete a character |
| `increase <attribute>` | `inc` | Spend attribute point |
| `save` | | Manually save character |
| `logout` | | Return to character select |
| `quit` | `exit`, `disconnect` | Disconnect from server |

### Attribute Shortcuts
- `str`, `s` - Strength
- `dex`, `d` - Dexterity
- `con`, `c` - Constitution
- `int`, `i` - Intelligence
- `wis`, `w` - Wisdom
- `cha`, `ch` - Charisma

## Authentication

| Command | Aliases | Description |
|---------|---------|-------------|
| `login <user> <pass>` | | Log into account |
| `register <user> <pass> <email>` | | Create new account |

## Sympathy Magic System

Sympathy creates magical links between objects to transfer energy.

### Setup Commands

| Command | Description |
|---------|-------------|
| `hold <source>` | Hold a heat source (candle, torch, brazier, body) |
| `release` | Release held source |
| `bind <type> <source> <target>` | Create sympathetic binding |
| `unbind [number]` | Remove a binding |
| `bindings` | List active bindings |
| `alar` | Check Alar (mental focus) status |

### Binding Types
- `heat` - Transfer thermal energy
- `kinetic` - Transfer motion/force
- `damage` - Combat damage link

### Casting Commands

| Command | Description |
|---------|-------------|
| `heat [amount]` | Transfer heat through binding |
| `push [force]` | Kinetic push through binding |
| `cast damage <target>` | Attack using sympathy |

### Slippage & Heat Sources
Each source has different efficiency (slippage):
- Brazier: 10% slippage (best)
- Torch: 20% slippage
- Candle: 30% slippage
- Body heat: 5% slippage (dangerous - damages caster!)

## Economy & Trading

| Command | Aliases | Description |
|---------|---------|-------------|
| `wealth` | `money`, `gold` | Check your money |
| `buy <item>` | `purchase` | Buy from merchant |
| `sell <item>` | | Sell to merchant |
| `list` | `wares` | View merchant inventory |
| `barter` | `haggle` | Attempt to negotiate price |
| `appraise <item>` | | Get item value estimate |

### Cealdish Currency (smallest to largest)
- Iron drabs (1 drab)
- Copper jots (10 drabs)
- Silver talents (100 jots)
- Gold marks (10 talents)

## University System

Available when at the University location.

| Command | Aliases | Description |
|---------|---------|-------------|
| `admit` | `admission`, `apply` | Request admission to University |
| `tuition [pay]` | `pay` | Check or pay tuition |
| `rank` | `standing`, `arcanum` | Check Arcanum rank and standing |
| `work <job>` | `job` | Work a University job |

### University Jobs
- `scriv` - Archives work (E'lir+ rank, 25 jots)
- `medica` - Medical assistant (E'lir+ rank, 1 talent)
- `artificery` - Artificery helper (any rank, 50 jots)

### Arcanum Ranks
1. E'lir - "Listener" (entry rank)
2. Re'lar - "Speaker" (advanced)
3. El'the - "Seer" (master)

## NPC Interactions

| Command | Description |
|---------|-------------|
| `look <npc>` | Examine an NPC |
| `talk <npc>` | Start conversation |
| `give <item> to <npc>` | Give item to NPC |
| `attack <npc>` | Initiate combat |
| `consider <npc>` | Check difficulty |

## Quick Reference

### Essential Shortcuts
```
n/s/e/w/u/d     - Move
l               - Look around
i               - Inventory
eq              - Equipment
'message        - Say something
:action         - Emote
```

### Combat Quick Start
```
consider rat    - Check if you can win
attack rat      - Start fighting
cs              - Check combat status
flee            - Run away if losing
```

### Sympathy Quick Start
```
hold candle     - Hold heat source
bind heat candle target - Create binding
heat 10         - Transfer 10 units of heat
unbind          - Release binding
```

## Experience & Leveling

XP is gained from:
- Killing NPCs (10 × enemy level, bonus for higher-level enemies)
- Exploring new rooms (25 XP)
- First login (100 XP)
- Completing quests (100+ XP)

Level requirements follow quadratic scaling:
- Level 2: 100 XP total
- Level 3: 400 XP total
- Level 4: 1000 XP total
- Level 5: 2000 XP total

Each level grants:
- 1 attribute point
- Increased max HP (5 + CON modifier per level)
- Full HP restoration
