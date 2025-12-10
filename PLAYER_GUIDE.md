# Waystone MUD - Player Guide

Welcome to the Four Corners! This guide will help you navigate the world of the Kingkiller Chronicle.

## Getting Started

### Connecting

```bash
telnet localhost 4000
# or
telnet your-server-address 4000
```

### Creating an Account

1. **Register**: `register <username> <password> <email>`
2. **Login**: `login <username> <password>`

### Creating a Character

1. View existing characters: `characters`
2. Create new character: `create <name>`
3. Choose a background when prompted:
   - **Soldier** - Combat-focused, bonus to Strength
   - **Scholar** - Magic-focused, bonus to Intelligence
   - **Merchant** - Trade-focused, bonus to Charisma
   - **Traveler** - Balanced, bonus to Constitution
   - **Noble** - Social, bonus to Charisma
   - **Peasant** - Hardworking, bonus to Constitution
4. Enter the world: `play <name>`

---

## Basic Commands

### Movement

| Command | Description |
|---------|-------------|
| `north` or `n` | Move north |
| `south` or `s` | Move south |
| `east` or `e` | Move east |
| `west` or `w` | Move west |
| `up` or `u` | Move up |
| `down` or `d` | Move down |
| `northeast` or `ne` | Move northeast |
| `northwest` or `nw` | Move northwest |
| `southeast` or `se` | Move southeast |
| `southwest` or `sw` | Move southwest |
| `go <direction>` | Move in any direction |
| `look` or `l` | Look at your surroundings |
| `exits` | Show available exits |

### Communication

| Command | Description |
|---------|-------------|
| `say <message>` | Speak to everyone in the room |
| `'<message>` | Shortcut for say |
| `emote <action>` | Perform an emote (e.g., `emote waves`) |
| `:<action>` | Shortcut for emote |
| `chat <message>` | Global chat channel |
| `tell <player> <message>` | Private message to a player |

### Information

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `help <command>` | Get help on a specific command |
| `score` | View your character stats |
| `who` | See who's online |
| `time` | Check the in-game time |
| `save` | Save your character |

---

## Inventory & Equipment

| Command | Description |
|---------|-------------|
| `inventory` or `inv` or `i` | View your inventory |
| `equipment` or `eq` | View equipped items |
| `get <item>` | Pick up an item |
| `drop <item>` | Drop an item |
| `examine <item>` | Look at an item closely |
| `equip <item>` | Equip a weapon or armor |
| `unequip <slot>` | Remove equipped item |
| `give <item> to <player>` | Give item to another player |

**Equipment Slots:**
- `weapon` - Main weapon
- `off_hand` - Shield or secondary item
- `head` - Helmets, hats
- `body` - Armor, robes
- `hands` - Gloves
- `feet` - Boots
- `ring` - Rings (up to 2)
- `neck` - Amulets, necklaces

---

## Combat

### Basic Combat

| Command | Description |
|---------|-------------|
| `attack <target>` or `kill <target>` | Attack an enemy |
| `defend` | Take a defensive stance |
| `flee` | Attempt to escape combat |
| `cs` or `combatstatus` | View combat status |

### Combat Tips

- Check enemy difficulty with `consider <npc>` before fighting
- Equip weapons and armor before combat
- Use `defend` when low on health
- `flee` has a chance to fail based on your Dexterity

### Difficulty Ratings

When you `consider` an enemy:
- **Trivial** - Easy victory
- **Easy** - Low risk
- **Moderate** - Fair fight
- **Hard** - Dangerous
- **Deadly** - Very high risk
- **Impossible** - Certain death

---

## Character Development

### Attributes

| Attribute | Effect |
|-----------|--------|
| **Strength (STR)** | Physical damage, carrying capacity |
| **Dexterity (DEX)** | Accuracy, dodge chance, flee success |
| **Constitution (CON)** | Health points, stamina |
| **Intelligence (INT)** | Magic power, Alar strength |
| **Wisdom (WIS)** | Magic defense, Alar control |
| **Charisma (CHA)** | NPC interactions, prices |

