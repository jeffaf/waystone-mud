# Vintage BBS Research Report
## For Kingkiller Chronicle MUD Implementation

**Research Date:** January 25, 2025
**Purpose:** Design a BBS feature for a Kingkiller Chronicle themed MUD where characters like Elodin and Ambrose leave posts

---

## Table of Contents
1. [BBS Culture & History](#bbs-culture--history)
2. [Core BBS Features](#core-bbs-features)
3. [Renegade BBS](#renegade-bbs)
4. [WWIV BBS](#wwiv-bbs)
5. [Elite/Warez Boards](#elitewarez-boards)
6. [Common BBS Commands](#common-bbs-commands)
7. [Visual Style & ANSI Art](#visual-style--ansi-art)
8. [Social Dynamics](#social-dynamics)
9. [MUD Integration Recommendations](#mud-integration-recommendations)
10. [Kingkiller Chronicle Adaptation](#kingkiller-chronicle-adaptation)

---

## BBS Culture & History

### The Glory Days (1978-1996)

Bulletin Board Systems emerged from the Great Blizzard of 1978 when Ward Christensen and Randy Suess created the first public dial-up BBS - the **Computerized Bulletin Board System (CBBS)**. By 1994, an estimated **60,000 BBSes** served **17 million users** in the United States alone.

**The BBS Experience:**
- A home computer (Apple II, Commodore 64, IBM PC) in a basement or bedroom
- Connected via modem to a second phone line
- Single-node systems meant one caller at a time
- Users would read/post messages, upload/download files, play games, and chat with the SysOp

> "The BBS scene of the 80s and 90s was a magical time. Long before the Internet escaped from the lab, there was a brave and pioneering band of computer users who spent their time, money and sanity setting up their systems."

**Peak and Decline:**
- FidoNet BBSes reached peak usage around 1996
- The World Wide Web and AOL's mainstream adoption caused rapid decline
- By the late 1990s, Telnet BBSes replaced dial-up systems
- Today, approximately 900-1000 BBSes remain active via Internet

---

## Core BBS Features

### Message Boards (Forums)
The heart of any BBS. Users could:
- **Post** new messages to topic-specific boards
- **Read** messages from other users
- **Reply** to existing threads
- **Scan** for new messages since last login
- Messages were typically public, readable by anyone with appropriate access level

### File Areas
- Software libraries for uploading/downloading
- Often categorized by type (games, utilities, graphics)
- Upload/download ratios enforced (e.g., 1:3 or 1:10)
- CD-ROM support for larger file libraries

### Door Games
External programs that ran within the BBS:
- **Legend of the Red Dragon (LORD)** - Fantasy RPG with social features
- **TradeWars 2002** - Space trading/combat strategy
- **Usurper**, **Solar Realms Elite**, **MajorMUD**
- Games had daily turn limits and persistent state

### Chat Systems
- One-on-one chat with SysOp
- Multi-line chat rooms (on multi-node systems)
- Private messaging between users

### User Access Levels
```
LEVEL          ACCESS
------         ------
New User       Minimal access, pending validation
Validated      Basic message/file access
Regular        Full message boards, file downloads
Elite          Premium areas, reduced ratios
SysOp          Full system control
```

---

## Renegade BBS

### History
- Originally written by **Cott Lang** in Turbo Pascal
- Based on Telegard source code (which derived from WWIV)
- Gained popularity in early-to-mid 1990s
- Development ceased April 23, 1997
- Current version: v1.35 (still maintained at rgbbs.info)

### Key Features
- DOS-based dial communication system
- Message areas with threading
- Interactive chat
- File downloads with ratio enforcement
- Lightbar menus (navigation with arrow keys)
- Fully customizable menu system

### Menu Structure

**Main Menu Commands:**
```
(M) Message Base     - Access message forums
(F) File Base        - Browse/download files
(D) Door Games       - External games
(C) Chat             - Chat with SysOp or users
(S) User Stats       - View your statistics
(O) Operator Page    - Page the SysOp
(U) User List        - View other users
(X) Expert Mode      - Toggle brief/full menus
(G) Goodbye          - Log off
(Q) Quit             - Return to previous menu
```

**SysOp Menu Commands:**
```
(B) Board Editor     (V) Voting Editor
(C) Change to User   (L) SysOp Logs
(D) Pseudo-DOS       (M) Mail Read
(E) Event Editor     (N) Text Editor
(F) File Base Editor (P) System Config
(U) User Editor      (X) Protocol Edit
($) Conf Editor      (Z) System Log
(%) Pack Messages    (*) SysOp Menu
```

**Function Keys (SysOp):**
```
F1 = System Keys Help
F2 = Edit user with warning
F5 = Split screen chat
ALT-C = Line Chat
ALT-S = Split Screen Chat
```

### Lightbar Navigation
Renegade pioneered "lightbar" menus - users could navigate using arrow keys instead of typing commands:
```
  [ ] Message Forums
  [*] File Libraries     <-- Highlighted selection
  [ ] Door Games
  [ ] User Statistics
```

---

## WWIV BBS

### History
- Created in the late 1980s, peaked in early-mid 1990s
- Originally written in Basic, ported to Pascal, C, then C++
- **Modifiable source code** - SysOps could customize the main program
- Spawned WWIVnet - tens of thousands of linked BBSes
- Current version: WWIV v5 (Open Source, Apache License v2.0)

### Messaging System

**Sub-Boards Configuration:**
| Setting | Purpose |
|---------|---------|
| Name | Topic description (shown in sub listing) |
| Filename | Unique 8-character identifier |
| Read SL | Security level required to read |
| Post SL | Security level required to post |
| Anony | Anonymous posting (no/yes/forced/dear abby) |
| Max msgs | Maximum before auto-purge (up to 999) |
| AR | Access restrictions (flags A-P) |
| Req ANSI | Require ANSI capability |

**Network Features:**
- Native WWIVnet networking
- Native FidoNet (FTN) support
- Native QWK support for offline reading
- Cross-BBS message sharing via Echomail

**Messaging Commands:**
```
N     - Scan for new messages across all subs
S     - Read messages on current sub
P     - Post a new message
R     - Reply to current message
Q     - Quit to previous menu
```

### ANSI Color Codes

**Pipe Color Codes (for menus/displays):**
```
|#0 = Reset/Default    |#5 = Magenta
|#1 = Blue             |#6 = Brown
|#2 = Green            |#7 = Light Gray
|#3 = Cyan             |#8 = Dark Gray
|#4 = Red              |#9 = Bright Colors
```

**Color Value System:**
```
0 = Black       8 = Dark Gray
1 = Blue        9 = Light Blue
2 = Green      10 = Light Green
3 = Cyan       11 = Light Cyan
4 = Red        12 = Light Red
5 = Magenta    13 = Light Magenta
6 = Brown      14 = Yellow
7 = Light Gray 15 = White

Background = (background_color * 16) + foreground_color
```

---

## Elite/Warez Boards

### The Underground Scene

Elite boards (also called "WaReZ" or "pirate" boards) distributed cracked software, phreaking materials, and other illicit content. They operated as invitation-only communities with strict verification.

### Access Verification Methods

**New User Interrogation:**
1. "What does ACiD stand for?" (testing scene knowledge)
2. "What is the CDC?" (Cult of the Dead Cow - hacker group)
3. "What other boards do you have Full Access on?"
4. "What members here will vouch for you?"
5. "What are your top three appz/gamez?" (recent releases)
6. Upload requirement: "Upload the piratedest software you have"

> "There was really no single litmus test - it was all about who you knew."

### Elite Board Characteristics

**Strict Ratios:**
- Typical: 1:3 (1MB upload for every 3MB download)
- "Locals that were not prepared to upload the latest stuff ended up being nuked"
- Disabled ratios only for trusted members

**Infrastructure:**
- Multiple phone lines
- Up to 100MB storage (expensive at the time)
- Part of national/international warez networks

**Courier System:**
- "Warez couriers" transported software between boards
- Larger central boards fed smaller feeder boards
- Speed and freshness were paramount

### Leetspeak Origins
Elite boards spawned leetspeak:
```
Elite -> 31337 -> LEET
Warez -> W4r3Z
Hacker -> H4X0R
```

---

## Common BBS Commands

### Universal Navigation
```
COMMAND    ACTION
-------    ------
?  or H    Help menu
Q          Quit/Return to previous menu
G or B     Goodbye/Bye (log off)
X          Toggle expert mode (brief menus)
```

### Message Commands
```
COMMAND    ACTION
-------    ------
N          New message scan (all boards)
R          Read messages
R #        Read specific message number
RM         Read messages TO you
RN         Read NEW messages to you
L          List new messages since last login
LM         List messages addressed to you
LL #       List last # messages
P or S     Post/Send new message
SR         Reply to current message
K #        Kill/Delete message
```

### File Commands
```
COMMAND    ACTION
-------    ------
D          Download file
U          Upload file
F          File search
L          List files in current area
N          New files scan
```

### User Commands
```
COMMAND    ACTION
-------    ------
O          Operator page (call SysOp)
C          Comment to SysOp
W          Who's online
U          User list
S          Your statistics
I          User info/profile
```

---

## Visual Style & ANSI Art

### The ANSI Art Form

ANSI art uses IBM Code Page 437's 256 characters combined with ANSI escape sequences for color. It was the visual language of the BBS era.

**Character Set Elements:**
- Box-drawing characters: `┌─┐│└┘├┤┬┴┼`
- Block characters: `█▓▒░`
- Shading characters for dithering effects
- Accented letters and mathematical symbols

### Color Palette (16 Colors)

**Standard ANSI Foreground Colors (30-37):**
```
\e[0;30m  Black       \e[0;34m  Blue
\e[0;31m  Red         \e[0;35m  Magenta
\e[0;32m  Green       \e[0;36m  Cyan
\e[0;33m  Yellow      \e[0;37m  White
```

**Bright/High Intensity Colors (90-97):**
```
\e[0;90m  Dark Gray   \e[0;94m  Light Blue
\e[0;91m  Light Red   \e[0;95m  Light Magenta
\e[0;92m  Light Green \e[0;96m  Light Cyan
\e[0;93m  Light Yellow \e[0;97m  Bright White
```

**Background Colors (40-47):**
```
\e[40m Black    \e[44m Blue
\e[41m Red      \e[45m Magenta
\e[42m Green    \e[46m Cyan
\e[43m Yellow   \e[47m White
```

### Welcome Screens

The welcome screen was the first impression - ranging from simple logos to elaborate artworks:

**Common Elements:**
- BBS name in large stylized font
- SysOp name and contact info
- Node number and line count
- Modem speed/connection info
- Theme-appropriate artwork

**Example Structure:**
```
┌──────────────────────────────────────────┐
│  ▄▄▄▄   ▄▄▄▄   ▄▄▄▄                      │
│  █  █   █  █   █  █  THE DRAGON'S LAIR   │
│  █▄▄█   █▄▄█   █▄▄█                      │
│  █  █   █  █   █  █  SysOp: Bahamut      │
│  ▀▀▀▀   ▀▀▀▀   ▀▀▀▀                      │
├──────────────────────────────────────────┤
│  Node 1 of 4  │  14.4k HST  │  Online!   │
├──────────────────────────────────────────┤
│  Enter your handle: _                    │
└──────────────────────────────────────────┘
```

### ANSI Art Groups

**Major Groups:**
- **ACiD** (ANSI Creators in Demand) - Early influential group
- **iCE** (Insane Creators Enterprise) - Major rival to ACiD
- **Blade** - Known for artistic innovation
- **Dark Illustrated** - High quality artwork

Artpacks were released monthly, driving competition and innovation.

### Menu Layout Patterns

**Typical Main Menu:**
```
╔══════════════════════════════════════════════════════╗
║           ▄▄▄  THE DRAGON'S LAIR BBS  ▄▄▄            ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║   [M]essage Forums      [F]ile Libraries             ║
║   [D]oor Games          [B]ulletins                  ║
║   [C]hat System         [U]ser List                  ║
║   [S]tatistics          [O]perator Page              ║
║   [G]oodbye             [?] Help                     ║
║                                                      ║
╠══════════════════════════════════════════════════════╣
║  Time Left: 45:23  │  Calls: 1247  │  New Msgs: 12   ║
╚══════════════════════════════════════════════════════╝

 Your command? _
```

**Message Thread Display:**
```
╔═══════════════════════════════════════════════════════╗
║ Msg#: 142  From: SHADOWMAGE        Date: 01-15-1994   ║
║            To: ALL                 Time: 14:32        ║
║       Subj: Re: The new DOOM level                    ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║ Has anyone else found the secret room in E2M4?        ║
║ I spent three hours looking for it last night.        ║
║                                                       ║
║ The hint says "push the demon's nose" but I can't     ║
║ find any demon statue anywhere!                       ║
║                                                       ║
╠═══════════════════════════════════════════════════════╣
║ [R]eply  [N]ext  [P]rev  [A]gain  [Q]uit              ║
╚═══════════════════════════════════════════════════════╝
```

---

## Social Dynamics

### User Interaction Patterns

**Message Threading:**
- Linear chronological ordering (not hierarchical like modern forums)
- "Re:" prefix for replies
- Quote original message with `>` prefix lines
- Personal signature ("tagline") at message end

**Community Building:**
- Regular users developed reputations
- SysOp could grant privileges to trusted members
- "Caller logs" showed who visited
- "Who's Online" for real-time presence

### FidoNet & Echomail

**The First Social Network:**
- 39,000 systems at peak
- 4 million total users, 2 million using echomail
- Store-and-forward messaging across dial-up connections
- Messages bundled, compressed (ARC/ZIP), and forwarded

**Echomail Forums:**
- Public discussions similar to Usenet newsgroups
- Sysops joined "echoes" (distributed forums)
- Messages propagated across the network
- Network validation for moderated echoes

### Access Control Philosophy

**Security Levels (SL):**
- Numeric values (0-255 typical)
- Higher = more access
- Different SL for reading vs posting

**Access Restrictions (AR):**
- Letter flags (A-P) for fine-grained control
- Combine with SL for complex permissions
- Example: SL 50 + AR B = Validated user in Beta testers group

**Post/Call Ratios:**
- Encouraged active participation
- Must post X messages per Y logins to maintain access
- Prevented "leeches" who only downloaded

---

## MUD Integration Recommendations

### Bulletin Board Object Architecture

**Board Entity:**
```
BulletinBoard {
    id: string
    name: string              // "The Fishery Notice Board"
    location: Room            // Where it's located in the MUD
    description: string       // How it looks
    accessLevel: number       // Who can read
    postLevel: number         // Who can post
    maxMessages: number       // Before auto-archive
    messages: Message[]
    moderator: Character      // NPC or player moderator
}
```

**Message Entity:**
```
Message {
    id: number                // Sequential per board
    author: Character         // Who posted (or NPC)
    subject: string
    body: string
    timestamp: DateTime
    replyTo: number?          // Parent message ID
    isAnonymous: boolean
    isPinned: boolean         // Sticky at top
}
```

### Command Structure for MUD

**Primary Commands:**
```
BOARD                    - List available boards in current room
BOARD <name>             - Select/view a specific board
POST <subject>           - Start composing a new message
READ                     - Read messages on current board
READ <number>            - Read specific message
READ NEW                 - Read unread messages
REPLY <number>           - Reply to a message
REMOVE <number>          - Remove your own message (or mod powers)
```

**Navigation Commands:**
```
NEXT                     - Next message
PREV                     - Previous message
FIRST                    - Jump to first message
LAST                     - Jump to last message
LIST                     - List message subjects
LIST NEW                 - List only unread messages
QUIT                     - Exit board view
```

### Visual Formatting (MUD-Adapted)

**Board Header:**
```
.=========================================================.
|              THE FISHERY NOTICE BOARD                   |
|=========================================================|
| 12 messages (3 new)           Last post: 2 days ago     |
'---------------------------------------------------------'

 #  Subject                          Author         Date
--- -------------------------------- -------------- --------
 12 [NEW] Equipment for sale         Simmon         Today
 11 [NEW] Lost: Brown leather pouch  Fela           Today
 10 [NEW] Eolian performance tonight Threpe         Yester.
  9 Seeking tutor for Artificing     Wil            3 days
  8 Re: Admissions deadline          Hemme          4 days
  ...

Type READ <#> to read, POST to write, or QUIT to leave.
```

**Message Display:**
```
.=========================================================.
| Message #12 of 12                                       |
|=========================================================|
| From: Simmon                                            |
| Date: Cendling, 14th of Equis                           |
| Subj: Equipment for sale                                |
'---------------------------------------------------------'

I have the following items available for sale, all in
excellent condition:

  - Sympathy lamp (barely used)     - 3 talents
  - Set of binding cables           - 1 talent, 2 jots
  - Mommet-grade wax (2 blocks)     - 4 jots each

Find me at the Artificing workshop most afternoons.

                                        - Simmon
.=========================================================.
[R]eply  [N]ext  [P]rev  [L]ist  [Q]uit
```

### NPC Posting System

**Scheduled Posts:**
```
NPCPost {
    npc: Character           // Elodin, Ambrose, etc.
    board: BulletinBoard
    schedule: Cron           // When to post
    messageTemplate: string  // With variable substitution
    personality: string      // Writing style
    responseRules: Rule[]    // How to respond to replies
}
```

**Example NPC Behaviors:**
- Elodin: Random, cryptic posts at odd hours
- Ambrose: Haughty announcements, complaints about commoners
- Kilvin: Workshop schedules, safety reminders
- Lorren: Library policy updates, strictly formal
- Simmon: Friendly sale posts, event announcements

---

## Kingkiller Chronicle Adaptation

### Thematic Boards

**University Boards:**
| Board | Location | Theme | Access |
|-------|----------|-------|--------|
| Admissions | Hollows | Enrollment, tuition | Public |
| The Horns | Archives | Academic discipline | Students |
| Artificer's Guild | Fishery | Commissions, sales | Artificers |
| Archives Index | Stacks | Research requests | Re'lar+ |
| The Underthing | Secret | Underground secrets | Discovery |

**Imre Boards:**
| Board | Location | Theme | Access |
|-------|----------|-------|--------|
| Eolian Stage | Eolian | Performances, auditions | Patrons |
| Talent Exchange | Merchant sq. | Buy/sell/trade | Public |
| Courier Post | Main gate | Delivery notices | Public |

### Example Elodin Posts

**Cryptic Wisdom:**
```
From: Master Elodin
Subj: Wind

The name of the wind is not a name.
Think on this. Or don't.
I certainly won't.

(This message brought to you by the Department of Naming,
which does not exist, officially.)
```

**Class Announcement:**
```
From: Master Elodin
Subj: Naming - Class Cancelled

Today's Naming session is cancelled because I have
misplaced my shoes. Also because naming is not something
you can schedule on a Felling afternoon.

Those seeking enlightenment may find me on the roof
of the Mews. Or perhaps I will find you.

No, probably the roof thing.
```

### Example Ambrose Posts

**Complaint:**
```
From: Ambrose Jakis
Subj: Commoner Infestation

It has come to my attention that certain scholarship
students have been using the Artificery as their personal
workshop, leaving their crude projects scattered about
like refuse.

Those of proper breeding should not have to navigate
around the detritus of the lower classes.

This is beneath the standards of the Arcanum.

                        - Ambrose Jakis
                          House Jakis, Vintas
```

**Boast:**
```
From: Ambrose Jakis
Subj: Eolian Performance - Three Nights Hence

I shall be performing at the Eolian this Hepten eve.
Those of refined taste are welcome to attend.

Naturally, the talent pipes shall be mine by evening's end.

                        - Ambrose Jakis
                          Patron of the Arts
```

### Access Level Mapping

**MUD Rank to BBS Access:**
```
E'lir      = Level 1 (Basic boards, read most, post some)
Re'lar     = Level 2 (Research boards, more posting)
El'the    = Level 3 (Advanced boards, mentoring)
Arcanist   = Level 4 (Professional boards)
Master     = Level 5 (Administrative access)
```

**Special Access:**
- Tehlin Church boards (faith-based)
- Noble house boards (aristocracy)
- Edema Ruh boards (troupe members)
- Cealdish merchant boards (trade guilds)

### Kingkiller ANSI Adaptation

For a fantasy setting, adapt ANSI aesthetic to manuscript/medieval feel:

```
.~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~.
|                 THE ARCHIVES                       |
|     "The four-plate door remains sealed"           |
|~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~|
|                                                    |
|  Tomes Available: 847,329 (approx)                 |
|  Scrivs on Duty: 4                                 |
|  Current Acquisitions: See Notice Board            |
|                                                    |
|  [R]ead Notices   [S]earch Catalog   [L]eave       |
|                                                    |
'~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
```

### Implementation Priorities

**Phase 1: Core System**
1. Board object with messages
2. Basic READ/POST/REPLY commands
3. Message persistence
4. Per-character read tracking

**Phase 2: Access Control**
1. Access levels per board
2. Moderator/admin commands
3. Anonymous posting option
4. Message pinning

**Phase 3: NPC Integration**
1. Scheduled NPC posts
2. Character-appropriate writing styles
3. NPC responses to player posts
4. Event-triggered announcements

**Phase 4: Advanced Features**
1. Cross-location board access (sympathetic link?)
2. Private messaging
3. Board subscriptions/notifications
4. Archive system for old messages

---

## References & Sources

### Primary Sources
- [Wikipedia - Bulletin Board System](https://en.wikipedia.org/wiki/Bulletin_board_system)
- [WWIV BBS Documentation](https://docs.wwivbbs.org/)
- [Renegade BBS Official Site](https://www.rgbbs.info/)
- [textfiles.com BBS List](http://bbslist.textfiles.com/)
- [16colo.rs ANSI Art Archive](https://16colo.rs/)

### Historical Archives
- [BBS Documentary](http://www.bbsdocumentary.com/)
- [artscene.textfiles.com](http://artscene.textfiles.com/ansi/)
- [Break Into Chat Wiki](https://breakintochat.com/wiki/)

### Technical Documentation
- [FidoNet Wikipedia](https://en.wikipedia.org/wiki/FidoNet)
- [ANSI Escape Codes Reference](https://gist.github.com/fnky/458719343aabd01cfb17a3a4f7296797)
- [Telnet BBS Guide](https://www.telnetbbsguide.com/)

---

*Report compiled for Waystone MUD development*
