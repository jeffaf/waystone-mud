# Product Requirements Document: Waystone MUD
## A Multi-User Dungeon set in Patrick Rothfuss's Kingkiller Chronicle Universe

**Version:** 1.0
**Date:** 2025-12-06
**Status:** Draft - Ready for Implementation
**Project Codename:** Waystone

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Kingkiller Chronicle World Systems](#kingkiller-chronicle-world-systems)
4. [Core MUD Systems](#core-mud-systems)
5. [Technical Stack & Infrastructure](#technical-stack--infrastructure)
6. [CI/CD Pipeline](#cicd-pipeline)
7. [Implementation Phases](#implementation-phases)
8. [Risk Assessment & Mitigation](#risk-assessment--mitigation)
9. [Appendices](#appendices)

---

## Executive Summary

### Project Overview

Waystone MUD is a text-based Multi-User Dungeon game set in Patrick Rothfuss's richly detailed Kingkiller Chronicle universe. The project aims to create an immersive, multiplayer role-playing experience that faithfully captures the magic systems, geography, factions, and economy of Temerant while providing a robust, scalable foundation for continuous expansion.

### Success Metrics

**Player Engagement:**
- 50+ concurrent users within 3 months of launch
- Average session duration: 45+ minutes
- Player retention rate: 60% after 30 days
- Daily active users (DAU) growth of 15% month-over-month

**Technical Performance:**
- Server uptime: 99.5%+
- Average command response time: <100ms
- Support for 100+ concurrent connections
- Zero data loss during server crashes/restarts

**Development Velocity:**
- Complete MVP (Phase 1) within 2 weeks
- Release new major feature phase every 2-3 weeks
- Test coverage maintained at 80%+
- All CI/CD pipelines passing before deployment

### Technical Stack

**Language & Runtime:**
- Python 3.12+ (primary language)
- asyncio for asynchronous networking
- Type hints throughout (enforced via mypy)

**Core Libraries:**
- `telnetlib3` - Asyncio-based Telnet protocol implementation
- `websockets` - WebSocket support for browser-based clients
- `SQLAlchemy` - ORM and database management (supports SQLite and PostgreSQL)
- `aiosqlite` - Async SQLite driver (for budget/dev mode)
- `Pydantic` - Data validation and serialization

**Testing & Quality:**
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-cov` - Coverage reporting
- `ruff` - Fast Python linter and formatter
- `mypy` - Static type checking

**Infrastructure (Budget Mode - $0/month):**
- SQLite - Primary data persistence (zero config, file-based)
- In-memory dict - Session/cache layer (no Redis needed for <50 users)
- Oracle Cloud Free Tier - Hosting (ARM VM, forever free)
- GitHub Actions - CI/CD
- Docker - Containerization (optional for local dev)

**Infrastructure (Scale Mode - when needed):**
- PostgreSQL - Primary data persistence (via Neon free tier or managed)
- Redis/Upstash - Session/cache layer
- Oracle Cloud or DigitalOcean - Hosting
- Nginx - Reverse proxy (for WebSocket)

### Timeline Estimate

**Total Development Time:** 10-14 weeks for full feature set

| Phase | Duration | Deliverables |
|-------|----------|-------------|
| Phase 1: Core Infrastructure | 2 weeks | Playable MVP with basic room navigation |
| Phase 2: Character System | 2 weeks | Character creation, inventory, attributes |
| Phase 3: Combat & NPCs | 2 weeks | Combat mechanics, basic NPCs |
| Phase 4: Magic - Sympathy | 2 weeks | Sympathy system implementation |
| Phase 5: University System | 2 weeks | University, Arcanum, tuition mechanics |
| Phase 6: Economy & Crafting | 1-2 weeks | Currency, shops, basic crafting |
| Phase 7: Advanced Features | 1-2 weeks | Naming, factions, quests |

### Resource Requirements

**Team Composition:**
- 1 Senior Backend Engineer (Python expertise, game systems knowledge)
- 1 DevOps Engineer (part-time, CI/CD and infrastructure)
- 1 QA Engineer (part-time, test automation)
- 1 Content Designer (part-time, world building and narrative)

**Infrastructure Costs (Monthly) - Budget Optimized:**
- VPS Hosting: **Oracle Cloud Free Tier** - $0/month (2 AMD VMs, 1GB RAM each, forever free)
- Database: **SQLite** (dev/small scale) or **Neon Free Tier** (prod) - $0/month
- Cache/Sessions: **In-memory** (dev) or **Upstash Free Tier** (10K commands/day) - $0/month
- Domain: Optional ($12/year) or use Oracle's free public IP
- **Total Estimated:** $0-10/month for initial launch

**Scaling Path (when needed):**
- 50+ concurrent users: Stay on Oracle Free Tier (handles it fine)
- 100+ concurrent users: Consider paid VPS ($20-40/month)
- 500+ concurrent users: Separate database, load balancing ($100+/month)

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Telnet Client│  │ Web Client   │  │  Mobile App  │     │
│  │  (MUSHclient)│  │ (WebSocket)  │  │  (Future)    │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
└─────────┼──────────────────┼──────────────────┼─────────────┘
          │                  │                  │
          │                  ▼                  │
          │         ┌────────────────┐          │
          │         │     Nginx      │          │
          │         │ (Reverse Proxy)│          │
          │         └────────┬───────┘          │
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   NETWORK LAYER                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │          Async Connection Manager                    │   │
│  │  - Telnet Protocol Handler (telnetlib3)              │   │
│  │  - WebSocket Handler (websockets)                    │   │
│  │  - Session Management (Redis)                        │   │
│  │  - Connection Pool Management                        │   │
│  └──────────────────┬───────────────────────────────────┘   │
└─────────────────────┼───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   GAME ENGINE CORE                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Command Parser & Router                  │  │
│  │  - Input Validation & Sanitization                    │  │
│  │  - Command Tokenization                               │  │
│  │  - Permission/Auth Checking                           │  │
│  └───────────────────┬───────────────────────────────────┘  │
│                      ▼                                       │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Game Systems Manager                     │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │ World Mgr   │  │ Character   │  │  Combat     │   │  │
│  │  │ - Rooms     │  │  System     │  │  System     │   │  │
│  │  │ - Areas     │  │ - Attributes│  │ - Actions   │   │  │
│  │  │ - Exits     │  │ - Inventory │  │ - Damage    │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │ Magic Mgr   │  │  NPC/AI     │  │   Quest     │   │  │
│  │  │ - Sympathy  │  │  System     │  │   System    │   │  │
│  │  │ - Naming    │  │ - Behaviors │  │ - Tracking  │   │  │
│  │  │ - Sygaldry  │  │ - Dialogue  │  │ - Rewards   │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │  │
│  │  │ Economy Mgr │  │ University  │  │  Faction    │   │  │
│  │  │ - Currency  │  │   System    │  │   System    │   │  │
│  │  │ - Trading   │  │ - Admission │  │ - Reputation│   │  │
│  │  │ - Crafting  │  │ - Classes   │  │ - Relations │   │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │  │
│  └───────────────────┬───────────────────────────────────┘  │
└─────────────────────┼────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   PERSISTENCE LAYER                          │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │   PostgreSQL     │  │      Redis       │                 │
│  │  - Player Data   │  │  - Sessions      │                 │
│  │  - World State   │  │  - Active Users  │                 │
│  │  - Game Events   │  │  - Chat Channels │                 │
│  │  - Audit Logs    │  │  - Rate Limiting │                 │
│  └──────────────────┘  └──────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Diagrams

#### Player Command Flow

```
Player Input → Network Layer → Auth Check → Parse Command →
  ↓
Validate Permissions → Execute Game Logic → Update State →
  ↓
Persist Changes (if needed) → Generate Response → Send to Client(s)
  ↓
Log Event (audit trail)
```

#### Combat Round Flow

```
Combat Initiated → Initiative Roll → Turn Order Queue →
  ↓
Player/NPC Action Input → Validate Action → Calculate Effects →
  ↓
Apply Damage/Buffs/Debuffs → Update Combat State → Check Win Conditions →
  ↓
Broadcast Updates to Participants → Continue/End Combat → Distribute Rewards
```

#### Magic (Sympathy) Flow

```
Player Casts Sympathy → Select Source & Target → Define Binding →
  ↓
Calculate Efficiency (based on similarity) → Check Alar Strength →
  ↓
Consume Energy (from heat source) → Apply Effect to Target →
  ↓
Risk Check (for sympathetic backlash) → Update Player State → Notify Result
```

### Technology Decisions

#### Why Python?

**Strengths:**
- Rapid development and prototyping
- Excellent async support (asyncio)
- Rich ecosystem for game logic and networking
- Easy to read/maintain for content additions
- Strong testing frameworks

**Note:** While TypeScript is generally preferred in PAI infrastructure, Python is the **approved choice** for this MUD project due to:
1. Traditional MUD development heritage in Python
2. Excellent async networking support (telnetlib3, asyncio)
3. Rich game development libraries
4. User specifically requested Python
5. Better suited for this specific use case

**Mitigation for Python Weaknesses:**
- Strict type hints enforced via mypy
- Comprehensive test coverage (80%+)
- Linting via ruff for code quality
- Use uv for dependency management (NOT pip)

#### Why PostgreSQL?

- Relational data model fits MUD structure (rooms, items, characters)
- ACID compliance for critical game state
- JSON/JSONB support for flexible attributes
- Excellent Python support (psycopg3, SQLAlchemy)
- Battle-tested for game persistence

#### Why Redis?

- Lightning-fast session management
- Pub/sub for real-time chat channels
- Simple caching layer
- Connection state tracking
- Rate limiting support

#### Why Telnet + WebSocket?

- **Telnet:** Traditional MUD protocol, supported by all MUD clients
- **WebSocket:** Modern browser-based access, mobile-friendly future
- Both protocols share same game engine backend
- Allows gradual migration to web-first experience

### Infrastructure Requirements

#### Hosting Recommendations

**Primary Option: Oracle Cloud Free Tier (RECOMMENDED - $0/month forever)**

**Oracle Cloud Infrastructure (OCI) Always Free:**
- **Compute:** 2 AMD VMs with 1GB RAM each (or 1 Ampere ARM VM with up to 4 OCPUs, 24GB RAM)
- **Storage:** 200GB block storage
- **Bandwidth:** 10TB/month outbound
- **Cost:** $0/month - genuinely forever free, not a trial
- **Reasoning:**
  - More than enough power for a MUD (text is lightweight)
  - Full root access, run whatever you want
  - ARM option is incredibly powerful for free
  - No credit card charges ever (truly free tier, not "free trial")

**Setup for Waystone MUD on Oracle Free Tier:**
```
Option A (Simple): 1 AMD VM (1 OCPU, 1GB RAM)
- SQLite for database (file-based, zero config)
- In-memory session storage (no Redis needed for <50 users)
- Python asyncio server
- Systemd for process management

Option B (Recommended): 1 ARM VM (2 OCPU, 12GB RAM)
- Same as above but with headroom for growth
- Can add PostgreSQL later if needed
- Room for Redis if session management becomes complex
```

**Alternative Free Options:**

| Provider | Free Tier | Limitations |
|----------|-----------|-------------|
| **Fly.io** | 3 shared VMs (256MB each) | Low memory, but works |
| **Render** | Web service | Sleeps after 15min inactivity (bad for MUD) |
| **Railway** | $5/month credit | Burns through on always-on service |
| **Home Raspberry Pi** | $0 | Needs Tailscale/Cloudflare Tunnel for access |

**Production Scaling Path:**
1. **Phase 1-5:** Oracle Free Tier ARM VM (handles 50-100 concurrent easily)
2. **Phase 6+:** If exceeding free tier, upgrade to paid Oracle ($20/month) or migrate to DigitalOcean
3. **500+ users:** Separate database to managed PostgreSQL, consider load balancing

#### Network Requirements

- **Bandwidth:** 1TB/month minimum (avg 100KB per user per hour)
- **Latency:** <50ms for optimal player experience
- **DDoS Protection:** Cloudflare free tier initially, paid if needed
- **SSL/TLS:** Let's Encrypt for WebSocket connections

#### Security Architecture

**Authentication:**
- Password hashing: bcrypt (12 rounds minimum)
- Session tokens: UUID4, stored in Redis with TTL
- Failed login rate limiting: 5 attempts per 15 minutes
- Account lockout after 10 failed attempts in 1 hour

**Authorization:**
- Role-based access control (RBAC)
- Roles: Player, Helper, Builder, Admin, Owner
- Permission checks before every sensitive command
- Audit logging for privileged actions

**Data Protection:**
- Input sanitization for all player commands
- SQL injection prevention via ORM (SQLAlchemy)
- XSS protection for web client
- No storage of sensitive data (credit cards, etc.)
- GDPR compliance: data export and account deletion features

**Network Security:**
- Rate limiting on all endpoints (Redis-backed)
- Connection limits per IP (max 5 simultaneous)
- Automatic ban for command flooding
- Regular security audits via GitHub's Dependabot

### Integration Points

#### External APIs (Future Consideration)

- **Discord Bot:** For community notifications and server status
- **Twitch Integration:** Stream integration for viewer participation
- **Analytics:** Google Analytics or self-hosted Plausible
- **Payment Processing:** Stripe for optional donations/cosmetics (Phase 8+)

#### Internal Service Communication

- **Game Engine ↔ Database:** SQLAlchemy ORM
- **Game Engine ↔ Redis:** redis-py async client
- **Network Layer ↔ Game Engine:** Direct Python function calls (monolith initially)
- **Admin Tools ↔ Game Engine:** REST API (FastAPI) for out-of-game management

---

## Kingkiller Chronicle World Systems

### The Four Corners Geography

#### Major Regions

**The Commonwealth**
- Capital: Tarbean (major port city)
- University location: Imre region, across the Omethi River
- Characterized by: Merchant culture, relative stability, diverse population
- Key Cities: Tarbean, Imre, Newarre, Hallowfell

**Vintas**
- Capital: Cershaen
- Characterized by: Noble court politics, intrigue, formal social hierarchy
- Key Locations: Severen (The Maer's estate), countryside estates
- Economy: Aristocratic wealth, taxes on trade routes

**Ceald**
- Capital: Ralien
- Characterized by: Financial center, birthplace of standardized currency
- Economic Power: Banking, lending, merchant guilds
- Notable: Cealdish mercenaries, shrewd traders

**Modeg**
- Capital: Renere
- Less detail in books, room for creative expansion
- Military culture, historical conflicts with neighbors

**Other Significant Regions:**
- **Yll:** Island nation, distinct culture
- **Ademre:** Home of the Adem mercenaries, isolated mountain culture
- **The Small Kingdoms:** Collection of smaller states
- **Atur:** Historical empire, now fragmented

#### World Design for MUD

**Initial Launch (Phase 1-3):**
- The University and Imre (20-30 rooms)
- Small slice of Commonwealth countryside (10-15 rooms)
- Single dungeon/adventure area (15-20 rooms)

**Expansion Priority:**
- Tarbean (major city content)
- Vintas courts (political intrigue quests)
- Wilderness areas (Eld, Fae realm borders)
- Ancient ruins (Naming practice, Chandrian lore)

### Magic Systems

#### 1. Sympathy (Priority: Phase 4)

**Core Mechanics:**

Sympathy is energy manipulation through creating connections (bindings) between objects.

**Three Primary Laws:**
1. **Law of Conservation:** Energy cannot be created or destroyed
2. **Law of Correspondence:** Similarity determines binding strength
3. **Law of Consanguinity:** Objects once connected maintain stronger links

**System Implementation:**

```
Binding Strength = (Similarity Score × Consanguinity Modifier) / Distance Factor

Energy Transfer Efficiency = Binding Strength × Alar Modifier

Actual Effect = (Source Energy × Efficiency) - Slippage
```

**Similarity Scores:**
- Identical objects: 100%
- Same material, different shape: 70-80%
- Similar material: 50-60%
- Same category (metal to metal): 30-40%
- Dissimilar: <10%

**Consanguinity Modifiers:**
- Same object (split): +50%
- Blood relation: +30%
- Recent contact: +10-20%
- No connection: 0%

**Alar (Mental Strength):**
- Trainable attribute (improves with practice)
- Determines maximum energy transfer
- Required for multiple simultaneous bindings
- Affects resistance to sympathetic backlash

**Heat Sources:**
- Candle: 50 energy units/turn
- Torch: 150 energy units/turn
- Brazier: 500 energy units/turn
- Own body heat: 100 energy units/turn (DANGEROUS)

**Bindings Available:**

| Binding Name | Description | Energy Cost | Effects |
|--------------|-------------|-------------|---------|
| Heat Transfer | Move thermal energy | 10/turn | Warm/freeze objects |
| Kinetic Transfer | Move momentum | 20/turn | Push/lift objects |
| Damage Transfer | Inflict harm sympathetically | 30/turn | Deal damage at range |
| Dowsing | Sense linked object direction | 5/turn | Find items/people |
| Light Binding | Transfer illumination | 10/turn | Create light sources |

**Sympathetic Backlash:**
If energy transfer exceeds safe limits or binding breaks unexpectedly:
- Minor: Headache, fatigue (-10% max energy for 1 hour)
- Moderate: Unconsciousness, temporary Alar damage
- Severe: Brain damage, permanent attribute loss
- Critical: Death

**Progression System:**
- **E'lir (Novice):** Single simple bindings, 50% efficiency cap
- **Re'lar (Intermediate):** Multiple bindings, 70% efficiency cap
- **El'the (Advanced):** Complex bindings, 85% efficiency cap
- **Master:** Theoretical 95% efficiency, multiple complex bindings

#### 2. Naming (Priority: Phase 7)

**Core Concept:**
Knowing the true name of a thing grants control over it.

**Known Names in Canon:**
- The Wind (Kvothe's primary name)
- Fire
- Stone
- Water
- Iron
- Wood
- (Others exist but are secret/unknown)

**System Implementation:**

**Learning a Name:**
- Requires deep meditation and understanding
- Triggered by moment of clarity/crisis (cannot be forced)
- Once learned, can be "Spoken" or "Called"

**Calling vs Speaking:**
- **Calling:** Instinctive, emotional, unreliable (happens in crisis)
- **Speaking:** Deliberate, controlled, requires training and focus

**Name Effects:**

| Name | Effect When Spoken | Energy Cost | Cooldown |
|------|-------------------|-------------|----------|
| Wind | Control air currents, create gusts | 50 | 5 minutes |
| Fire | Summon/control flames | 75 | 10 minutes |
| Stone | Shape/break rock | 100 | 15 minutes |
| Water | Control liquids | 60 | 8 minutes |
| Iron | Manipulate metal | 80 | 12 minutes |

**Sleeping Mind:**
The "sleeping mind" knows Names but cannot always access them. Stress, anger, or fear can trigger spontaneous Calling.

**Risk:**
- Naming is mentally dangerous
- Risk of losing oneself in the Name
- Can cause temporary or permanent madness
- University has "Haven" for those driven insane by magic

**Game Mechanic:**
- Names are rare, quest-locked achievements
- Players must complete difficult trials
- Once learned, mastery improves with use
- Failure chance on Speaking (decreases with practice)

#### 3. Sygaldry (Priority: Phase 6)

**Core Concept:**
Rune-based artificial sympathy inscribed on objects.

**Characteristics:**
- Permanent magical effects without active concentration
- Requires crafting skill + sygaldry knowledge
- Uses materials with sympathetic properties
- Draws energy from ambient sources or stored reserves

**Example Sygaldric Devices:**

| Item | Runes | Effect | Materials |
|------|-------|--------|-----------|
| Sympathy Lamp | Heat → Light binding | Ever-burning light | Glass, iron frame |
| Gram | Repulsion ward | Deflects arrows/harm | Silver, rare woods |
| Heat Funnel | Heat attraction | Draws warmth to wearer | Copper, cloth |
| Dowsing Compass | Direction finding | Points to target | Iron, glass, blood |

**Crafting Mechanics:**
- Requires "Artificery" skill
- Must know underlying sympathetic principles
- Materials determine efficiency
- Failure wastes materials
- Masterwork items have enhanced effects

#### 4. Alchemy (Priority: Phase 6)

**Core Concept:**
Magical chemistry creating potions, poisons, and transmutations.

**Example Formulas:**

| Potion | Effect | Ingredients | Difficulty |
|--------|--------|-------------|------------|
| Healing Salve | Restore 50 HP over time | Willow bark, honey, ramston steel | Medium |
| Nahlrout | Extreme rage, strength +5 | Rare herbs, mercury | Hard |
| Regim | Sleeplessness, focus +2 | Coffee, denner resin | Easy |
| Plum Bob | Poison, 30 damage | Nightshade, sulfur | Medium |

**Alchemy Skill Progression:**
- Apprentice: Basic healing potions
- Journeyman: Buffs, antidotes
- Expert: Transmutation, exotic effects
- Master: Custom formula creation

### The University

#### Campus Structure

**Buildings (All Visitable Rooms):**

1. **The Mews** - Student housing, shared rooms, common areas
2. **The Hollows** - Administration, Admissions exams held here
3. **Mains** - Lecture halls, classrooms for basic courses
4. **The Archives** - Vast library, restricted sections, dangerous knowledge
5. **The Artificery** - Workshop, forge, sygaldry crafting
6. **The Medica** - Hospital, healing, alchemy supplies
7. **Haven** - Asylum for magically damaged minds (restricted)
8. **The Rookery** - Masters' offices and private quarters
9. **Anker's Tavern** - Off-campus, student gathering place (in Imre)

#### The Arcanum

**Membership Ranks:**

| Rank | Title | Requirements | Privileges |
|------|-------|--------------|------------|
| 0 | Non-member | - | Can attend University, not Arcanum |
| 1 | E'lir ("Seer") | Pass initial admission | Basic sympathy training, Archives access level 1 |
| 2 | Re'lar ("Speaker") | Master sponsorship | Advanced training, Archives level 2, can teach |
| 3 | El'the ("Guild member") | Complete thesis, earn gilthe | Full access, independent research, can sponsor |
| 4 | Master | Lifetime achievement | Teach, set policy, judge admissions |

**Advancement Mechanics:**
- E'lir → Re'lar: Demonstrate proficiency, receive Master's sponsorship
- Re'lar → El'the: Complete 6+ terms, defend thesis, craft masterwork (artificery or other)
- El'the → Master: Exceptional lifetime contribution (NPC-only initially)

#### Admission & Tuition System

**Admission Process:**
1. Applicant requests admission in the Hollows
2. Masters assemble (9 total, quorum of 5+ required)
3. Each Master asks questions (academic, practical, ethical)
4. Masters vote on acceptance and tuition amount

**Tuition Calculation:**

```
Base Tuition = Rank × 10 talents
Modifiers:
  - Excellent performance: -50% to -100%
  - Poor performance: +50% to +200%
  - Insolence/disrespect: +100%+
  - Exceptional answer: -20%
  - Master's favor/disfavor: ±30%

Minimum Tuition: 0 talents (free admission)
Maximum Tuition: Unlimited (effectively a rejection)
Negative Tuition: Possible (University pays student)
```

**In-Game Tuition Timing:**
- Held every 2 real-world weeks (game time: end of term)
- Player attends admission room, answers questions
- Questions generated from pool based on player's skills/history
- Tuition affects player's economic state
- Can work as "scriv" (scribe) to earn money if broke

#### The Nine Masters

| Master | Discipline | Personality Traits | Question Style |
|--------|-----------|-------------------|----------------|
| Hemme | Geometry | Pompous, dislikes cleverness | Trap questions, nitpicky |
| Arwyl | Medica | Practical, kind | Medical ethics, healing scenarios |
| Mandrag | Alchemy | Gruff, direct | Practical application tests |
| Kilvin | Artificery | Fair, values craftsmanship | Hands-on demonstrations |
| Elxa Dal | Sympathy | Encouraging, theoretical | Sympathetic bindings, law questions |
| Brandeur | Rhetoric | Formal, traditional | Debate, argumentation |
| Lorren | Archives | Strict, humorless | Library rules, research methods |
| Elodin | Naming | Eccentric, unpredictable | Nonsensical riddles, Zen koans |
| Herma | History | Detail-oriented | Historical events, dates |

**Master Interaction:**
- Each Master has reputation tracker with player
- Positive reputation: Better tuition, access to resources
- Negative reputation: Higher tuition, denied privileges
- Special quests available for favored students

#### University Activities

**Classes (Repeatable for Skill Gain):**
- Sympathy lectures (Elxa Dal)
- Artificery workshop (Kilvin)
- Alchemy lab (Mandrag)
- Medica training (Arwyl)
- Archives research (Lorren)
- Rhetoric debate (Brandeur)

**Jobs for Income:**
- Scriv (copying texts): 2-5 jots per hour
- Medica assistant: 1 talent per shift
- Artificery work: 3-10 talents per project
- Tutoring younger students: 5 jots per session

**Social Areas:**
- The Mess (cafeteria): Social hub, rumors, quests
- Anker's Tavern: Off-campus, gambling, music
- Eolian (music venue): Perform for tips, reputation

### Factions

#### The Chandrian

**Overview:**
- Primary antagonists, group of seven
- Seek to erase knowledge of themselves
- Leave signs: blue flame, rust, decay, madness
- Kill witnesses who learn too much

**In-Game Role:**
- High-level endgame content
- Mystery/investigation questlines
- Dangerous encounters (likely fatal)
- Lore scattered throughout world

**Known Members:**
- Cinder (white hair, cruel)
- Haliax (leader, shadowed)
- Five others (less defined, creative freedom)

**Interaction:**
- Players can research lore
- Finding too much attracts attention (random dangerous events)
- Completing Chandrian knowledge quests unlocks special abilities
- Ultimate confrontation is endgame goal

#### The Amyr

**Overview:**
- Ancient organization, supposedly disbanded 300 years ago
- "For the greater good" - willing to commit atrocities
- May still exist in secret
- Opposition to the Chandrian

**In-Game Role:**
- Hidden faction, not openly joinable
- Players can uncover evidence of activity
- Moral ambiguity: are they heroes or villains?
- Recruitment possible at high levels (secret questline)

**Reputation System:**
- Actions aligned with "greater good" increase Amyr favor
- Ruthless efficiency valued over mercy
- Unlocks access to hidden caches, ancient knowledge

#### Edema Ruh

**Overview:**
- Traveling performers, Kvothe's people
- Suffer prejudice and discrimination
- Rich oral tradition, music, storytelling
- Strong internal culture and ethics

**In-Game Role:**
- Joinable faction (if player chooses Ruh background)
- Traveling performance mechanics
- Special music/storytelling skills
- Persecution events (NPC hostility in some areas)

**Benefits:**
- Bonus to performance skills
- Access to Ruh-only questlines
- Network of Ruh contacts across world
- Special movement/travel abilities

#### Other Factions

**University Factions:**
- Arcanum membership (primary)
- Individual Master patronage
- Student societies (drinking clubs, study groups)

**Religious/Cultural:**
- Tehlin Church (dominant religion)
- Aturan traditionalists
- Regional cultural groups

**Future Expansion:**
- The Sithe (Fae defenders)
- The Singers (mysterious group)
- Mercenary companies (Adem, Cealdish)

### Economy

#### Currency System

**Cealdish Standard (Four Corners-wide):**

| Coin | Value | Material | Description |
|------|-------|----------|-------------|
| Shim | 0.08 drabs | Cheap iron | Unofficial, based on weight |
| Drab | 1 drab | Iron/steel | Lowest official denomination |
| Jot | 10 drabs | Copper | Common trade coin |
| Talent | 10 jots (100 drabs) | Silver | Significant wealth |
| Mark | 10 talents (1000 drabs) | Gold | Rare, major transactions |

**Conversion:**
- 1 talent = 10 jots = 100 drabs (≈1200 shims)
- 1 mark = 10 talents = 100 jots = 1000 drabs

**Price References (from books):**
- Loaf of bread: 1-2 shims
- Mug of ale: 5-8 shims (≈1 drab)
- Hot meal: 2-3 drabs
- Night's lodging: 5-8 drabs
- University tuition: 0-20+ talents per term
- Fine lute: 7-10 talents
- Wealthy person's monthly income: 50-100 talents

**In-Game Economy Design:**

**Starting Wealth (by Background):**
- Poor (street urchin, orphan): 5-10 drabs
- Common (farmer, laborer): 2-5 jots
- Educated (scribe, merchant): 3-8 talents
- Wealthy (minor noble): 20-50 talents

**Income Sources:**
- Quests: 1 jot - 10 talents depending on difficulty
- Jobs: 5 drabs - 3 talents per game day
- Crafting/selling: Variable based on skill
- Performance: 1 drab - 5 talents (based on skill/venue)
- Loot: 1-100 drabs from NPCs/chests

**Major Expenses:**
- University tuition: 1-15 talents per term (every 2 weeks)
- Magical training: 1-5 talents per lesson
- Equipment upgrades: 5 jots - 20 talents
- Property/housing: 10-100 talents (one-time or monthly)
- Bribes/information: 1 jot - 5 talents

**Money Sinks (Prevent Inflation):**
- Tuition payments
- Gambling losses
- Fines for rule violations
- Crafting material costs
- Magical component costs
- Property taxes

#### Merchants & Trading

**Merchant Types:**

1. **General Stores:** Basic supplies, food, simple tools
2. **Artificers:** Sygaldric items, enchanted equipment
3. **Apothecaries:** Alchemy ingredients, potions
4. **Weapon Smiths:** Combat equipment
5. **Booksellers:** Skill books, lore, maps
6. **Fences:** Black market, stolen goods (hidden)

**Trading Mechanics:**
- Base prices adjusted by:
  - Player's Mercantile skill: 0-30% discount
  - Merchant reputation: 0-20% discount
  - Regional supply/demand: ±20%
  - Item condition: 50-100% value

**Special Vendors:**
- **Kilvin's Workshop:** High-end sygaldric items, requires University access
- **Black Market (Imre):** Illegal items, requires discovering secret location
- **Traveling Merchants:** Random encounters, rare items

---

## Core MUD Systems

### Room & Area System

#### Room Structure

**Room Data Model:**
```python
@dataclass
class Room:
    id: int
    area_id: int
    title: str
    description: str
    exits: Dict[str, int]  # direction -> room_id
    items: List[int]  # item IDs in room
    npcs: List[int]  # NPC IDs in room
    players: Set[int]  # player IDs currently here
    flags: Set[RoomFlag]  # SAFE, DARK, NO_MAGIC, etc.
    climate: Climate  # INDOOR, OUTDOOR, UNDERGROUND
    terrain: Terrain  # ROAD, FOREST, WATER, URBAN, etc.
```

**Room Flags:**
- `SAFE`: No combat allowed
- `DARK`: Requires light source to see
- `NO_MAGIC`: Magic suppressed
- `INDOORS`: Weather doesn't affect
- `WATER`: Requires swimming or boat
- `DEATH_TRAP`: Instant death (use sparingly)
- `PRIVATE`: Limited player capacity

#### Area Organization

**Area Hierarchy:**
```
World
├── The Commonwealth
│   ├── The University
│   │   ├── Mews (Housing)
│   │   ├── Archives
│   │   ├── Artificery
│   │   └── Mains
│   ├── Imre
│   │   ├── Anker's Tavern
│   │   ├── Market District
│   │   └── Residential Quarter
│   └── Newarre
├── Vintas
│   └── Severen
├── Wilderness
│   ├── Eld Forest
│   └── Commonwealth Roads
└── Dungeons
    ├── Ancient Ruins
    └── Bandit Camps
```

**Area Properties:**
- Level range (recommended player level)
- Climate/weather patterns
- Faction ownership
- Danger rating
- Resource availability

#### Movement & Navigation

**Basic Commands:**
- `north`, `south`, `east`, `west`, `up`, `down`
- `enter <location>`, `exit`
- `go <direction>` or `walk <direction>`

**Special Movement:**
- `swim <direction>` (in water rooms)
- `climb <direction>` (for vertical challenges)
- `sneak <direction>` (stealth movement)

**Movement Costs:**
- Standard terrain: 1 movement point
- Difficult terrain: 2-3 movement points
- Swimming: 3-5 movement points
- Max movement points: based on Endurance stat

**Room Description Display:**
```
[The University Archives - Main Hall]
Towering shelves of books stretch into the shadows above. The scent of old
parchment and dust fills the air. A massive oak desk stands near the entrance,
where Master Lorren keeps eternal vigil over his domain. The Archives extend
deeper to the north, while the exit leads south.

Obvious exits: north, south
You see: a wooden reading desk, an oil lamp (lit)
Master Lorren is here, watching you suspiciously.
Simmon is here, studying a tome.
```

### Player Character System

#### Character Creation

**Step 1: Choose Name**
- Unique username (3-20 characters)
- Validation: alphanumeric, no offensive terms
- Stored in lowercase, displayed with proper capitalization

**Step 2: Choose Background**

| Background | Description | Starting Stats | Starting Items | Starting Wealth |
|------------|-------------|----------------|----------------|-----------------|
| Street Urchin | Grew up in Tarbean slums | STR 8, DEX 12, CON 10, INT 10, WIS 10, CHA 8 | Ragged clothes, rusty knife | 5 drabs |
| Merchant's Child | Apprenticed to trade | STR 9, DEX 10, CON 10, INT 12, WIS 11, CHA 11 | Common clothes, ledger, 20 drabs | 5 jots |
| Farmer's Son/Daughter | Rural upbringing | STR 11, DEX 10, CON 12, INT 9, WIS 10, CHA 9 | Sturdy clothes, walking stick | 2 jots |
| Noble Bastard | Educated but outcast | STR 9, DEX 10, CON 9, INT 12, WIS 10, CHA 12 | Fine clothes, letter of introduction | 20 talents |
| Edema Ruh | Traveling performer | STR 9, DEX 11, CON 10, INT 11, WIS 10, CHA 13 | Performer's clothes, small lute, 3 jots | 3 jots |
| Orphan Scholar | Self-taught, hungry for knowledge | STR 8, DEX 10, CON 9, INT 13, WIS 11, CHA 10 | Worn clothes, old book, 10 drabs | 1 jot |

**Step 3: Allocate Attribute Points**
- Receive 5 additional points to distribute
- Can increase any attribute by max +3 from base
- Minimum attribute: 6, Maximum: 18

**Step 4: Choose Starting Skills** (Pick 3)
- Sympathy, Alchemy, Artificery, Swordsmanship, Archery, Stealth,
  Performance, Lore, Mercantile, Medicine, Survival

#### Attributes

**Primary Attributes:**

| Attribute | Abbrev | Description | Affects |
|-----------|--------|-------------|---------|
| Strength | STR | Physical power | Melee damage, carrying capacity |
| Dexterity | DEX | Agility, reflexes | Dodge chance, initiative, ranged accuracy |
| Constitution | CON | Health, endurance | Max HP, movement points, poison resistance |
| Intelligence | INT | Reasoning, learning | Magic power, skill learning speed |
| Wisdom | WIS | Awareness, willpower | Alar strength, perception checks |
| Charisma | CHA | Personality, leadership | NPC reactions, performance quality |

**Derived Stats:**
- **Hit Points (HP):** `CON × 10 + Level × 5`
- **Movement Points (MP):** `CON × 2 + Level`
- **Alar Strength:** `(INT + WIS) / 2`
- **Initiative:** `DEX + d20`
- **Carrying Capacity:** `STR × 10` pounds

#### Progression System

**Experience Points (XP):**
- Combat encounters: 10-500 XP based on difficulty
- Quest completion: 50-2000 XP based on complexity
- Skill usage: 1-10 XP per successful use
- Exploration: 25 XP per new area discovered
- Roleplay: 10-50 XP for quality interactions (admin-awarded)

**Leveling Formula:**
```
XP Required for Level N = 1000 × N × (N + 1) / 2

Level 2: 1,000 XP
Level 3: 3,000 XP (cumulative)
Level 4: 6,000 XP (cumulative)
Level 5: 10,000 XP (cumulative)
Level 10: 55,000 XP (cumulative)
Level 20: 210,000 XP (cumulative)
```

**Level-Up Benefits:**
- +5 HP
- +1 Movement Point
- +1 Attribute Point (allocate freely)
- +1 Skill Point (increase any skill by 1)
- Every 5 levels: Choose 1 special ability/perk

**Level Cap:** 50 (for initial release)

#### Skills System

**Skill Categories:**

**Combat Skills:**
- Swordsmanship (melee accuracy/damage with swords)
- Brawling (unarmed combat)
- Archery (ranged accuracy/damage)
- Defense (dodge, parry, armor use)

**Magic Skills:**
- Sympathy (binding strength, efficiency)
- Naming (success chance, power)
- Alchemy (potion quality, success rate)
- Sygaldry (item enchantment quality)

**Practical Skills:**
- Stealth (hiding, sneaking, pickpocketing)
- Survival (tracking, foraging, navigation)
- Medicine (healing, diagnosis)
- Mercantile (buy/sell prices, appraisal)
- Performance (music, storytelling, earnings)
- Lore (knowledge checks, research speed)

**Skill Ranks:**
- 0-20: Novice
- 21-40: Apprentice
- 41-60: Journeyman
- 61-80: Expert
- 81-100: Master

**Skill Improvement:**
- Active use: Small XP per use
- Training: Study with NPC masters (costs money)
- Skill books: One-time skill boosts
- Practice: Repeatable skill-gaining activities

### NPC System

#### NPC Types

**1. Merchants**
- Buy/sell items
- Fixed inventory + random stock refresh
- Reputation affects prices

**2. Quest Givers**
- Offer quests based on player level/reputation
- Track quest state
- Provide rewards

**3. Trainers**
- Teach skills for money
- Require minimum stats/reputation
- Limited training capacity per level

**4. Combat NPCs**
- Aggressive enemies (attack on sight)
- Neutral guards (attack if provoked)
- Defensive creatures (flee or attack when cornered)

**5. Ambient NPCs**
- Flavor characters
- Provide lore/rumors
- Make world feel alive

#### NPC Behavior AI

**Behavior Types:**

```python
class NPCBehavior(Enum):
    STATIONARY = "stays in one room"
    PATROL = "walks a defined path"
    WANDER = "random movement within area"
    GUARD = "attacks hostiles entering area"
    FLEE = "runs from combat"
    HUNT = "actively seeks players"
```

**Aggression Levels:**
- **Passive:** Never attacks
- **Defensive:** Attacks if attacked
- **Aggressive:** Attacks on sight
- **Social:** Attacks if player has negative reputation

**Dialogue System:**
- Keyword-based responses
- Contextual dialogue (changes based on quest state)
- Random greetings/farewells
- Memory of past interactions (limited)

#### NPC Examples

**Master Kilvin (University Artificer)**
- Location: The Artificery
- Type: Trainer, Quest Giver, Merchant
- Sells: Sygaldric components, basic enchanted items
- Teaches: Artificery skill (up to rank 60)
- Quests: Craft-focused challenges
- Dialogue: Gruff but fair, appreciates good work

**Ambrose Jakis (Antagonist Student)**
- Location: The University (wanders)
- Type: Social Antagonist
- Behavior: Insults player, interferes with quests
- Combat: Will duel if provoked (cheats, uses political power)
- Impact: Reputation damage, creates obstacles

**Bandit (Enemy)**
- Location: Wilderness areas
- Type: Combat NPC
- Behavior: Aggressive, flees if health <30%
- Loot: 10-50 drabs, basic weapons
- Level: 3-7

### Combat System

#### Turn-Based Combat

**Combat Flow:**
1. Initiative: All combatants roll `Initiative = DEX + d20`
2. Turn Order: Highest to lowest initiative
3. Each turn: Choose action (attack, defend, use item, flee, cast magic)
4. Resolve action, apply effects
5. Check victory/defeat conditions
6. Next combatant's turn

**Action Types:**

**Attack:**
```
To Hit = d20 + Attack Skill + DEX modifier
    vs
Target Defense = 10 + Defense Skill + DEX modifier + Armor Bonus

If To Hit >= Defense:
    Damage = Weapon Damage + STR modifier - Armor Reduction
    Apply damage to target HP
```

**Defend:**
- Skip attack this turn
- Gain +5 Defense until next turn
- Recover 10% stamina

**Use Item:**
- Consume healing potion (+50 HP instant)
- Apply buff potion (lasts 5 rounds)
- Throw alchemical bomb (splash damage)

**Cast Magic:**
- Sympathy spell (damage transfer, kinetic push, etc.)
- Naming invocation (if Name is known)
- Costs energy, uses magic skill check

**Flee:**
- Success chance: `(Player DEX - Average Enemy DEX) × 10 + d100`
- If success: Escape to adjacent room
- If failure: Enemy gets free attack, try again next turn

#### Damage Types & Armor

**Damage Types:**
- **Physical:** Normal weapons (swords, arrows, fists)
- **Fire:** Alchemical flames, Naming
- **Cold:** Ice magic, environmental
- **Sympathetic:** Direct energy transfer (bypasses armor)

**Armor Types:**

| Armor | Defense Bonus | Damage Reduction | Movement Cost | Examples |
|-------|---------------|------------------|---------------|----------|
| None | 0 | 0 | 0 | Common clothes |
| Light | +2 | 2 | -1 MP | Leather jerkin |
| Medium | +4 | 4 | -2 MP | Chain shirt |
| Heavy | +6 | 6 | -3 MP | Plate armor (rare) |

#### Death & Respawn

**Player Death:**
1. HP reaches 0 → Player is "unconscious"
2. 3 rounds to receive healing or die permanently
3. If death: Player respawns at last safe location (University, inn)
4. **Death Penalty:**
   - Lose 10% of current level XP
   - Drop all carried items at death location (can retrieve)
   - Lose all drabs carried (money drops)
   - 30-minute debuff: -20% to all stats

**Permadeath Option (Hardcore Mode):**
- Optional character flag
- Death is permanent, character deleted
- Leaderboard for longest-surviving characters
- Special achievements/rewards

### Inventory & Equipment

#### Inventory System

**Capacity:**
- Maximum weight: `STR × 10` pounds
- Maximum item count: 50 items
- Equipped items don't count toward limit

**Item Slots:**
- Weapon (Right Hand)
- Shield/Off-hand (Left Hand)
- Armor (Body)
- Head
- Hands
- Feet
- Neck (amulet/pendant)
- Finger × 2 (rings)
- Back (cloak)
- Belt (pouch, holds extra items)

**Item Properties:**
```python
@dataclass
class Item:
    id: int
    name: str
    description: str
    item_type: ItemType
    weight: float
    value: int  # in drabs
    properties: Dict[str, Any]
    flags: Set[ItemFlag]
```

**Item Flags:**
- `QUEST_ITEM`: Cannot drop/sell
- `UNIQUE`: Only one can exist
- `CURSED`: Cannot unequip without Remove Curse
- `MAGICAL`: Enchanted, detectable
- `STOLEN`: Merchants won't buy, guards react

#### Item Types

**Weapons:**
- One-handed swords (1d8 damage, DEX/STR)
- Two-handed swords (2d6 damage, STR)
- Daggers (1d4 damage, DEX)
- Bows (1d8 damage, DEX, requires arrows)
- Staves (1d6 damage, INT for mages)

**Armor:**
- See Combat System armor table

**Consumables:**
- Healing potions (restore HP)
- Buff potions (temporary stat boosts)
- Food (restore movement points)
- Alchemical bombs (combat items)

**Tools:**
- Lockpicks (open locked doors/chests)
- Climbing rope (access high areas)
- Light sources (torches, lanterns)
- Bedroll (safe rest in wilderness)

**Special Items:**
- Sympathy sources (candles, braziers)
- Sygaldric devices (enchanted tools)
- Lore books (skill increases, quest clues)
- Musical instruments (performance)

#### Crafting System (Basic)

**Alchemy Crafting:**
```
Required: Alchemy skill, recipe, ingredients, alembic (tool)

Example - Healing Potion:
  Ingredients: 2× Willow Bark, 1× Honey, 1× Clean Water
  Skill Required: Alchemy 20
  Success Chance: (Alchemy Skill - 20) × 2 + 60%
  Result: Healing Potion (restores 50 HP)
```

**Artificery Crafting:**
```
Required: Artificery skill, sygaldry knowledge, materials, workshop access

Example - Sympathy Lamp:
  Materials: 1× Glass Sphere, 2× Iron Rods, 1× Heat Source
  Skill Required: Artificery 40, Sympathy 30
  Success Chance: (Artificery Skill - 40) × 2 + 50%
  Result: Ever-burning Lamp (provides light, never depletes)
```

### Chat & Communication

#### Communication Commands

**Local Chat:**
- `say <message>` or `'<message>`: Everyone in same room sees
- `emote <action>` or `:<action>`: Roleplay action
- `whisper <player> <message>`: Private message to player in same room

**Global Channels:**
- `chat <message>`: Global OOC (out-of-character) channel
- `newbie <message>`: Help channel for new players
- `roleplay <message>`: IC (in-character) global channel

**Private Communication:**
- `tell <player> <message>`: Private message to any online player
- `reply <message>`: Reply to last received tell

**Group Communication:**
- `gsay <message>`: Party/group chat
- `gchat <message>`: Guild chat (if in guild)

#### Social Features

**Friends List:**
- `friend add <player>`: Add to friends
- `friend remove <player>`: Remove from friends
- `friend list`: See online friends

**Ignore System:**
- `ignore <player>`: Block all communication
- `unignore <player>`: Remove block

**Emotes:**
Predefined and custom emotes for roleplay:
- `smile`, `laugh`, `cry`, `bow`, `wave`, `nod`, `shake`
- `emote studies the ancient tome carefully` → "Kvothe studies the ancient tome carefully."

### Quest System

#### Quest Structure

```python
@dataclass
class Quest:
    id: int
    title: str
    description: str
    giver_npc_id: int
    required_level: int
    prerequisites: List[int]  # other quest IDs
    objectives: List[Objective]
    rewards: QuestRewards
    time_limit: Optional[int]  # in game minutes, None = no limit
```

**Objective Types:**
- **Kill:** Defeat N of creature type
- **Collect:** Gather N items
- **Deliver:** Bring item to NPC
- **Explore:** Visit specific location
- **Talk:** Speak to NPC(s)
- **Escort:** Protect NPC to destination
- **Craft:** Create specific item

**Quest Rewards:**
- Experience points
- Money (talents/jots)
- Items (unique or standard)
- Reputation with faction
- Unlock new areas/quests

#### Quest Examples

**"Welcome to the University" (Tutorial Quest)**
- Giver: University Greeter
- Objectives:
  1. Find the Mews and speak to the Housing Master
  2. Visit the Archives entrance
  3. Speak to Master Kilvin in the Artificery
- Rewards: 100 XP, 5 jots, Map of University
- Level: 1

**"A Theft in the Archives" (Investigation Quest)**
- Giver: Master Lorren
- Prerequisites: University member, Level 5+
- Objectives:
  1. Question 3 students in the Mews
  2. Examine the crime scene in Archives level 2
  3. Find the stolen book (hidden in Imre)
  4. Return book to Lorren
- Rewards: 500 XP, 3 talents, +10 Lorren reputation
- Level: 5

**"Bandits on the Road" (Combat Quest)**
- Giver: Merchant in Imre
- Objectives:
  1. Travel to Commonwealth Road
  2. Defeat 5 bandits
  3. Return to merchant for reward
- Rewards: 300 XP, 2 talents, random loot item
- Level: 3

#### Quest Tracking

**Player Quest Log:**
- Active quests: Up to 10 concurrent
- Completed quests: Permanent record
- Failed quests: Can retry after 24 hours

**Quest Commands:**
- `quest log`: View active quests
- `quest info <quest_name>`: See details
- `quest abandon <quest_name>`: Drop quest

---

## Technical Stack & Infrastructure

### Project Structure

```
waystone-mud/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Application entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py         # Configuration management
│   │   └── database.py         # DB connection setup
│   ├── network/
│   │   ├── __init__.py
│   │   ├── telnet_server.py    # Telnet protocol handler
│   │   ├── websocket_server.py # WebSocket handler
│   │   ├── connection.py       # Connection abstraction
│   │   └── session.py          # Session management
│   ├── game/
│   │   ├── __init__.py
│   │   ├── engine.py           # Core game loop
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Command base class
│   │   │   ├── movement.py     # Movement commands
│   │   │   ├── communication.py
│   │   │   ├── combat.py
│   │   │   ├── magic.py
│   │   │   └── admin.py
│   │   ├── world/
│   │   │   ├── __init__.py
│   │   │   ├── room.py
│   │   │   ├── area.py
│   │   │   ├── item.py
│   │   │   └── loader.py       # Load world data
│   │   ├── character/
│   │   │   ├── __init__.py
│   │   │   ├── player.py
│   │   │   ├── npc.py
│   │   │   ├── attributes.py
│   │   │   └── skills.py
│   │   ├── systems/
│   │   │   ├── __init__.py
│   │   │   ├── combat.py
│   │   │   ├── magic/
│   │   │   │   ├── sympathy.py
│   │   │   │   ├── naming.py
│   │   │   │   ├── alchemy.py
│   │   │   │   └── sygaldry.py
│   │   │   ├── economy.py
│   │   │   ├── quest.py
│   │   │   └── university.py
│   │   └── ai/
│   │       ├── __init__.py
│   │       └── npc_behavior.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── character.py
│   │   │   ├── world.py
│   │   │   └── quest.py
│   │   └── migrations/
│   │       └── (alembic migrations)
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       ├── formatter.py        # Text formatting/coloring
│       └── validators.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures
│   ├── test_network/
│   ├── test_game/
│   ├── test_combat/
│   ├── test_magic/
│   └── integration/
├── data/
│   ├── world/
│   │   ├── areas/
│   │   │   ├── university.yaml
│   │   │   ├── imre.yaml
│   │   │   └── wilderness.yaml
│   │   ├── rooms/
│   │   ├── npcs/
│   │   └── items/
│   ├── quests/
│   └── config/
│       ├── skills.yaml
│       ├── spells.yaml
│       └── loot_tables.yaml
├── scripts/
│   ├── setup_db.py
│   ├── create_admin.py
│   └── populate_world.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── GAMEDESIGN.md
│   └── CONTRIBUTING.md
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── deploy.yml
│       └── security-scan.yml
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── pyproject.toml              # Poetry/uv dependencies
├── README.md
├── LICENSE
└── .env.example
```

### Database Schema

**PostgreSQL Tables:**

**users**
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_banned BOOLEAN DEFAULT FALSE,
    is_admin BOOLEAN DEFAULT FALSE
);
```

**characters**
```sql
CREATE TABLE characters (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(50) UNIQUE NOT NULL,
    background VARCHAR(50),
    level INTEGER DEFAULT 1,
    experience INTEGER DEFAULT 0,

    -- Attributes
    strength INTEGER DEFAULT 10,
    dexterity INTEGER DEFAULT 10,
    constitution INTEGER DEFAULT 10,
    intelligence INTEGER DEFAULT 10,
    wisdom INTEGER DEFAULT 10,
    charisma INTEGER DEFAULT 10,

    -- Derived stats
    hp_current INTEGER,
    hp_max INTEGER,
    movement_current INTEGER,
    movement_max INTEGER,

    -- Location
    current_room_id INTEGER,

    -- Currency (in drabs)
    money INTEGER DEFAULT 0,

    -- State
    is_online BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- JSONB for flexible data
    skills JSONB DEFAULT '{}',
    flags JSONB DEFAULT '{}',
    quest_state JSONB DEFAULT '{}'
);
```

**rooms**
```sql
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    area_id INTEGER REFERENCES areas(id),
    title VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    exits JSONB DEFAULT '{}',  -- {"north": 123, "south": 124}
    flags JSONB DEFAULT '[]',
    terrain VARCHAR(50),
    climate VARCHAR(50)
);
```

**items**
```sql
CREATE TABLE items (
    id SERIAL PRIMARY KEY,
    template_id INTEGER,  -- reference to item template
    location_type VARCHAR(20),  -- 'room', 'character', 'container'
    location_id INTEGER,  -- ID of room/character/container
    properties JSONB DEFAULT '{}'  -- custom properties, charges, etc.
);
```

**item_templates**
```sql
CREATE TABLE item_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    item_type VARCHAR(50),
    weight FLOAT,
    value INTEGER,  -- in drabs
    properties JSONB DEFAULT '{}'  -- damage, armor, effects, etc.
);
```

**npcs**
```sql
CREATE TABLE npcs (
    id SERIAL PRIMARY KEY,
    template_id INTEGER REFERENCES npc_templates(id),
    current_room_id INTEGER REFERENCES rooms(id),
    hp_current INTEGER,
    flags JSONB DEFAULT '{}',
    state JSONB DEFAULT '{}'  -- current behavior state, cooldowns, etc.
);
```

**quests**
```sql
CREATE TABLE quest_templates (
    id SERIAL PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    description TEXT,
    giver_npc_id INTEGER,
    required_level INTEGER,
    objectives JSONB NOT NULL,
    rewards JSONB NOT NULL
);

CREATE TABLE character_quests (
    id SERIAL PRIMARY KEY,
    character_id INTEGER REFERENCES characters(id),
    quest_id INTEGER REFERENCES quest_templates(id),
    state VARCHAR(20),  -- 'active', 'completed', 'failed'
    progress JSONB DEFAULT '{}',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

**Redis Data Structures:**

```
# Active sessions
session:<session_id> = {
    "user_id": 123,
    "character_id": 456,
    "connection_type": "telnet",
    "last_activity": timestamp
}

# Online users (sorted set by last activity)
online_users = [(character_id, timestamp), ...]

# Chat channels
channel:global = [list of messages]
channel:newbie = [list of messages]

# Rate limiting
ratelimit:<user_id>:<action> = count (with TTL)

# Combat state (temporary)
combat:<combat_id> = {
    "participants": [ids],
    "turn_order": [ids],
    "current_turn": id,
    "round": 3
}
```

### Configuration Management

**settings.py**
```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Application
    app_name: str = "Waystone MUD"
    debug: bool = False
    log_level: str = "INFO"

    # Network
    telnet_host: str = "0.0.0.0"
    telnet_port: int = 4000
    websocket_host: str = "0.0.0.0"
    websocket_port: int = 8765
    max_connections: int = 100

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "waystone"
    postgres_user: str = "waystone"
    postgres_password: str

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # Security
    secret_key: str
    session_timeout: int = 3600  # seconds
    bcrypt_rounds: int = 12

    # Game
    save_interval: int = 300  # seconds
    tick_rate: int = 2  # game ticks per second

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**.env.example**
```bash
# Application
DEBUG=False
LOG_LEVEL=INFO

# Network
TELNET_PORT=4000
WEBSOCKET_PORT=8765

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=waystone
POSTGRES_USER=waystone
POSTGRES_PASSWORD=your_secure_password_here

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Security
SECRET_KEY=generate_a_strong_random_key_here
BCRYPT_ROUNDS=12

# Game
SAVE_INTERVAL=300
TICK_RATE=2
```

### Dependency Management

**pyproject.toml** (for uv)
```toml
[project]
name = "waystone-mud"
version = "0.1.0"
description = "A Multi-User Dungeon set in the Kingkiller Chronicle universe"
authors = [{name = "Waystone Team"}]
requires-python = ">=3.12"
dependencies = [
    "telnetlib3>=2.0.0",
    "websockets>=12.0",
    "sqlalchemy>=2.0.0",
    "psycopg[binary]>=3.1.0",
    "redis>=5.0.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "bcrypt>=4.1.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
    "black>=23.11.0",
]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]  # Line too long (handled by formatter)

[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "--cov=src --cov-report=html --cov-report=term"

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

### Docker Configuration

**Dockerfile**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN uv pip install --system -e ".[dev]"

# Copy application code
COPY src/ ./src/
COPY data/ ./data/
COPY scripts/ ./scripts/

# Create non-root user
RUN useradd -m -u 1000 muduser && chown -R muduser:muduser /app
USER muduser

# Expose ports
EXPOSE 4000 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(); s.connect(('localhost', 4000)); s.close()"

# Start application
CMD ["python", "-m", "src.main"]
```

**docker-compose.yml** (Development)
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: waystone
      POSTGRES_USER: waystone
      POSTGRES_PASSWORD: dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U waystone"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  mud:
    build: .
    ports:
      - "4000:4000"
      - "8765:8765"
    environment:
      DEBUG: "True"
      POSTGRES_HOST: postgres
      POSTGRES_PASSWORD: dev_password
      REDIS_HOST: redis
      SECRET_KEY: dev_secret_key_change_in_production
    volumes:
      - ./src:/app/src
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
```

---

## CI/CD Pipeline

### GitHub Actions Workflows

**.github/workflows/ci.yml**
```yaml
name: CI Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv pip install --system -e ".[dev]"

      - name: Run ruff (linting)
        run: ruff check src/ tests/

      - name: Run ruff (formatting check)
        run: ruff format --check src/ tests/

      - name: Run mypy (type checking)
        run: mypy src/

  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: waystone_test
          POSTGRES_USER: waystone
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv pip install --system -e ".[dev]"

      - name: Run tests with coverage
        env:
          POSTGRES_HOST: localhost
          POSTGRES_DB: waystone_test
          POSTGRES_USER: waystone
          POSTGRES_PASSWORD: test_password
          REDIS_HOST: localhost
          SECRET_KEY: test_secret_key
        run: pytest --cov --cov-report=xml --cov-report=term

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

      - name: Check coverage threshold
        run: |
          coverage report --fail-under=80

  integration:
    runs-on: ubuntu-latest
    needs: [lint, test]

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t waystone-mud:test .

      - name: Run integration tests
        run: docker-compose -f docker-compose.yml up -d

      - name: Wait for services
        run: sleep 10

      - name: Test Telnet connection
        run: |
          timeout 5 telnet localhost 4000 || exit 0

      - name: Check logs
        if: failure()
        run: docker-compose logs

      - name: Cleanup
        if: always()
        run: docker-compose down -v

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'

      - name: Upload Trivy results to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: 'trivy-results.sarif'
```

**.github/workflows/deploy.yml**
```yaml
name: Deploy

on:
  push:
    branches: [ main ]
    tags:
      - 'v*'

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    environment: staging

    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        run: |
          echo "Deploy to staging server"
          # SSH deployment commands here
          # scp, rsync, or docker registry push

      - name: Run smoke tests
        run: |
          echo "Running smoke tests on staging"
          # Basic connection tests

  deploy-production:
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    environment: production
    needs: [deploy-staging]

    steps:
      - uses: actions/checkout@v4

      - name: Build production image
        run: docker build -t waystone-mud:${{ github.ref_name }} .

      - name: Deploy to production
        run: |
          echo "Deploy to production server"
          # Production deployment steps

      - name: Create GitHub Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          draft: false
          prerelease: false
```

**.github/workflows/security-scan.yml**
```yaml
name: Security Scan

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  dependency-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install uv
        run: pip install uv

      - name: Check for vulnerabilities
        run: |
          uv pip install --system safety
          safety check --json

      - name: Dependabot alerts
        run: echo "Check GitHub Dependabot alerts manually"
```

### Testing Strategy

#### Unit Tests

**Coverage Requirements:**
- Overall: 80%+ code coverage
- Critical systems (combat, magic, economy): 90%+
- Network layer: 70%+
- Utilities: 85%+

**Test Organization:**
```
tests/
├── test_network/
│   ├── test_telnet_server.py
│   ├── test_websocket_server.py
│   └── test_session.py
├── test_game/
│   ├── test_commands.py
│   ├── test_world.py
│   └── test_character.py
├── test_systems/
│   ├── test_combat.py
│   ├── test_sympathy.py
│   ├── test_economy.py
│   └── test_quest.py
└── integration/
    ├── test_full_flow.py
    └── test_performance.py
```

**Example Test (test_combat.py):**
```python
import pytest
from src.game.systems.combat import CombatSystem
from src.game.character.player import Player
from src.game.character.npc import NPC

@pytest.fixture
def combat_system():
    return CombatSystem()

@pytest.fixture
def player():
    return Player(
        name="TestPlayer",
        strength=12,
        dexterity=14,
        constitution=10,
        level=5
    )

@pytest.fixture
def enemy():
    return NPC(
        name="Bandit",
        strength=10,
        dexterity=12,
        constitution=8,
        level=3
    )

def test_initiative_calculation(combat_system, player, enemy):
    """Test that initiative is calculated correctly."""
    combat = combat_system.start_combat([player, enemy])

    # Initiative = DEX + d20 (mocked)
    assert len(combat.turn_order) == 2
    assert player in combat.turn_order
    assert enemy in combat.turn_order

def test_attack_hit(combat_system, player, enemy, monkeypatch):
    """Test successful attack."""
    # Mock d20 roll to guarantee hit
    monkeypatch.setattr('random.randint', lambda a, b: 20)

    combat = combat_system.start_combat([player, enemy])
    initial_hp = enemy.hp

    damage = combat_system.attack(player, enemy)

    assert damage > 0
    assert enemy.hp < initial_hp
    assert enemy.hp == initial_hp - damage

def test_attack_miss(combat_system, player, enemy, monkeypatch):
    """Test missed attack."""
    # Mock d20 roll to guarantee miss
    monkeypatch.setattr('random.randint', lambda a, b: 1)

    combat = combat_system.start_combat([player, enemy])
    initial_hp = enemy.hp

    damage = combat_system.attack(player, enemy)

    assert damage == 0
    assert enemy.hp == initial_hp

def test_combat_victory(combat_system, player, enemy):
    """Test combat ending when enemy HP reaches 0."""
    combat = combat_system.start_combat([player, enemy])

    # Reduce enemy to 0 HP
    enemy.hp = 0

    assert combat_system.check_victory(combat) == player
    assert combat.is_finished

@pytest.mark.asyncio
async def test_combat_timeout(combat_system, player):
    """Test that combat times out if no action taken."""
    combat = combat_system.start_combat([player])

    # Simulate 30 seconds of inactivity
    await asyncio.sleep(0.1)  # Mocked time

    # Should auto-flee or forfeit
    assert combat_system.check_timeout(combat)
```

#### Integration Tests

**Full Flow Test:**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_player_registration_and_login():
    """Test complete player registration and login flow."""
    async with TelnetClient() as client:
        # Connect
        await client.connect('localhost', 4000)

        # Receive welcome message
        welcome = await client.receive()
        assert "Welcome to Waystone MUD" in welcome

        # Register new account
        await client.send("register testuser password123 test@example.com")
        response = await client.receive()
        assert "Account created" in response

        # Login
        await client.send("login testuser password123")
        response = await client.receive()
        assert "Logged in" in response

        # Create character
        await client.send("create Kvothe")
        response = await client.receive()
        assert "Character creation" in response

        # Enter game world
        await client.send("enter")
        response = await client.receive()
        assert "You enter the world" in response
```

#### Performance Tests

**Load Testing:**
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_connections():
    """Test server can handle 100 concurrent connections."""
    clients = []

    # Create 100 connections
    for i in range(100):
        client = TelnetClient()
        await client.connect('localhost', 4000)
        clients.append(client)

    # All should receive welcome message
    for client in clients:
        welcome = await asyncio.wait_for(client.receive(), timeout=5)
        assert welcome is not None

    # Cleanup
    for client in clients:
        await client.disconnect()

@pytest.mark.performance
def test_command_response_time():
    """Test that commands respond within 100ms."""
    import time

    start = time.time()
    result = game_engine.execute_command(player, "look")
    end = time.time()

    assert (end - start) < 0.1  # 100ms
```

### Deployment Stages

**1. Development**
- Local development with Docker Compose
- Hot reload enabled
- Debug logging
- Test database

**2. Staging**
- Deployed on every push to `main` branch
- Production-like environment
- Automated smoke tests
- Accessible for internal testing

**3. Production**
- Deployed on version tags (`v1.0.0`)
- Manual approval required
- Database migrations run automatically
- Health checks before traffic routing
- Rollback capability

**Deployment Checklist:**
- [ ] All CI tests passing
- [ ] Code coverage ≥80%
- [ ] Security scans clean
- [ ] Database migrations tested
- [ ] Backup created
- [ ] Monitoring configured
- [ ] Rollback plan documented

---

## Implementation Phases

### Phase 1: Core Infrastructure (MVP) - 2 Weeks

**Goal:** Create a playable MUD with basic room navigation, authentication, and communication.

**Deliverables:**
- Working Telnet server accepting connections
- User registration and login
- Basic character creation
- 10-15 interconnected rooms
- Movement commands (north, south, east, west)
- Communication commands (say, emote)
- Database persistence (users, characters, rooms)
- Basic error handling and logging

#### Implementation Checklist

**Week 1: Foundation**

**Day 1-2: Project Setup**
- [ ] Initialize Git repository
- [ ] Create project structure (see Technical Stack section)
- [ ] Set up `pyproject.toml` with uv dependencies
- [ ] Create Docker Compose environment (PostgreSQL, Redis, App)
- [ ] Configure `.env` file with development settings
- [ ] Write `README.md` with setup instructions
- [ ] Initialize PostgreSQL database schema
  - [ ] Create `users` table
  - [ ] Create `characters` table
  - [ ] Create `rooms` table
- [ ] Set up Alembic for database migrations
- [ ] Create first migration: initial schema

**Day 3-4: Network Layer**
- [ ] Implement `src/network/telnet_server.py`
  - [ ] Async Telnet server using `telnetlib3`
  - [ ] Connection handler (accept, manage, disconnect)
  - [ ] Input buffering and line parsing
- [ ] Implement `src/network/session.py`
  - [ ] Session class with state management
  - [ ] Redis integration for session storage
  - [ ] Session timeout handling
- [ ] Implement `src/network/connection.py`
  - [ ] Connection abstraction layer
  - [ ] Send/receive methods
  - [ ] Color code support (ANSI)
- [ ] Write tests:
  - [ ] `tests/test_network/test_telnet_server.py`
  - [ ] `tests/test_network/test_session.py`

**Day 5-7: Authentication & Character Creation**
- [ ] Implement `src/database/models/user.py`
  - [ ] User SQLAlchemy model
  - [ ] Password hashing with bcrypt
  - [ ] Email validation
- [ ] Implement `src/database/models/character.py`
  - [ ] Character SQLAlchemy model
  - [ ] Attribute fields (STR, DEX, CON, INT, WIS, CHA)
  - [ ] Inventory and location tracking
- [ ] Implement authentication commands:
  - [ ] `register <username> <password> <email>`
  - [ ] `login <username> <password>`
  - [ ] `logout`
- [ ] Implement character creation flow:
  - [ ] Choose name (validation)
  - [ ] Choose background (6 options from PRD)
  - [ ] Allocate 5 bonus attribute points
  - [ ] Save to database
- [ ] Write tests:
  - [ ] `tests/test_game/test_auth.py`
  - [ ] `tests/test_game/test_character_creation.py`

**Week 2: Basic Gameplay**

**Day 8-10: World & Movement**
- [ ] Implement `src/game/world/room.py`
  - [ ] Room class with all properties
  - [ ] Exit validation
  - [ ] Player tracking (who's in room)
- [ ] Implement `src/game/world/loader.py`
  - [ ] Load rooms from `data/world/rooms/university.yaml`
  - [ ] Populate database with initial rooms
  - [ ] Validate room connections
- [ ] Create initial world data:
  - [ ] Design 15 rooms (University + Imre)
  - [ ] Write `data/world/rooms/university.yaml`
  - [ ] Write `data/world/rooms/imre.yaml`
- [ ] Implement movement commands:
  - [ ] `north`, `south`, `east`, `west`, `up`, `down`
  - [ ] `look` - view current room
  - [ ] `exits` - show available exits
- [ ] Implement `src/game/commands/movement.py`
  - [ ] Movement validation (exit exists)
  - [ ] Update character location in DB
  - [ ] Notify players in both rooms (player left/entered)
- [ ] Write tests:
  - [ ] `tests/test_game/test_movement.py`
  - [ ] `tests/test_game/test_world.py`

**Day 11-12: Communication**
- [ ] Implement `src/game/commands/communication.py`
  - [ ] `say <message>` - local chat
  - [ ] `emote <action>` - roleplay action
  - [ ] `chat <message>` - global OOC channel
  - [ ] `tell <player> <message>` - private message
- [ ] Implement Redis pub/sub for chat channels:
  - [ ] Global chat channel
  - [ ] Room-based message broadcasting
- [ ] Implement messaging utilities:
  - [ ] `src/utils/formatter.py` - text formatting, ANSI colors
  - [ ] Message broadcasting to room
  - [ ] Message targeting specific player
- [ ] Write tests:
  - [ ] `tests/test_game/test_communication.py`

**Day 13-14: Integration & Polish**
- [ ] Implement `src/game/engine.py`
  - [ ] Main game loop
  - [ ] Command parsing and routing
  - [ ] Error handling
  - [ ] Player command queue
- [ ] Implement `src/main.py`
  - [ ] Application entry point
  - [ ] Start Telnet server
  - [ ] Initialize database connections
  - [ ] Graceful shutdown handling
- [ ] Create helper scripts:
  - [ ] `scripts/setup_db.py` - initialize database
  - [ ] `scripts/create_admin.py` - create admin account
  - [ ] `scripts/populate_world.py` - load initial world data
- [ ] Write integration tests:
  - [ ] `tests/integration/test_full_flow.py`
  - [ ] Test: connect, register, login, create character, move, chat
- [ ] Set up GitHub Actions CI:
  - [ ] `.github/workflows/ci.yml`
  - [ ] Lint, type check, unit tests, coverage
- [ ] Write documentation:
  - [ ] `docs/ARCHITECTURE.md`
  - [ ] `docs/SETUP.md`
  - [ ] Update `README.md` with usage instructions

#### Acceptance Criteria

- [ ] Player can connect via Telnet client (e.g., `telnet localhost 4000`)
- [ ] Player can register a new account
- [ ] Player can log in with correct credentials
- [ ] Player can create a character with custom name and background
- [ ] Player can see room descriptions when entering
- [ ] Player can move between 15 interconnected rooms
- [ ] Player can use `say` and `emote` commands
- [ ] Multiple players can be online simultaneously
- [ ] Chat messages are visible to correct recipients
- [ ] All data persists across server restarts
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes all checks
- [ ] No critical security vulnerabilities
- [ ] Server runs stable for 1+ hour under normal load

---

### Phase 2: Character System - 2 Weeks

**Goal:** Implement complete character progression, inventory, and equipment systems.

**Deliverables:**
- Full attribute and derived stats system
- Experience points and leveling
- Skills system with training
- Inventory management
- Equipment slots and bonuses
- Character persistence and saving

#### Implementation Checklist

**Week 3: Attributes & Progression**

**Day 15-16: Attributes & Derived Stats**
- [ ] Implement `src/game/character/attributes.py`
  - [ ] Attribute class (STR, DEX, CON, INT, WIS, CHA)
  - [ ] Attribute modifiers calculation
  - [ ] Derived stats formulas (HP, MP, Alar, etc.)
  - [ ] Attribute increase on level-up
- [ ] Update `Character` model:
  - [ ] Add `experience` field
  - [ ] Add `attribute_points` (unspent)
  - [ ] Add HP/MP current and max fields
- [ ] Implement character stat display:
  - [ ] `stats` command - show full character sheet
  - [ ] `attributes` command - detailed attribute view
- [ ] Write tests:
  - [ ] `tests/test_game/test_attributes.py`

**Day 17-19: Experience & Leveling**
- [ ] Implement `src/game/systems/experience.py`
  - [ ] XP award function (by source type)
  - [ ] Level-up XP calculation
  - [ ] Level-up handler (attribute points, HP increase)
  - [ ] Level-up notification
- [ ] Implement XP sources:
  - [ ] Exploration (discover new room: 25 XP)
  - [ ] First login bonus (100 XP)
  - [ ] Placeholder for future sources (combat, quests)
- [ ] Implement level-up flow:
  - [ ] Automatic level-up when XP threshold reached
  - [ ] Notify player of level-up
  - [ ] Grant attribute point
  - [ ] Increase HP/MP
- [ ] Implement attribute allocation:
  - [ ] `increase <attribute>` command
  - [ ] Validation (has unspent points, valid attribute)
  - [ ] Update character stats
- [ ] Write tests:
  - [ ] `tests/test_game/test_experience.py`
  - [ ] `tests/test_game/test_leveling.py`

**Day 20-21: Skills System**
- [ ] Implement `src/game/character/skills.py`
  - [ ] Skill class (name, rank, XP)
  - [ ] Skill rank tiers (Novice, Apprentice, etc.)
  - [ ] Skill XP gain calculation
  - [ ] Skill rank-up logic
- [ ] Update `Character` model:
  - [ ] Skills JSONB field structure
  - [ ] Default skills on character creation
- [ ] Implement skill commands:
  - [ ] `skills` - show all skills and ranks
  - [ ] `train <skill>` - practice skill (costs money, grants XP)
- [ ] Create skill data file:
  - [ ] `data/config/skills.yaml`
  - [ ] Define all skills (Combat, Magic, Practical)
  - [ ] Specify base costs and XP curves
- [ ] Write tests:
  - [ ] `tests/test_game/test_skills.py`

**Week 4: Inventory & Equipment**

**Day 22-24: Items & Inventory**
- [ ] Implement `src/game/world/item.py`
  - [ ] Item class (template-based)
  - [ ] Item flags (QUEST_ITEM, UNIQUE, etc.)
  - [ ] Item stacking logic
- [ ] Implement `src/database/models/item.py`
  - [ ] `item_templates` table model
  - [ ] `items` table model (instances)
  - [ ] Location tracking (room, character, container)
- [ ] Create initial item data:
  - [ ] `data/world/items/weapons.yaml`
  - [ ] `data/world/items/armor.yaml`
  - [ ] `data/world/items/consumables.yaml`
  - [ ] `data/world/items/misc.yaml`
- [ ] Implement inventory commands:
  - [ ] `inventory` or `i` - show all carried items
  - [ ] `get <item>` - pick up item from room
  - [ ] `drop <item>` - drop item to room
  - [ ] `give <item> <player>` - give item to another player
- [ ] Implement weight/capacity system:
  - [ ] Calculate total carried weight
  - [ ] Prevent pickup if over capacity
  - [ ] Display weight in inventory
- [ ] Write tests:
  - [ ] `tests/test_game/test_item.py`
  - [ ] `tests/test_game/test_inventory.py`

**Day 25-26: Equipment System**
- [ ] Implement `src/game/character/equipment.py`
  - [ ] Equipment slots (weapon, armor, accessories)
  - [ ] Equip/unequip logic
  - [ ] Equipment stat bonuses
- [ ] Update `Character` model:
  - [ ] Equipment JSONB field (slot -> item_id mapping)
- [ ] Implement equipment commands:
  - [ ] `equip <item>` - equip an item from inventory
  - [ ] `unequip <slot>` - unequip item in slot
  - [ ] `equipment` or `eq` - show equipped items
- [ ] Implement stat calculation with equipment:
  - [ ] Recalculate stats when equipment changes
  - [ ] Apply bonuses from equipped items
  - [ ] Display effective stats vs base stats
- [ ] Write tests:
  - [ ] `tests/test_game/test_equipment.py`

**Day 27-28: Persistence & Polish**
- [ ] Implement auto-save system:
  - [ ] `src/game/systems/persistence.py`
  - [ ] Periodic save timer (every 5 minutes)
  - [ ] Save on logout
  - [ ] Save on critical events (level-up, loot)
- [ ] Implement character commands:
  - [ ] `save` - manual save
  - [ ] `score` - quick stat summary
  - [ ] `worth` - show total wealth
- [ ] Optimize database queries:
  - [ ] Eager loading for character data
  - [ ] Batch updates for inventory
- [ ] Write integration tests:
  - [ ] `tests/integration/test_character_system.py`
  - [ ] Test: level-up, skill gain, inventory management
- [ ] Update documentation:
  - [ ] `docs/GAMEDESIGN.md` - character system details
  - [ ] `docs/COMMANDS.md` - player command reference

#### Acceptance Criteria

- [ ] Character attributes affect derived stats correctly
- [ ] Players gain XP from exploration
- [ ] Players level up automatically when XP threshold reached
- [ ] Players can allocate attribute points on level-up
- [ ] Skills display with ranks and can be trained
- [ ] Players can pick up, drop, and carry items
- [ ] Weight limit prevents carrying too much
- [ ] Players can equip weapons and armor
- [ ] Equipment bonuses apply to stats correctly
- [ ] All character data persists across sessions
- [ ] `save` command works manually
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

### Phase 3: Combat & NPCs - 2 Weeks

**Goal:** Implement turn-based combat system and NPC interactions.

**Deliverables:**
- Turn-based combat engine
- Attack, defend, flee actions
- NPC combat AI
- Loot system
- Basic NPCs (merchants, enemies)
- Death and respawn mechanics

#### Implementation Checklist

**Week 5: Combat System**

**Day 29-30: Combat Engine Core**
- [ ] Implement `src/game/systems/combat.py`
  - [ ] Combat class (manages a single combat instance)
  - [ ] Initiative calculation and turn order
  - [ ] Combat state machine (setup, in_progress, ended)
  - [ ] Turn timer (30 seconds for action)
- [ ] Implement combat initiation:
  - [ ] `attack <target>` command
  - [ ] Validate target (same room, not self, alive)
  - [ ] Create combat instance
  - [ ] Roll initiative for all participants
- [ ] Implement combat round loop:
  - [ ] Process turn order
  - [ ] Await player action or timeout
  - [ ] Apply action effects
  - [ ] Check victory/defeat conditions
- [ ] Write tests:
  - [ ] `tests/test_systems/test_combat.py`
  - [ ] Test initiative, turn order, state transitions

**Day 31-32: Combat Actions**
- [ ] Implement attack action:
  - [ ] To-hit roll: `d20 + skill + DEX mod vs Defense`
  - [ ] Damage calculation: `weapon damage + STR mod - armor reduction`
  - [ ] Apply damage to target HP
  - [ ] Broadcast combat messages to room
- [ ] Implement defend action:
  - [ ] Grant +5 defense until next turn
  - [ ] Recover 10% stamina
  - [ ] Skip attack this turn
- [ ] Implement flee action:
  - [ ] Success chance based on DEX difference
  - [ ] On success: move to random adjacent room
  - [ ] On failure: enemy gets free attack
- [ ] Implement item use in combat:
  - [ ] Use healing potion
  - [ ] Use buff item
  - [ ] Consume action
- [ ] Write tests:
  - [ ] `tests/test_systems/test_combat_actions.py`

**Day 33-35: Death, Loot & Rewards**
- [ ] Implement death mechanics:
  - [ ] HP reaches 0 → unconscious state
  - [ ] 3 rounds to receive healing
  - [ ] If not healed → death
- [ ] Implement player death:
  - [ ] Drop all inventory at death location
  - [ ] Lose 10% current level XP
  - [ ] Respawn at safe location (University)
  - [ ] Apply 30-minute debuff (-20% stats)
- [ ] Implement NPC death:
  - [ ] Award XP to victors
  - [ ] Generate loot based on loot table
  - [ ] Remove NPC from room
  - [ ] Schedule respawn (if applicable)
- [ ] Implement loot system:
  - [ ] `src/game/systems/loot.py`
  - [ ] Loot table data: `data/config/loot_tables.yaml`
  - [ ] Random loot generation
  - [ ] Drop loot to room on death
- [ ] Write tests:
  - [ ] `tests/test_systems/test_death.py`
  - [ ] `tests/test_systems/test_loot.py`

**Week 6: NPCs**

**Day 36-38: NPC System**
- [ ] Implement `src/game/character/npc.py`
  - [ ] NPC class (inherits from base character)
  - [ ] NPC templates (loaded from YAML)
  - [ ] NPC instance spawning
  - [ ] NPC stats and attributes
- [ ] Implement `src/database/models/npc.py`
  - [ ] `npc_templates` table
  - [ ] `npcs` table (instances)
  - [ ] Respawn tracking
- [ ] Create NPC data:
  - [ ] `data/world/npcs/enemies.yaml` (bandits, wolves, draccus)
  - [ ] `data/world/npcs/merchants.yaml` (shopkeepers, traders)
  - [ ] `data/world/npcs/university.yaml` (Masters, students)
- [ ] Implement NPC spawning:
  - [ ] Load NPC templates on startup
  - [ ] Spawn NPCs in designated rooms
  - [ ] Track spawned NPC instances
- [ ] Write tests:
  - [ ] `tests/test_game/test_npc.py`

**Day 39-40: NPC AI & Behavior**
- [ ] Implement `src/game/ai/npc_behavior.py`
  - [ ] Behavior types (STATIONARY, PATROL, WANDER, etc.)
  - [ ] Aggression levels (PASSIVE, AGGRESSIVE, etc.)
  - [ ] Decision-making logic
- [ ] Implement NPC behaviors:
  - [ ] Stationary: stay in room
  - [ ] Patrol: walk predefined path
  - [ ] Wander: random movement in area
  - [ ] Guard: attack hostiles
  - [ ] Flee: run when low HP
- [ ] Implement NPC combat AI:
  - [ ] Choose action based on HP, stats
  - [ ] Prioritize targets (lowest HP, highest threat)
  - [ ] Use items if available
  - [ ] Flee at <30% HP (if behavior allows)
- [ ] Implement NPC tick system:
  - [ ] Periodic AI updates (every 2 seconds)
  - [ ] Execute behavior (movement, actions)
  - [ ] Update NPC state
- [ ] Write tests:
  - [ ] `tests/test_ai/test_npc_behavior.py`

**Day 41-42: NPC Interactions**
- [ ] Implement merchant NPCs:
  - [ ] `src/game/systems/merchant.py`
  - [ ] Merchant inventory system
  - [ ] Buy/sell commands
  - [ ] Price calculation with modifiers
- [ ] Implement merchant commands:
  - [ ] `list` - show merchant inventory
  - [ ] `buy <item>` - purchase item
  - [ ] `sell <item>` - sell item to merchant
  - [ ] `appraise <item>` - check item value
- [ ] Implement NPC dialogue:
  - [ ] `talk <npc>` - initiate conversation
  - [ ] Keyword-based responses
  - [ ] Quest hints in dialogue
- [ ] Create initial merchants:
  - [ ] General store in Imre (basic supplies)
  - [ ] Weapon smith (weapons, armor)
  - [ ] University artificer (magical items)
- [ ] Write tests:
  - [ ] `tests/test_systems/test_merchant.py`
  - [ ] `tests/test_game/test_npc_dialogue.py`

#### Acceptance Criteria

- [ ] Players can initiate combat with NPCs
- [ ] Turn-based combat works with initiative order
- [ ] Players can attack, defend, flee, use items
- [ ] Damage calculation includes stats, weapons, armor
- [ ] Players and NPCs die when HP reaches 0
- [ ] Player death penalty works (XP loss, respawn, debuff)
- [ ] NPCs drop loot on death
- [ ] XP awarded for defeating NPCs
- [ ] NPCs spawn in designated rooms
- [ ] NPCs exhibit behaviors (wander, patrol, guard)
- [ ] Aggressive NPCs attack players on sight
- [ ] NPCs have combat AI (choose actions intelligently)
- [ ] Merchant NPCs allow buying/selling
- [ ] Prices affected by player's Mercantile skill
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

### Phase 4: Magic - Sympathy System - 2 Weeks

**Goal:** Implement the Sympathy magic system with bindings, energy sources, and progression.

**Deliverables:**
- Sympathy binding mechanics
- Energy sources (heat sources, body heat)
- Binding efficiency calculation
- Alar attribute and progression
- Sympathetic backlash risks
- Integration with combat system
- University sympathy training

#### Implementation Checklist

**Week 7: Sympathy Core**

**Day 43-44: Energy & Heat Sources**
- [ ] Implement `src/game/systems/magic/sympathy.py`
  - [ ] Energy source class
  - [ ] Heat source types (candle, torch, brazier, body)
  - [ ] Energy consumption mechanics
  - [ ] Energy pool tracking
- [ ] Implement heat source items:
  - [ ] Add to `data/world/items/magic.yaml`
  - [ ] Candle (50 energy/turn)
  - [ ] Torch (150 energy/turn)
  - [ ] Brazier (500 energy/turn)
  - [ ] Body heat (100 energy/turn, DANGEROUS)
- [ ] Implement heat source management:
  - [ ] `hold <heat_source>` - designate active source
  - [ ] Track remaining energy
  - [ ] Notify when depleted
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_energy.py`

**Day 45-47: Binding Mechanics**
- [ ] Implement binding system:
  - [ ] Binding class (source, target, type, strength)
  - [ ] Similarity scoring algorithm
  - [ ] Consanguinity modifier calculation
  - [ ] Distance factor
- [ ] Implement similarity scores:
  - [ ] Material database (metals, woods, etc.)
  - [ ] Similarity comparison function
  - [ ] Category matching (metal-to-metal)
- [ ] Implement binding types:
  - [ ] Heat Transfer (warm/freeze objects)
  - [ ] Kinetic Transfer (push/lift)
  - [ ] Damage Transfer (combat use)
  - [ ] Dowsing (locate objects)
  - [ ] Light Binding (create light)
- [ ] Implement binding efficiency:
  - [ ] Calculate based on similarity + consanguinity
  - [ ] Apply Alar modifier (from WIS + INT)
  - [ ] Cap efficiency by rank (E'lir: 50%, Re'lar: 70%, etc.)
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_bindings.py`

**Day 48-49: Sympathy Commands & Usage**
- [ ] Implement sympathy commands:
  - [ ] `bind <source> <target> <type>` - create binding
  - [ ] `release` - end current binding
  - [ ] `bindings` - show active bindings
  - [ ] `push <target>` - kinetic binding shortcut
  - [ ] `heat <target>` - heat transfer shortcut
- [ ] Implement binding execution:
  - [ ] Validate source and target exist
  - [ ] Calculate efficiency
  - [ ] Consume energy from heat source
  - [ ] Apply effect to target
  - [ ] Update binding state
- [ ] Implement multi-binding:
  - [ ] Allow multiple simultaneous bindings
  - [ ] Maximum based on Alar strength
  - [ ] Split efficiency across bindings
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_commands.py`

**Week 8: Combat Integration & Progression**

**Day 50-51: Sympathy in Combat**
- [ ] Implement sympathetic combat:
  - [ ] Damage Transfer binding in combat
  - [ ] Use as combat action (attack alternative)
  - [ ] Calculate damage based on efficiency
  - [ ] Bypasses armor (direct energy transfer)
- [ ] Implement combat sympathy commands:
  - [ ] `cast damage <target>` - sympathetic attack
  - [ ] Uses current heat source
  - [ ] Consumes energy per turn
  - [ ] Requires maintained binding
- [ ] Implement sympathetic defense:
  - [ ] Heat shield (absorb incoming energy)
  - [ ] Kinetic deflection (push projectiles)
  - [ ] Costs energy to maintain
- [ ] Update combat system:
  - [ ] Add sympathy as action option
  - [ ] Track energy expenditure
  - [ ] Handle heat source depletion
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_combat.py`

**Day 52-53: Sympathetic Backlash**
- [ ] Implement backlash system:
  - [ ] Risk calculation based on energy transferred
  - [ ] Backlash severity levels (minor, moderate, severe, critical)
  - [ ] Random backlash trigger on risky bindings
- [ ] Implement backlash effects:
  - [ ] Minor: Headache, -10% max energy for 1 hour
  - [ ] Moderate: Unconsciousness for 5 minutes, -20% Alar
  - [ ] Severe: Brain damage, temporary INT/WIS loss
  - [ ] Critical: Death
- [ ] Implement body heat danger:
  - [ ] Using body heat increases backlash risk
  - [ ] Rapid hypothermia if too much drawn
  - [ ] Special warnings for body heat use
- [ ] Implement safety mechanics:
  - [ ] Energy transfer limits based on skill
  - [ ] Warning messages at risk thresholds
  - [ ] Automatic release if critical risk
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_backlash.py`

**Day 54-56: Sympathy Progression**
- [ ] Implement Sympathy skill progression:
  - [ ] Grant Sympathy XP for each binding
  - [ ] More XP for complex bindings
  - [ ] Skill-up increases efficiency cap
- [ ] Implement Alar training:
  - [ ] Alar exercises (special training command)
  - [ ] University Sympathy classes (Master Elxa Dal)
  - [ ] Alar directly increases from Sympathy skill
- [ ] Implement University Sympathy training:
  - [ ] Add Sympathy classroom
  - [ ] Master Elxa Dal NPC
  - [ ] `attend sympathy` - attend class (costs time, grants XP)
  - [ ] Special quests for advanced sympathy techniques
- [ ] Create sympathy skill data:
  - [ ] Update `data/config/skills.yaml`
  - [ ] Define sympathy rank benefits
  - [ ] Define learning curve
- [ ] Write tests:
  - [ ] `tests/test_systems/test_sympathy_progression.py`

#### Acceptance Criteria

- [ ] Players can designate heat sources
- [ ] Players can create sympathy bindings
- [ ] Binding efficiency calculated correctly (similarity, consanguinity, Alar)
- [ ] Bindings consume energy from heat source
- [ ] Players can use sympathy in combat
- [ ] Sympathetic damage bypasses armor
- [ ] Multiple simultaneous bindings work (limited by Alar)
- [ ] Backlash occurs on risky bindings
- [ ] Body heat use is dangerous and warns player
- [ ] Sympathy skill increases with use
- [ ] Alar strength increases with Sympathy skill and training
- [ ] University Sympathy classes available
- [ ] Master Elxa Dal teaches sympathy
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

### Phase 5: University System - 2 Weeks

**Goal:** Implement the University, Arcanum membership, admission system, and Masters.

**Deliverables:**
- Complete University campus (15+ rooms)
- The Nine Masters as NPCs
- Admission examination system
- Tuition calculation and payment
- Arcanum ranks (E'lir, Re'lar, El'the)
- University classes and training
- Jobs for income (scriv, medica assistant)
- The Archives (restricted access)

#### Implementation Checklist

**Week 9: University Infrastructure**

**Day 57-59: University World Building**
- [ ] Create University areas:
  - [ ] `data/world/areas/university.yaml`
  - [ ] The Mews (student housing, 5 rooms)
  - [ ] The Hollows (administration, admissions room)
  - [ ] Mains (lecture halls, classrooms, 4 rooms)
  - [ ] The Archives (library, 3 levels, restricted)
  - [ ] The Artificery (workshop, forge)
  - [ ] The Medica (hospital, alchemy lab)
  - [ ] The Rookery (Masters' offices)
  - [ ] Outdoor areas (quad, paths)
- [ ] Implement University NPCs:
  - [ ] `data/world/npcs/university.yaml`
  - [ ] The Nine Masters (detailed below)
  - [ ] Student NPCs (ambient, quest givers)
  - [ ] Staff NPCs (housing master, scriv supervisor)
- [ ] Implement room restrictions:
  - [ ] Archives level 2: Requires E'lir rank
  - [ ] Archives level 3: Requires Re'lar rank
  - [ ] Masters' offices: Requires invitation
  - [ ] Display access denied message
- [ ] Write tests:
  - [ ] `tests/test_game/test_university_world.py`

**Day 60-61: The Nine Masters**
- [ ] Implement Master NPCs:
  - [ ] Master Hemme (Geometry) - pompous, dislikes cleverness
  - [ ] Master Arwyl (Medica) - kind, practical
  - [ ] Master Mandrag (Alchemy) - gruff, direct
  - [ ] Master Kilvin (Artificery) - fair, values craftsmanship
  - [ ] Master Elxa Dal (Sympathy) - encouraging, theoretical
  - [ ] Master Brandeur (Rhetoric) - formal, traditional
  - [ ] Master Lorren (Archives) - strict, humorless
  - [ ] Master Elodin (Naming) - eccentric, unpredictable
  - [ ] Master Herma (History) - detail-oriented
- [ ] Implement Master reputation system:
  - [ ] `src/game/systems/university.py`
  - [ ] Track reputation with each Master (-100 to +100)
  - [ ] Reputation affects tuition
  - [ ] Reputation affects access to resources
  - [ ] Reputation changes based on actions
- [ ] Implement Master interactions:
  - [ ] Dialogue system for each Master
  - [ ] Quest offerings based on reputation
  - [ ] Teaching services
- [ ] Write tests:
  - [ ] `tests/test_game/test_masters.py`

**Day 62-63: Admission & Tuition System**
- [ ] Implement Arcanum membership:
  - [ ] Add `arcanum_rank` field to Character model
  - [ ] Ranks: None, E'lir, Re'lar, El'the
  - [ ] Track current term number
- [ ] Implement admission examination:
  - [ ] `src/game/systems/admission.py`
  - [ ] Scheduled every 2 real-world weeks (end of term)
  - [ ] Player enters Hollows during admission period
  - [ ] Quorum of 5+ Masters required
- [ ] Implement admission questions:
  - [ ] Question pool (50+ questions across disciplines)
  - [ ] Questions chosen based on character skills/history
  - [ ] Each Master asks 1-2 questions
  - [ ] Player has 60 seconds to answer each
  - [ ] Answers scored (excellent, good, adequate, poor)
- [ ] Implement tuition calculation:
  - [ ] Base tuition = Rank × 10 talents
  - [ ] Modifiers based on:
    - [ ] Answer quality (-50% to +200%)
    - [ ] Master reputations (±30% each)
    - [ ] Previous term performance (±20%)
    - [ ] Special circumstances (player-specific)
  - [ ] Minimum: 0 talents (free)
  - [ ] Maximum: Unlimited (rejection)
  - [ ] Negative tuition possible (University pays player)
- [ ] Implement tuition payment:
  - [ ] `pay tuition` command
  - [ ] Deduct from player money
  - [ ] Update Arcanum membership status
  - [ ] Grant term access
- [ ] Write tests:
  - [ ] `tests/test_systems/test_admission.py`
  - [ ] `tests/test_systems/test_tuition.py`

**Week 10: Classes, Jobs & Archives**

**Day 64-66: University Classes**
- [ ] Implement class attendance system:
  - [ ] `attend <class>` command
  - [ ] Class schedule (specific times/days)
  - [ ] Requires enrollment (paid tuition)
  - [ ] Takes 1 hour game time
- [ ] Implement available classes:
  - [ ] Sympathy (Master Elxa Dal) - Sympathy skill XP
  - [ ] Artificery (Master Kilvin) - Artificery skill XP
  - [ ] Alchemy (Master Mandrag) - Alchemy skill XP
  - [ ] Medica (Master Arwyl) - Medicine skill XP
  - [ ] Rhetoric (Master Brandeur) - Charisma boost
  - [ ] History (Master Herma) - Lore skill XP
- [ ] Implement class benefits:
  - [ ] Grant skill XP (50-100 per class)
  - [ ] Improve Master reputation (+5 per class)
  - [ ] Unlock advanced lessons at high reputation
- [ ] Implement advanced training:
  - [ ] One-on-one sessions with Masters
  - [ ] Requires high reputation (+50+)
  - [ ] Costs money (5-10 talents)
  - [ ] Grants double XP
- [ ] Write tests:
  - [ ] `tests/test_systems/test_classes.py`

**Day 67-68: University Jobs**
- [ ] Implement scriv (scribe) job:
  - [ ] `work scriv` command
  - [ ] Available in Archives
  - [ ] Requires Archives access
  - [ ] Takes 2 hours game time
  - [ ] Pays 2-5 jots per shift
  - [ ] Small Lore XP bonus
- [ ] Implement Medica assistant job:
  - [ ] `work medica` command
  - [ ] Available in Medica
  - [ ] Takes 4 hours game time
  - [ ] Pays 1 talent per shift
  - [ ] Medicine XP bonus
  - [ ] Improves Arwyl reputation
- [ ] Implement Artificery work:
  - [ ] `work artificery` command
  - [ ] Requires Artificery skill 20+
  - [ ] Takes variable time (complete project)
  - [ ] Pays 3-10 talents per project
  - [ ] Artificery XP bonus
  - [ ] Improves Kilvin reputation
- [ ] Implement job cooldowns:
  - [ ] Can only work once per 24 hours (real-time)
  - [ ] Prevents job grinding
- [ ] Write tests:
  - [ ] `tests/test_systems/test_university_jobs.py`

**Day 69-70: The Archives**
- [ ] Implement Archives system:
  - [ ] `src/game/systems/archives.py`
  - [ ] Archives access levels (0, 1, 2, 3)
  - [ ] Access level based on Arcanum rank
  - [ ] Master Lorren enforces rules
- [ ] Implement Archives rules:
  - [ ] No fires (candles banned)
  - [ ] No food/drink
  - [ ] Silence required
  - [ ] Violation = banned + Lorren reputation loss
- [ ] Implement book research:
  - [ ] `research <topic>` command
  - [ ] Search Archives for information
  - [ ] Success based on Lore skill
  - [ ] Grants lore snippets (quest clues)
  - [ ] Takes time (30-60 minutes game time)
- [ ] Implement restricted books:
  - [ ] Level 2: Advanced magic, dangerous knowledge
  - [ ] Level 3: Chandrian lore, Naming secrets
  - [ ] Require specific access level
  - [ ] Some require Master permission
- [ ] Create Archives book database:
  - [ ] `data/world/archives_books.yaml`
  - [ ] 50+ book entries
  - [ ] Topics: History, Magic, Fae, Chandrian, etc.
  - [ ] Access level restrictions
- [ ] Write tests:
  - [ ] `tests/test_systems/test_archives.py`

#### Acceptance Criteria

- [ ] University campus fully explorable (15+ rooms)
- [ ] All Nine Masters exist as NPCs with dialogue
- [ ] Master reputation system tracks relationships
- [ ] Admission exams occur every 2 weeks
- [ ] Players answer questions from Masters
- [ ] Tuition calculated based on performance and reputation
- [ ] Players can pay tuition to gain Arcanum membership
- [ ] Arcanum ranks grant access to restricted areas
- [ ] Players can attend classes to gain skill XP
- [ ] Classes improve Master reputations
- [ ] Players can work jobs for income (scriv, medica, artificery)
- [ ] Jobs grant money and skill XP
- [ ] Archives accessible with restrictions by level
- [ ] Research command provides lore information
- [ ] Master Lorren enforces Archives rules
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

### Phase 6: Economy & Crafting - 1-2 Weeks

**Goal:** Implement full economy, currency, shops, trading, and basic crafting.

**Deliverables:**
- Cealdish currency system
- Merchant shops with dynamic inventory
- Player trading
- Alchemy crafting system
- Artificery crafting system
- Money sinks (taxes, repairs, tuition)

#### Implementation Checklist

**Week 11: Economy**

**Day 71-72: Currency & Wealth**
- [ ] Implement currency system:
  - [ ] `src/game/systems/economy.py`
  - [ ] Currency class (convert between drabs, jots, talents, marks)
  - [ ] Display formatting (automatic conversion)
- [ ] Update Character money field:
  - [ ] Store in smallest denomination (drabs)
  - [ ] Add `add_money()` and `remove_money()` methods
  - [ ] Transaction logging
- [ ] Implement money commands:
  - [ ] `wealth` or `worth` - show total money
  - [ ] `give <amount> <player>` - transfer money
  - [ ] Automatic conversion display (e.g., "You have 3 talents, 4 jots, and 2 drabs")
- [ ] Write tests:
  - [ ] `tests/test_systems/test_currency.py`

**Day 73-75: Shops & Merchants**
- [ ] Implement merchant system:
  - [ ] Update `src/game/systems/merchant.py` (from Phase 3)
  - [ ] Dynamic inventory refresh (daily)
  - [ ] Stock limits (items sell out)
  - [ ] Price fluctuation (supply/demand)
- [ ] Implement merchant commands:
  - [ ] `list` - show available items
  - [ ] `buy <item> [quantity]` - purchase items
  - [ ] `sell <item> [quantity]` - sell items
  - [ ] `appraise <item>` - check sell value
  - [ ] `barter <item>` - negotiate price (Mercantile check)
- [ ] Implement price calculation:
  - [ ] Base price from item template
  - [ ] Mercantile skill modifier: 0-30% discount
  - [ ] Merchant reputation modifier: 0-20% discount
  - [ ] Supply/demand modifier: ±20%
  - [ ] Item condition: 50-100% value
- [ ] Create merchant NPCs:
  - [ ] General Store (Imre) - food, basic supplies
  - [ ] Weapon Smith (Imre) - weapons, armor
  - [ ] Apothecary (Imre) - alchemy ingredients
  - [ ] Kilvin's Workshop (University) - magical items
  - [ ] Black Market (hidden) - illegal items, stolen goods
- [ ] Implement merchant inventory data:
  - [ ] `data/world/merchants/general_store.yaml`
  - [ ] `data/world/merchants/weapon_smith.yaml`
  - [ ] etc.
- [ ] Write tests:
  - [ ] `tests/test_systems/test_merchant_enhanced.py`

**Day 76-77: Player Trading**
- [ ] Implement player-to-player trading:
  - [ ] `trade <player>` - initiate trade
  - [ ] Trade window/interface (text-based)
  - [ ] Add items and money to trade
  - [ ] Both players must accept
  - [ ] Atomic transaction (all or nothing)
- [ ] Implement trade commands:
  - [ ] `trade <player>` - start trade
  - [ ] `offer <item> [quantity]` - add item to trade
  - [ ] `offer <amount> money` - add money to trade
  - [ ] `remove <item>` - remove from trade
  - [ ] `accept` - accept current trade terms
  - [ ] `cancel` - cancel trade
- [ ] Implement trade safety:
  - [ ] Prevent trade scams
  - [ ] Validate both players have items/money
  - [ ] Log all trades for audit
- [ ] Write tests:
  - [ ] `tests/test_systems/test_trading.py`

**Week 12: Crafting**

**Day 78-80: Alchemy Crafting**
- [ ] Implement alchemy system:
  - [ ] `src/game/systems/magic/alchemy.py`
  - [ ] Recipe database
  - [ ] Ingredient requirements
  - [ ] Success chance calculation
- [ ] Implement alchemy recipes:
  - [ ] `data/config/alchemy_recipes.yaml`
  - [ ] Healing Potion (restore 50 HP)
  - [ ] Nahlrout (rage potion, +5 STR, -2 INT)
  - [ ] Regim (sleeplessness, +2 focus)
  - [ ] Plum Bob (poison, 30 damage)
  - [ ] Antidote (cure poison)
  - [ ] 10+ total recipes
- [ ] Implement alchemy crafting:
  - [ ] `craft alchemy <recipe>` command
  - [ ] Requires Alchemy skill level
  - [ ] Requires ingredients in inventory
  - [ ] Requires alembic (tool) or Medica access
  - [ ] Success chance based on skill
  - [ ] On success: create item, grant XP
  - [ ] On failure: waste ingredients, small XP
- [ ] Implement ingredient sourcing:
  - [ ] Buy from Apothecary
  - [ ] Forage in wilderness (future)
  - [ ] Quest rewards
- [ ] Write tests:
  - [ ] `tests/test_systems/test_alchemy_crafting.py`

**Day 81-82: Artificery Crafting**
- [ ] Implement artificery system:
  - [ ] `src/game/systems/magic/sygaldry.py`
  - [ ] Sygaldric device blueprints
  - [ ] Material requirements
  - [ ] Success chance and quality tiers
- [ ] Implement sygaldry blueprints:
  - [ ] `data/config/sygaldry_blueprints.yaml`
  - [ ] Sympathy Lamp (ever-burning light)
  - [ ] Gram (arrow deflection ward)
  - [ ] Heat Funnel (warmth attraction)
  - [ ] Dowsing Compass (direction finder)
  - [ ] 5+ total blueprints
- [ ] Implement artificery crafting:
  - [ ] `craft artificery <blueprint>` command
  - [ ] Requires Artificery skill level
  - [ ] Requires materials and tools
  - [ ] Requires Artificery workshop access
  - [ ] Takes time (1-4 hours game time)
  - [ ] Quality based on skill (poor, standard, masterwork)
- [ ] Implement sygaldric item properties:
  - [ ] Items have charges or continuous effects
  - [ ] Masterwork items have enhanced effects
  - [ ] Can sell to Kilvin or other players
- [ ] Write tests:
  - [ ] `tests/test_systems/test_artificery_crafting.py`

**Day 83-84: Money Sinks & Economy Balance**
- [ ] Implement money sinks:
  - [ ] University tuition (1-15 talents per term)
  - [ ] Equipment repairs (weapons/armor degrade)
  - [ ] Property rent (if player rents room)
  - [ ] Bribes for information
  - [ ] Gambling (future)
- [ ] Implement equipment degradation:
  - [ ] Items have durability
  - [ ] Durability decreases with use (combat, crafting)
  - [ ] Broken items provide reduced bonuses
  - [ ] Repair at blacksmith (costs money)
- [ ] Implement repair system:
  - [ ] `repair <item>` at blacksmith
  - [ ] Cost based on item value and damage
  - [ ] Fully restore durability
- [ ] Balance economy:
  - [ ] Playtest income vs expenses
  - [ ] Adjust quest rewards
  - [ ] Adjust merchant prices
  - [ ] Adjust job payouts
  - [ ] Goal: Player can afford tuition + basics without grinding
- [ ] Write tests:
  - [ ] `tests/test_systems/test_economy_balance.py`

#### Acceptance Criteria

- [ ] Currency displays correctly (auto-conversion)
- [ ] Players can transfer money to each other
- [ ] Merchant shops have dynamic inventory
- [ ] Players can buy and sell items
- [ ] Prices affected by Mercantile skill, reputation, supply/demand
- [ ] Multiple merchants exist with different inventories
- [ ] Player-to-player trading works safely
- [ ] Trade interface prevents scams
- [ ] Alchemy crafting works with recipes
- [ ] Alchemy success based on skill, ingredients, tools
- [ ] Artificery crafting creates sygaldric items
- [ ] Crafted items have quality tiers
- [ ] Money sinks exist (tuition, repairs, etc.)
- [ ] Equipment degrades and can be repaired
- [ ] Economy is balanced (income vs expenses)
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

### Phase 7: Advanced Features - 1-2 Weeks

**Goal:** Implement advanced magic (Naming), factions, quests, and polish.

**Deliverables:**
- Naming magic system
- Faction system (Chandrian, Amyr, Edema Ruh)
- Quest system with branching narratives
- Achievement system
- Admin tools
- Performance optimizations
- Final polish and bug fixes

#### Implementation Checklist

**Week 13: Advanced Magic & Factions**

**Day 85-86: Naming Magic**
- [ ] Implement Naming system:
  - [ ] `src/game/systems/magic/naming.py`
  - [ ] Known Names: Wind, Fire, Stone, Water, Iron, Wood
  - [ ] Name learning (quest-locked, rare)
  - [ ] Calling vs Speaking mechanics
- [ ] Implement Name learning quests:
  - [ ] "The Wind's Name" (Master Elodin quest chain)
  - [ ] Requires Re'lar rank minimum
  - [ ] Difficult trials and meditation
  - [ ] One-time permanent unlock
- [ ] Implement Name usage:
  - [ ] `call <name>` - instinctive, unreliable (stress-triggered)
  - [ ] `speak <name>` - deliberate, controlled
  - [ ] Effects based on Name (see PRD for details)
  - [ ] Energy cost (high)
  - [ ] Cooldown period (5-15 minutes)
- [ ] Implement Name risks:
  - [ ] Chance of failure on Speaking (decreases with practice)
  - [ ] Risk of madness (low chance, catastrophic)
  - [ ] Sleeping mind mechanics (spontaneous Calling)
- [ ] Implement Name progression:
  - [ ] Mastery increases with use
  - [ ] Failure chance decreases
  - [ ] Effect power increases
  - [ ] Cooldown reduces
- [ ] Write tests:
  - [ ] `tests/test_systems/test_naming.py`

**Day 87-89: Faction System**
- [ ] Implement faction framework:
  - [ ] `src/game/systems/faction.py`
  - [ ] Faction class (name, reputation, ranks)
  - [ ] Reputation tracking (-100 to +100)
  - [ ] Faction membership and ranks
- [ ] Implement factions:
  - [ ] **Chandrian** (hidden, dangerous)
    - [ ] Reputation affects random encounters
    - [ ] Negative rep = hunted by Chandrian
    - [ ] Positive rep = may receive cryptic aid (very rare)
  - [ ] **Amyr** (secret, not openly joinable)
    - [ ] Unlocked by special quest chain
    - [ ] Reputation based on "greater good" actions
    - [ ] High rep grants access to hidden caches
  - [ ] **Edema Ruh** (cultural faction)
    - [ ] Join during character creation (background)
    - [ ] Reputation with all Ruh NPCs
    - [ ] Special performance abilities
  - [ ] **University** (already implemented as Masters' reputation)
  - [ ] **Tehlin Church** (religious faction)
- [ ] Implement faction actions:
  - [ ] Actions affect faction reputation
  - [ ] Helping faction members: +5 to +20
  - [ ] Harming faction members: -10 to -50
  - [ ] Completing faction quests: +20 to +100
- [ ] Implement faction benefits:
  - [ ] Access to faction-specific NPCs
  - [ ] Discounts from faction merchants
  - [ ] Faction-specific items and equipment
  - [ ] Special abilities (Ruh performance bonuses, etc.)
- [ ] Write tests:
  - [ ] `tests/test_systems/test_factions.py`

**Day 90-91: Quest System Enhancement**
- [ ] Implement quest framework:
  - [ ] Update `src/game/systems/quest.py`
  - [ ] Branching narratives (choice-based outcomes)
  - [ ] Quest chains (multi-part stories)
  - [ ] Faction-specific quests
- [ ] Implement quest types:
  - [ ] Linear quests (simple A→B→C)
  - [ ] Branching quests (player choices affect outcome)
  - [ ] Repeatable quests (dailies/weeklies)
  - [ ] Hidden quests (discovered through exploration/dialogue)
- [ ] Create major quest chains:
  - [ ] "The Chandrian Mystery" (investigate Chandrian, 5+ parts)
  - [ ] "Elodin's Trials" (learn Naming, 4 parts)
  - [ ] "The Draccus of Trebon" (combat/investigation, 3 parts)
  - [ ] "Ambrose's Schemes" (social intrigue, branching)
  - [ ] 10+ total major quests
- [ ] Implement quest tracking UI:
  - [ ] `quest log` - show all quests
  - [ ] `quest details <quest>` - show objectives and progress
  - [ ] `quest abandon <quest>` - drop quest (confirmation required)
- [ ] Implement quest rewards variety:
  - [ ] XP and money (standard)
  - [ ] Unique items (quest-locked)
  - [ ] Faction reputation
  - [ ] Unlock new areas/NPCs
  - [ ] Learn secrets (lore entries)
- [ ] Write tests:
  - [ ] `tests/test_systems/test_quest_enhanced.py`

**Week 14: Polish & Optimization**

**Day 92-93: Achievement System**
- [ ] Implement achievement framework:
  - [ ] `src/game/systems/achievements.py`
  - [ ] Achievement definitions
  - [ ] Progress tracking
  - [ ] Unlock notifications
- [ ] Create achievements:
  - [ ] **Exploration**: Visit all University buildings
  - [ ] **Combat**: Defeat 100 enemies
  - [ ] **Magic**: Cast 1000 sympathy bindings
  - [ ] **Wealth**: Accumulate 100 talents
  - [ ] **Academic**: Achieve El'the rank
  - [ ] **Social**: Befriend all Nine Masters (+50 rep with each)
  - [ ] **Secrets**: Discover all hidden rooms
  - [ ] **Legendary**: Learn a Name
  - [ ] 20+ total achievements
- [ ] Implement achievement commands:
  - [ ] `achievements` - show all achievements
  - [ ] `achievement <name>` - show progress on specific achievement
- [ ] Implement achievement rewards:
  - [ ] Titles (displayed with player name)
  - [ ] Cosmetic items (cloaks, badges)
  - [ ] Small stat bonuses
- [ ] Write tests:
  - [ ] `tests/test_systems/test_achievements.py`

**Day 94-95: Admin Tools**
- [ ] Implement admin commands:
  - [ ] `src/game/commands/admin.py`
  - [ ] Require `is_admin` flag on user
- [ ] Create admin commands:
  - [ ] `admin tp <location>` - teleport to any room
  - [ ] `admin summon <player>` - teleport player to you
  - [ ] `admin goto <player>` - teleport to player
  - [ ] `admin give <player> <item> [quantity]` - give items
  - [ ] `admin money <player> <amount>` - adjust money
  - [ ] `admin level <player> <level>` - set level
  - [ ] `admin spawn <npc>` - spawn NPC in room
  - [ ] `admin despawn <npc>` - remove NPC
  - [ ] `admin broadcast <message>` - global announcement
  - [ ] `admin shutdown [minutes]` - schedule server shutdown
  - [ ] `admin kick <player>` - disconnect player
  - [ ] `admin ban <player>` - ban account
- [ ] Implement admin logging:
  - [ ] Log all admin actions to database
  - [ ] Audit trail for accountability
- [ ] Write tests:
  - [ ] `tests/test_commands/test_admin.py`

**Day 96-97: Performance Optimization**
- [ ] Optimize database queries:
  - [ ] Add indexes on frequently queried fields
  - [ ] Use eager loading for relationships
  - [ ] Batch updates where possible
- [ ] Optimize game loop:
  - [ ] Profile tick processing
  - [ ] Reduce unnecessary calculations
  - [ ] Cache frequently accessed data (room descriptions, etc.)
- [ ] Implement Redis caching:
  - [ ] Cache room data
  - [ ] Cache NPC templates
  - [ ] Cache item templates
  - [ ] Cache with TTL (invalidate on updates)
- [ ] Optimize network layer:
  - [ ] Buffer outgoing messages
  - [ ] Reduce redundant sends
  - [ ] Compress large messages
- [ ] Load testing:
  - [ ] Simulate 100 concurrent users
  - [ ] Measure response times
  - [ ] Identify bottlenecks
  - [ ] Optimize hot paths
- [ ] Write performance tests:
  - [ ] `tests/test_performance/test_load.py`

**Day 98: Final Polish**
- [ ] Bug fixes:
  - [ ] Review GitHub issues
  - [ ] Fix critical bugs
  - [ ] Fix high-priority bugs
- [ ] UX improvements:
  - [ ] Better error messages
  - [ ] Help command improvements
  - [ ] Tutorial quest for new players
  - [ ] Newbie tips
- [ ] Content additions:
  - [ ] Add more room descriptions
  - [ ] Add more NPC dialogue
  - [ ] Add more items
  - [ ] Add more quests
- [ ] Documentation:
  - [ ] Update all docs with final features
  - [ ] Create player guide
  - [ ] Create world lore document
  - [ ] Update README.md with current state

#### Acceptance Criteria

- [ ] Naming magic system works with quests to learn Names
- [ ] Players can Speak or Call Names
- [ ] Name effects apply correctly
- [ ] Naming has risks (madness, failure)
- [ ] Faction system tracks reputation
- [ ] Multiple factions exist (Chandrian, Amyr, Ruh, Church)
- [ ] Faction actions affect reputation
- [ ] Faction benefits apply based on reputation
- [ ] Quest system supports branching narratives
- [ ] Major quest chains implemented (5+ quests)
- [ ] Quest rewards are varied and meaningful
- [ ] Achievement system tracks progress
- [ ] 20+ achievements available
- [ ] Achievement rewards granted
- [ ] Admin tools functional and secure
- [ ] Admin actions logged
- [ ] Performance optimized (response time <100ms)
- [ ] Database queries optimized with indexes
- [ ] Redis caching implemented
- [ ] Load testing shows stable performance at 100 users
- [ ] All critical bugs fixed
- [ ] Documentation complete and accurate
- [ ] Test coverage ≥80%
- [ ] CI pipeline passes

---

## Risk Assessment & Mitigation

### Technical Risks

**Risk: Database Performance Degradation**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Implement database indexes on frequently queried fields from Phase 1
  - Use Redis caching for hot data (rooms, NPCs, items)
  - Monitor query performance with slow query logs
  - Plan for database sharding if player base exceeds 1000 concurrent users
  - Regular VACUUM and ANALYZE on PostgreSQL

**Risk: Network Layer Failures (Connection Drops)**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  - Implement robust reconnection handling
  - Auto-save character state every 5 minutes
  - Session persistence in Redis (survive server restarts)
  - Heartbeat/keepalive packets to detect dead connections
  - Graceful degradation (player marked "link-dead" but not kicked for 5 minutes)

**Risk: Race Conditions in Combat/Trading**
- **Likelihood:** Medium
- **Impact:** High (item duplication, money duplication)
- **Mitigation:**
  - Use database transactions for all critical operations
  - Implement optimistic locking on character/item updates
  - Comprehensive integration tests for concurrent operations
  - Code review focus on atomic operations
  - Use Redis locks for distributed operations if scaling horizontally

**Risk: Security Vulnerabilities (SQL Injection, XSS)**
- **Likelihood:** Low (using ORM)
- **Impact:** Critical
- **Mitigation:**
  - Use SQLAlchemy ORM exclusively (no raw SQL)
  - Input sanitization on all player commands
  - Parameterized queries even in raw SQL (if needed)
  - Regular security audits via GitHub Dependabot
  - Penetration testing before public launch
  - Rate limiting to prevent abuse

**Risk: Python Performance Limitations**
- **Likelihood:** Medium (at scale)
- **Impact:** Medium
- **Mitigation:**
  - Use asyncio efficiently (non-blocking operations)
  - Profile code regularly to identify bottlenecks
  - Consider PyPy for production (JIT compilation)
  - Offload heavy computation to background tasks (Celery if needed)
  - Plan for horizontal scaling (multiple app servers behind load balancer)

### Content Risks

**Risk: Kingkiller Chronicle IP Infringement**
- **Likelihood:** Low (fan project, non-commercial)
- **Impact:** Critical (cease and desist, shutdown)
- **Mitigation:**
  - Clearly label as fan-made, non-commercial project
  - Do not monetize game directly
  - Include disclaimer on login screen
  - Respect copyright: no direct book quotes, no official art
  - Be prepared to shut down if requested by author/publisher
  - Consider reaching out to Patrick Rothfuss for blessing (optional)

**Risk: Lore Inconsistencies with Canon**
- **Likelihood:** Medium
- **Impact:** Low (fan disappointment)
- **Mitigation:**
  - Designate "lore master" on team (content designer)
  - Reference wiki and books frequently
  - Mark non-canon content as "MUD-specific" in lore
  - Accept community feedback on lore issues
  - Iterate and fix inconsistencies in patches

**Risk: Unbalanced Game Economy**
- **Likelihood:** High
- **Impact:** Medium (player frustration, inflation)
- **Mitigation:**
  - Extensive playtesting in Phase 6
  - Monitor player wealth distribution
  - Implement money sinks (tuition, repairs, taxes)
  - Adjust quest rewards and job payouts dynamically
  - Admin tools to manually adjust economy if needed

**Risk: Insufficient Content at Launch**
- **Likelihood:** Medium
- **Impact:** Medium (player churn, boredom)
- **Mitigation:**
  - Prioritize depth over breadth (make University really good)
  - Implement repeatable systems (quests, jobs, crafting)
  - Launch with 50+ quests minimum
  - Plan content roadmap for post-launch updates
  - Engage community for content suggestions

### Operational Risks

**Risk: Server Downtime**
- **Likelihood:** Medium
- **Impact:** High (player frustration, data loss)
- **Mitigation:**
  - Automated backups (daily full, hourly incremental)
  - Database replication (if budget allows)
  - Health checks and auto-restart (Docker/systemd)
  - Monitoring and alerting (UptimeRobot, PagerDuty free tier)
  - Graceful shutdown handling (save all state before stopping)
  - Status page for communication (status.waystone-mud.com)

**Risk: Team Member Unavailability**
- **Likelihood:** Medium (small team)
- **Impact:** Medium (delays)
- **Mitigation:**
  - Comprehensive documentation (code, architecture, processes)
  - Code reviews (knowledge sharing)
  - Modular architecture (easy for new devs to understand)
  - GitHub project board (clear task tracking)
  - Cross-training (everyone knows basics of each system)

**Risk: Scope Creep**
- **Likelihood:** High
- **Impact:** High (delays, feature bloat)
- **Mitigation:**
  - Strict adherence to phased implementation plan
  - "Phase 8" backlog for nice-to-have features
  - Regular scope review meetings
  - Clear MVP definition (Phase 1-3)
  - Feature freeze before launch
  - Post-launch content updates (not pre-launch)

**Risk: Insufficient Budget for Hosting**
- **Likelihood:** Low (modest costs)
- **Impact:** Medium (shutdown)
- **Mitigation:**
  - Start with low-cost VPS ($30-40/month)
  - Scale only when necessary
  - Monitor costs monthly
  - Consider donations (Patreon, Ko-fi) if community wants to support
  - Have 3-6 months hosting budget in reserve

---

## Appendices

### Appendix F: Budget Mode Setup Guide ($0/month)

This appendix provides step-by-step instructions for running Waystone MUD at zero cost.

#### Local Development (MacBook/Linux)

**Prerequisites:**
```bash
# Install Python 3.12+ via brew (macOS)
brew install python@3.12

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Quick Start:**
```bash
# Clone and setup
git clone https://github.com/yourusername/waystone-mud.git
cd waystone-mud
uv sync

# Run the server
uv run python -m waystone.server

# Connect (in another terminal)
telnet localhost 4000
```

**Database:** SQLite file at `./data/waystone.db` (auto-created)
**Sessions:** In-memory Python dict (no Redis needed)

#### Oracle Cloud Free Tier Deployment

**Step 1: Create Oracle Cloud Account**
1. Go to https://cloud.oracle.com/
2. Sign up for free tier (requires credit card for verification, never charged)
3. Select home region closest to your players

**Step 2: Create ARM VM (Recommended)**
```
Shape: VM.Standard.A1.Flex
OCPUs: 2 (free tier allows up to 4)
RAM: 12GB (free tier allows up to 24GB)
Boot Volume: 50GB
OS: Ubuntu 22.04 or Oracle Linux 8
```

**Step 3: Configure Firewall (Ingress Rules)**
```
Port 22   - SSH
Port 4000 - Telnet (MUD)
Port 4001 - WebSocket (optional)
```

**Step 4: Deploy Application**
```bash
# SSH into your VM
ssh -i your-key.pem ubuntu@<your-vm-ip>

# Install dependencies
sudo apt update && sudo apt install -y python3.12 python3.12-venv git

# Clone and setup
git clone https://github.com/yourusername/waystone-mud.git
cd waystone-mud
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .

# Create systemd service for auto-restart
sudo tee /etc/systemd/system/waystone.service << EOF
[Unit]
Description=Waystone MUD Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/waystone-mud
ExecStart=/home/ubuntu/waystone-mud/.venv/bin/python -m waystone.server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl enable waystone
sudo systemctl start waystone
```

**Step 5: Connect and Play**
```bash
telnet <your-vm-ip> 4000
```

#### Cost Comparison

| Setup | Monthly Cost | Max Concurrent Users | Notes |
|-------|-------------|---------------------|-------|
| Local Dev (MacBook) | $0 | N/A | Development only |
| Oracle Free Tier (AMD) | $0 | ~30-50 | 1GB RAM limit |
| Oracle Free Tier (ARM) | $0 | ~100+ | 12-24GB RAM, recommended |
| Fly.io Free | $0 | ~20 | Low memory |
| DigitalOcean | $6/mo | ~50 | If you need more control |
| Full Production | $50-100/mo | 500+ | PostgreSQL + Redis + LB |

#### Upgrading from Budget to Scale Mode

When you outgrow SQLite (rare for MUDs, but possible):

1. **Export data:** `uv run python -m waystone.tools.export_to_postgres`
2. **Update config:** Change `DATABASE_URL` in `.env`
3. **Migrate:** SQLAlchemy handles schema compatibility

The codebase is designed so this is a config change, not a code change.

---

### Appendix A: Command Reference

**Movement:**
- `north`, `south`, `east`, `west`, `up`, `down`
- `look` - View current room
- `exits` - Show available exits

**Communication:**
- `say <message>` - Local chat
- `emote <action>` - Roleplay action
- `chat <message>` - Global OOC channel
- `tell <player> <message>` - Private message
- `reply <message>` - Reply to last tell

**Character:**
- `stats` - Character sheet
- `attributes` - Detailed attributes
- `skills` - Skill list
- `inventory` or `i` - Show inventory
- `equipment` or `eq` - Show equipped items
- `score` - Quick summary
- `save` - Manual save

**Items:**
- `get <item>` - Pick up item
- `drop <item>` - Drop item
- `give <item> <player>` - Give item
- `equip <item>` - Equip item
- `unequip <slot>` - Unequip item
- `use <item>` - Use consumable

**Combat:**
- `attack <target>` - Initiate combat
- `defend` - Defensive stance
- `flee` - Attempt escape
- `kill <target>` - Alias for attack

**Magic:**
- `bind <source> <target> <type>` - Create sympathy binding
- `release` - End binding
- `bindings` - Show active bindings
- `cast <spell>` - Cast spell
- `speak <name>` - Speak a Name (Naming magic)

**University:**
- `attend <class>` - Attend class
- `work <job>` - Work a job
- `research <topic>` - Research in Archives
- `pay tuition` - Pay tuition

**Economy:**
- `wealth` - Show money
- `list` - Show merchant inventory (when at merchant)
- `buy <item>` - Purchase item
- `sell <item>` - Sell item
- `trade <player>` - Initiate trade
- `craft <type> <recipe>` - Craft item

**Social:**
- `who` - Show online players
- `friend add <player>` - Add friend
- `friend list` - Show friends
- `ignore <player>` - Ignore player

**Quests:**
- `quest log` - Show quests
- `quest info <quest>` - Quest details
- `quest abandon <quest>` - Drop quest

**Admin (Admin Only):**
- `admin tp <location>` - Teleport
- `admin summon <player>` - Summon player
- `admin give <player> <item>` - Give item
- `admin broadcast <message>` - Global announcement
- `admin shutdown` - Shutdown server

### Appendix B: Glossary

**Alar:** Mental strength, required for sympathy magic. Based on INT + WIS.

**Arcanum:** The elite magical school within the University.

**Binding:** A sympathetic connection between two objects that allows energy transfer.

**Chandrian:** Group of seven mysterious antagonists who erase knowledge of themselves.

**Consanguinity:** The principle that objects once connected maintain stronger sympathetic links.

**Drabs, Jots, Talents, Marks:** Cealdish currency denominations.

**E'lir, Re'lar, El'the:** Ranks within the Arcanum (Seer, Speaker, Guild Member).

**Four Corners:** The civilized world (Commonwealth, Vintas, Ceald, Modeg).

**Gilthe (Guilder):** Token of full arcanist status (El'the rank).

**Lethani:** Adem philosophical concept of right action.

**Naming:** Magic of knowing the true names of things, granting control over them.

**Scriv:** Student scribe job at the University.

**Slippage:** Energy loss in sympathetic bindings (inefficiency).

**Sympathy:** Magic system based on creating connections (bindings) between objects.

**Sygaldry:** Rune-based magic inscribed on objects for permanent effects.

**The University:** Premier school of magic and learning in the Commonwealth.

**Temerant:** The world where the Kingkiller Chronicle takes place.

### Appendix C: File Structure Quick Reference

See "Technical Stack & Infrastructure → Project Structure" for full details.

**Key Directories:**
- `src/` - All application code
- `tests/` - All tests
- `data/` - World data, configs (YAML files)
- `scripts/` - Utility scripts (setup, admin tools)
- `docs/` - Documentation
- `.github/workflows/` - CI/CD pipelines

### Appendix D: Resources & References

**Kingkiller Chronicle Wiki:**
- https://kingkiller.fandom.com/

**MUD Development Resources:**
- Evennia MUD framework: https://www.evennia.com/
- MUD Connector (inspiration): https://www.mudconnect.com/

**Python Libraries:**
- telnetlib3 docs: https://telnetlib3.readthedocs.io/
- websockets docs: https://websockets.readthedocs.io/
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- Redis-py docs: https://redis-py.readthedocs.io/

**Testing:**
- pytest docs: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/

**Deployment:**
- Docker docs: https://docs.docker.com/
- GitHub Actions docs: https://docs.github.com/en/actions

### Appendix E: Future Enhancements (Phase 8+)

**Not in initial scope, but planned for future:**

1. **WebSocket/Web Client:** Browser-based interface with rich UI
2. **Mobile App:** Native iOS/Android client
3. **Fae Realm:** Entire Fae world with different magic rules
4. **Advanced Alchemy:** Transmutation, custom potions
5. **Player Housing:** Rentable rooms, decoration, storage
6. **Guilds/Clans:** Player-run organizations
7. **PvP Arena:** Structured player-vs-player combat
8. **Wilderness Expansion:** Eld forest, Ademre mountains, Small Kingdoms
9. **Advanced Naming:** More Names, deeper mechanics
10. **Seasonal Events:** Holiday events, limited-time content
11. **Modding API:** Allow community content creation
12. **Voice Chat Integration:** Optional voice communication
13. **Graphics Overlay:** Optional graphical map/stats (MUD client enhancement)
14. **Story Continuation:** Original narrative beyond the books (careful with canon)
15. **Permadeath Server:** Hardcore mode server

---

## Conclusion

This PRD provides a comprehensive roadmap for building Waystone MUD, a text-based Multi-User Dungeon set in Patrick Rothfuss's Kingkiller Chronicle universe. The 7-phase implementation plan breaks down 10-14 weeks of development into manageable, testable increments, each delivering a working, playable build.

**Key Success Factors:**
1. **Faithful Adaptation:** Respect the source material while creating engaging gameplay
2. **Solid Technical Foundation:** Python + PostgreSQL + Redis provides scalability and reliability
3. **Incremental Delivery:** Each phase adds value and can be playtested
4. **Comprehensive Testing:** 80%+ code coverage ensures stability
5. **Community Engagement:** Listen to players and iterate based on feedback

**Next Steps:**
1. Review and approve this PRD
2. Set up development environment (Phase 1, Day 1-2)
3. Begin implementation following the detailed checklists
4. Regular check-ins to assess progress and adjust timeline
5. Prepare for alpha testing after Phase 3 (basic gameplay complete)

This MUD has the potential to become a beloved community gathering place for Kingkiller Chronicle fans, offering an immersive text-based experience that honors the rich world Patrick Rothfuss created while providing engaging multiplayer gameplay.

---

**Document End**

*For questions, clarifications, or change requests, please contact the engineering team.*