### Increasing Attributes

When you level up, you gain attribute points:
- `increase strength` or `increase str`
- `increase dexterity` or `increase dex`
- etc.

### Leveling Up

- Gain experience from combat and quests
- Level up grants: +10 HP, +5 MP, +1 attribute point
- Maximum level: 50

---

## Sympathy Magic

Sympathy is the art of creating links between objects to transfer energy.

### Heat Sources

Before using sympathy, you need a heat source:
- `hold candle` - Low energy, safe
- `hold torch` - Medium energy
- `hold brazier` - High energy (must be in room)
- `hold body` - **DANGEROUS** - uses your body heat

### Creating Bindings

1. Hold a heat source: `hold <item>`
2. Create a binding: `bind <type> <source> <target>`

**Binding Types:**
- `heat` - Transfer heat between objects
- `kinetic` - Transfer force/motion
- `damage` - Combat damage transfer
- `light` - Light manipulation
- `dowse` - Locate similar objects

### Using Bindings

| Command | Description |
|---------|-------------|
| `heat [amount]` | Transfer heat through active binding |
| `push [force]` | Push with kinetic force |
| `cast damage <target>` | Deal sympathetic damage |
| `bindings` | View your active bindings |
| `release [all\|number]` | Release bindings |
| `sympathy` | View sympathy skill status |

### Sympathy Ranks

| Rank | Efficiency Cap |
|------|----------------|
| Untrained | 30% |
| E'lir | 50% |
| Re'lar | 65% |
| El'the | 80% |
| Master | 90% |
| Arcane Master | 95% |

### Backlash Warning

Using sympathy carelessly can cause **backlash**:
- Minor: Headache, slight MP loss
- Moderate: Unconsciousness
- Severe: Stat damage, injury
- Critical: Potential death

**Body heat is especially dangerous!** Only use as a last resort.

---

## Trading & Economy

### Currency

The Four Corners uses a talent-based currency system:
- Iron Drabs (smallest)
- Copper Jots
- Silver Talents
- Gold Marks (largest)

### Merchant Commands

| Command | Description |
|---------|-------------|
| `list` | View merchant's wares |
| `buy <item>` | Purchase an item |
| `sell <item>` | Sell an item |
| `appraise <item>` | Check an item's value |

---

## NPCs

### Interacting with NPCs

| Command | Description |
|---------|-------------|
| `consider <npc>` | Assess NPC's combat level |
| `examine <npc>` | Look at an NPC |
| `talk <npc>` | Start conversation (if available) |

### NPC Types

- **Friendly** - Can be talked to, may give quests
- **Neutral** - Won't attack unless provoked
- **Aggressive** - Will attack on sight
- **Merchant** - Buy and sell items

---

## Tips for New Players

1. **Save often** - Use the `save` command regularly
2. **Check difficulty** - Always `consider` enemies before fighting
3. **Explore** - Use `look` and `exits` to navigate
4. **Read descriptions** - Important hints are in room descriptions
5. **Start small** - Fight easier enemies to gain experience
6. **Manage resources** - Keep track of health and equipment
7. **Learn sympathy** - Magic is powerful but dangerous

---

## Shortcuts

| Shortcut | Command |
|----------|---------|
| `'` | say |
| `:` | emote |
| `n/s/e/w` | Movement |
| `u/d` | up/down |
| `l` | look |
| `i` | inventory |
| `eq` | equipment |
| `cs` | combatstatus |

---

## Social Emotes

Express yourself with fun social actions! Type `emotes` to see all available emotes.

### Using Emotes

| Command | Description |
|---------|-------------|
| `emotes` | List all available social emotes |
| `<emote>` | Perform the emote |
| `<emote> <player>` | Direct the emote at a player |

### Emote Categories

**Expressions**
- `laugh` / `giggle` / `chuckle` / `snicker` / `guffaw` / `cackle`
- `grin` / `smile` / `smirk` / `wink`

**Greetings**
- `wave` / `bow` / `curtsy` / `salute` / `nod`

**Gestures**
- `shrug` / `point` / `clap` / `applaud` / `thumbsup`
- `facepalm` / `headshake` / `eyeroll`

**Emotions**
- `sigh` / `groan` / `cry` / `sob` / `pout`
- `blush` / `gasp` / `panic`

**Physical**
- `stretch` / `yawn` / `flex` / `strut` / `twirl`

**Social**
- `hug` / `highfive` / `nudge` / `poke` / `pat`
- `bonk`

**Dance Moves**
- `dance` / `jig` / `moonwalk` / `dab` / `twerk`

**Bodily Functions**
- `burp` / `fart` / `sneeze` / `hiccup` / `cough`

### Examples

```
> laugh
You throw back your head and laugh heartily!
(Others see: PlayerName throws back their head and laughs heartily!)

> wink Bob
You wink suggestively at Bob.
(Bob sees: PlayerName winks suggestively at you.)
(Others see: PlayerName winks suggestively at Bob.)

> fart
You let loose a thunderous fart that echoes through the room.
(Others see: PlayerName lets loose a thunderous fart. Everyone pretends not to notice.)
```

---

## The University & Arcanum

### Joining the Arcanum

1. Go to the University (from Stonebridge, go north)
2. Find the Hollows (administration building)
3. Use `admit` to take the admission examination
4. Answer the Masters' questions about magic, history, and theory
5. If admitted, pay your tuition with `tuition pay`

### Arcanum Ranks

| Rank | Description |
|------|-------------|
| **E'lir** | "Listener" - First rank, access to basic University |
| **Re'lar** | "Speaker" - Second rank, deeper Archives access |
| **El'the** | "Seer" - Third rank, full Archives access |

### University Commands

| Command | Description |
|---------|-------------|
| `admit` | Take the admission examination |
| `tuition` | Check tuition status |
| `tuition pay` | Pay your tuition for the term |
| `rank` | View your Arcanum standing and Master reputations |
| `work <job>` | Work a University job for money |

### University Jobs

| Job | Location | Pay | Requirement |
|-----|----------|-----|-------------|
| `work scriv` | Archives | 25 jots | E'lir |
| `work medica` | Medica | 1 talent | E'lir |
| `work artificery` | Artificery | 50 jots | None |

### Master Reputations

Your standing with each of the Nine Masters affects:
- Your tuition amount (better reputation = lower tuition)
- Access to advanced training
- Quest availability

Improve reputation by:
- Answering admission questions well
- Working University jobs
- Attending classes (future feature)

---

## The Fae Realm

### Finding the Fae

The Fae is a shadow realm accessible through ancient greystones - the standing stones found near Imre. Travel to the Greystones (from Imre North Road) and at twilight, type `enter fae` to step through.

### The Cthaeh

Deep in the Fae, in the Cthaeh's Clearing, dwells an ancient oracle. It speaks only truth - but uses truth as a weapon. The Sithe, immortal hunters, kill anyone who speaks with it.

**Warning:** Speaking to the Cthaeh is dangerous. Accepting its curse is **permanent and irreversible**.

### Fae Commands

| Command | Description |
|---------|-------------|
| `enter fae` | Enter the Fae realm at greystones |
| `speak cthaeh` | Speak to the Cthaeh (PERMANENT) |
| `embrace curse` | Accept the curse (CANNOT BE UNDONE) |
| `curse` | View your curse status |
| `leavefae` | Return to the mortal world |

### The Curse

If you accept the Cthaeh's curse, you gain:
- **+15% damage** on all attacks
- **+10% critical hit chance** (on top of natural 20)
- **+3 to STR, DEX, CON** attributes

But in exchange, the Cthaeh assigns "biddings" - targets you must kill within 24 hours:
- **Success**: +50% bonus XP for the kill
- **Failure**: Lose buffs, get -10% stat debuff for 4 hours

The curse is **permanent**. Choose wisely.

---

## Getting Help

- `help` - List all commands
- `help <command>` - Detailed help on a command
- `who` - See online players who might help
- `guide <topic>` - View guides: combat, sympathy, university, fae

Good luck in the Four Corners, and may your Alar be strong!
