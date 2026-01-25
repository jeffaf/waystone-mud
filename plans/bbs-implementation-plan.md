# BBS Implementation Plan - Waystone MUD
## Kingkiller Chronicle Bulletin Board System

**Created:** January 25, 2026
**Reference Documents:**
- `/Users/jeffaf/code/waystone/docs/BBS_RESEARCH_REPORT.md` - Vintage BBS research
- `/Users/jeffaf/code/waystone/docs/BBS_ARCHITECTURE.md` - System architecture

---

## Overview

Implement a vintage BBS-style bulletin board system for the Waystone MUD, featuring:
- Physical boards in specific locations (University, Eolian, Marketplace)
- NPC posts from Elodin, Ambrose, Kilvin, Lorren, and Simmon
- ANSI-style formatting adapted for MUD display
- Access control based on Arcanum rank and character attributes
- Read tracking for "new message" detection

---

## Phase 1: Database Foundation (Days 1-2)

### Goal
Create database models and migration for bulletin boards, messages, and read tracking.

### Tasks

#### 1.1 Create Database Models
**File:** `src/waystone/database/models/bulletin.py`

- [ ] Create `BoardAccessLevel` enum (PUBLIC, STUDENT, ADVANCED, MASTER, PRIVATE)
- [ ] Create `BulletinBoard` model with:
  - `id` (string primary key)
  - `name`, `description`
  - `room_id` (foreign key to rooms)
  - `read_level`, `post_level` (access control)
  - `max_messages`, `allow_anonymous`, `is_active`
  - `attribute_requirement` (optional JSON for CHA/INT requirements)
  - `messages` relationship
- [ ] Create `BoardMessage` model with:
  - `id` (UUID primary key)
  - `board_id`, `author_id`, `author_name`, `npc_author_id`
  - `subject` (80 chars max), `body` (text)
  - `reply_to` (for threading), `is_pinned`, `is_anonymous`
  - `board_sequence` (sequential number per board)
  - Relationships to board, author, parent message
- [ ] Create `MessageRead` model with:
  - Composite primary key (`character_id`, `message_id`)
  - `read_at` timestamp
  - For tracking which messages a character has read

#### 1.2 Register Models
**File:** `src/waystone/database/models/__init__.py`

- [ ] Import new models: `BulletinBoard`, `BoardMessage`, `MessageRead`, `BoardAccessLevel`
- [ ] Add to `__all__` exports

#### 1.3 Create Database Migration
**Using Alembic or direct SQL**

- [ ] Generate migration for new tables
- [ ] Test migration on development database
- [ ] Verify foreign key constraints work correctly

#### 1.4 Seed Initial Boards
**Data initialization**

- [ ] Create 7 predefined boards:
  1. **University Main** - `university_courtyard` - Public read, Student post
  2. **Admissions Board** - `university_hollows` - Public read, Master post
  3. **Research Requests** - `university_archives` - Student read, Advanced post
  4. **Artificer's Guild** - `university_artificery` - Public read, Student post
  5. **Eolian Performers** - `imre_eolian` - Public read/post, CHA 12+ requirement
  6. **Imre Marketplace** - `imre_main_square` - Public read/post
  7. **Courier Board** - `imre_main_gate` - Public, anonymous allowed

### Validation
- [ ] Run migration successfully
- [ ] Verify all 7 boards created in database
- [ ] Check foreign key constraints with test data
- [ ] Confirm SQLAlchemy relationships work

---

## Phase 2: Core Game System (Days 3-4)

### Goal
Implement `BoardManager` game system with access control and CRUD operations.

### Tasks

#### 2.1 Create Bulletin System
**File:** `src/waystone/game/systems/bulletin.py`

- [ ] Create `BoardInfo` dataclass (for lightweight board data transfer)
- [ ] Create `MessageInfo` dataclass (for message display)
- [ ] Implement `BoardManager` class with methods:
  - `get_boards_in_room(room_id)` - List boards at location
  - `get_board_by_id(board_id)` - Retrieve board details
  - `can_read_board(character, board)` - Access control check
  - `can_post_to_board(character, board)` - Post permission check
  - `get_messages(board_id, character_id)` - Get messages with read status
  - `get_unread_count(board_id, character_id)` - Count new messages
  - `get_message_by_sequence(board_id, sequence)` - Retrieve specific message
  - `post_message(board_id, author_id, subject, body, reply_to?, is_anonymous?)` - Create message
  - `delete_message(message_id, character_id)` - Remove message (own only)
  - `pin_message(message_id, character_id)` - Pin message (moderators)
  - `mark_as_read(message_id, character_id)` - Track read status
  - `prune_old_messages(board_id)` - Enforce max_messages limit

#### 2.2 Access Control Logic
**Within `BoardManager`**

- [ ] Implement `_check_access_level(character, required_level)`:
  - PUBLIC: Always allowed
  - STUDENT: E'lir or higher
  - ADVANCED: Re'lar or higher
  - MASTER: El'the or Masters
  - PRIVATE: Custom logic
- [ ] Implement `_check_attribute_requirement(character, requirements)`:
  - Parse JSON attribute requirements
  - Verify character meets CHA/INT/WIS minimums

#### 2.3 Message Formatter
**File:** `src/waystone/game/systems/bulletin.py` (same file)

- [ ] Create `MessageFormatter` class with:
  - `format_board_list(boards, character)` - List boards in room
  - `format_message_list(messages, character)` - Thread list with [NEW] tags
  - `format_message(message, character)` - Single message display with ANSI-style borders
  - `format_board_header(board, unread_count)` - Board info header
- [ ] Use box-drawing characters: `┌─┐│└┘├┤┬┴┼`
- [ ] Color coding for new messages, pinned posts

#### 2.4 Integration with GameEngine
**File:** `src/waystone/game/engine.py`

- [ ] Initialize `BoardManager` in engine startup
- [ ] Add to cleanup tasks (periodic message pruning)

### Validation
- [ ] Unit tests for access control logic
- [ ] Test message CRUD operations
- [ ] Verify read tracking works correctly
- [ ] Test message pruning when max_messages exceeded
- [ ] Check formatting output manually

---

## Phase 3: Player Commands (Days 5-6)

### Goal
Implement all player-facing BBS commands following existing command patterns.

### Tasks

#### 3.1 Create Command File
**File:** `src/waystone/game/commands/board.py`

- [ ] Import `Command`, `CommandContext` from `base.py`
- [ ] Import `BoardManager` and formatters

#### 3.2 Implement Commands

##### BoardListCommand
- [ ] **Name:** `board`, **Aliases:** `boards`, `bb`
- [ ] **Function:** List all boards in current room
- [ ] **Output:** Formatted table with board names, descriptions, unread counts
- [ ] **Validation:** Check if room has any boards

##### BoardSelectCommand
- [ ] **Name:** `board <name>`, **Aliases:** none
- [ ] **Function:** Select a board and show message list
- [ ] **Output:** Board header + message list with subjects, authors, dates
- [ ] **Validation:** Board exists in current room, character can read

##### ListCommand
- [ ] **Name:** `list`, **Aliases:** `l`
- [ ] **Function:** List messages on current board
- [ ] **Subcommands:** `list new` - only unread
- [ ] **Output:** Message list with [NEW] tags
- [ ] **Context:** Requires selected board in session state

##### ReadCommand
- [ ] **Name:** `read [number|new|all]`, **Aliases:** `r`
- [ ] **Function:** Read messages
  - `read` - Next unread or first message
  - `read 5` - Message #5
  - `read new` - All unread messages
  - `read all` - All messages
- [ ] **Output:** Formatted message with ANSI borders
- [ ] **Side effect:** Mark as read
- [ ] **Navigation:** Store current message in session

##### PostCommand
- [ ] **Name:** `post <subject>`, **Aliases:** `p`, `write`
- [ ] **Function:** Compose new message
- [ ] **Flow:**
  1. Prompt for subject (if not provided)
  2. Enter multi-line editor mode
  3. Commands: `.send`, `.cancel`, `.help`
- [ ] **Validation:** Character can post to board

##### ReplyCommand
- [ ] **Name:** `reply <number>`, **Aliases:** `re`
- [ ] **Function:** Reply to existing message
- [ ] **Flow:** Same as post, but sets `reply_to`
- [ ] **Output:** Quote original message in compose mode

##### RemoveCommand
- [ ] **Name:** `remove <number>`, **Aliases:** `delete`, `del`
- [ ] **Function:** Delete own message
- [ ] **Validation:** Character is author OR has moderator powers

##### PinCommand
- [ ] **Name:** `pin <number>`, **Aliases:** none
- [ ] **Function:** Pin message to top (moderators only)
- [ ] **Validation:** Character is El'the or Master

##### NextCommand
- [ ] **Name:** `next`, **Aliases:** `n`
- [ ] **Function:** Read next message
- [ ] **Context:** Uses current message from session

##### PrevCommand
- [ ] **Name:** `prev`, **Aliases:** `previous`, `p`
- [ ] **Function:** Read previous message
- [ ] **Context:** Uses current message from session

#### 3.3 Session State Management
**Tracking selected board and current message**

- [ ] Add `selected_board_id` to session state
- [ ] Add `current_message_sequence` to session state
- [ ] Clear board context on room change
- [ ] Clear on logout

#### 3.4 Register Commands
**File:** `src/waystone/game/engine.py`

- [ ] Import all board commands
- [ ] Register in `_register_commands()` method

### Validation
- [ ] Test each command with valid inputs
- [ ] Test error cases (no board selected, invalid message number)
- [ ] Verify access control prevents unauthorized actions
- [ ] Check multi-line editor works correctly
- [ ] Test navigation (next/prev) flows properly

---

## Phase 4: NPC Integration (Days 7-8)

### Goal
Implement scheduled NPC posting system with personality-appropriate content.

### Tasks

#### 4.1 Create NPC Poster System
**File:** `src/waystone/game/systems/npc_poster.py`

- [ ] Create `NPCPostTemplate` dataclass:
  - `subject_patterns` (list of format strings)
  - `body_patterns` (list of format strings)
  - `generate_subject(**kwargs)` - Random subject
  - `generate_body(**kwargs)` - Random body
- [ ] Create `NPCPostingSchedule` dataclass:
  - `npc_template_id`, `npc_name`, `board_id`
  - `min_interval_hours`, `max_interval_hours`
  - `active_hours` (tuple for time range)
  - `probability` (chance to post when checked)
  - `last_post_at`, `next_post_after`
  - `should_post(current_time)` - Scheduling logic
  - `record_post(current_time)` - Update state

#### 4.2 Define NPC Personalities

##### Elodin Templates
- [ ] **Subjects:** "Wind", "Names", "Class Cancelled", "A Thought", "Regarding Doors"
- [ ] **Tone:** Cryptic, whimsical, non-sequitur
- [ ] **Boards:** `university_main`
- [ ] **Schedule:** Random hours (2am-11pm), low probability (0.1)
- [ ] **Example:** "The name of the wind is not a name. Think on this. Or don't."

##### Ambrose Templates
- [ ] **Subjects:** "Commoner Infestation", "Eolian Performance", "Quality Standards"
- [ ] **Tone:** Haughty, condescending, formal
- [ ] **Boards:** `university_main`, `eolian_performers`
- [ ] **Schedule:** Afternoon (2pm-8pm), medium probability (0.3)
- [ ] **Example:** "Those of proper breeding should not have to navigate around the detritus of the lower classes."

##### Kilvin Templates
- [ ] **Subjects:** "Workshop Schedule", "Safety Reminder", "Equipment Maintenance"
- [ ] **Tone:** Practical, safety-focused, terse
- [ ] **Boards:** `artificery_commissions`
- [ ] **Schedule:** Morning (6am-10am), high probability (0.5)
- [ ] **Example:** "Reminder: Secure all crucibles before leaving. Last week's incident was preventable."

##### Lorren Templates
- [ ] **Subjects:** "Archives Policy Update", "Overdue Materials", "Research Request"
- [ ] **Tone:** Formal, strict, bureaucratic
- [ ] **Boards:** `archives_research`
- [ ] **Schedule:** Business hours (9am-5pm), medium probability (0.3)
- [ ] **Example:** "Effective immediately: No food or drink in the Stacks. Violators will lose privileges."

##### Simmon Templates
- [ ] **Subjects:** "Equipment for Sale", "Study Group", "Eolian Tonight"
- [ ] **Tone:** Friendly, casual, helpful
- [ ] **Boards:** `artificery_commissions`, `eolian_performers`, `imre_marketplace`
- [ ] **Schedule:** Evening (4pm-10pm), medium probability (0.4)
- [ ] **Example:** "Study group forming for Advanced Sympathy. Meet at Anker's, Cendling eve."

#### 4.3 Posting Scheduler
**File:** `src/waystone/game/systems/npc_poster.py`

- [ ] Create `NPCPosterManager` class:
  - `schedules: list[NPCPostingSchedule]` - All NPC schedules
  - `load_schedules()` - Initialize NPC configurations
  - `check_and_post()` - Main periodic task
  - `post_as_npc(schedule, template)` - Execute NPC post
- [ ] Integrate with `BoardManager.post_message()`
- [ ] Store `npc_author_id` in message metadata

#### 4.4 Integrate with Game Loop
**File:** `src/waystone/game/engine.py`

- [ ] Add `NPCPosterManager` to engine
- [ ] Create periodic task: Check every 30 minutes
- [ ] Call `npc_poster.check_and_post()` in cleanup cycle

### Validation
- [ ] Unit tests for template generation
- [ ] Test scheduling logic (active hours, probability)
- [ ] Verify NPCs post with correct personality
- [ ] Check messages show `npc_author_id` correctly
- [ ] Monitor logs for NPC posting activity

---

## Phase 5: Polish & Advanced Features (Days 9-10)

### Goal
Add quality-of-life features and refine user experience.

### Tasks

#### 5.1 Search and Filter
**File:** `src/waystone/game/systems/bulletin.py`

- [ ] Add `search_messages(board_id, query, character_id)`:
  - Search subject and body text
  - Case-insensitive
  - Return matching messages
- [ ] Add `filter_by_author(board_id, author_name, character_id)`:
  - Show all posts by specific author
- [ ] Create `SearchCommand` in `board.py`:
  - `search <keyword>` on current board

#### 5.2 Board Subscriptions (Optional)
**File:** `src/waystone/database/models/bulletin.py`

- [ ] Add `BoardSubscription` model:
  - `character_id`, `board_id`
  - `notify_on_post` (boolean)
- [ ] Notification on new posts to subscribed boards
- [ ] Commands: `subscribe`, `unsubscribe`, `subscriptions`

#### 5.3 Message Export
**File:** `src/waystone/game/commands/board.py`

- [ ] Add `export <number>` command:
  - Save message to character's inventory as readable item
  - "Parchment with message from [author]"
  - Can be given to other players

#### 5.4 Admin Commands
**File:** `src/waystone/game/commands/board.py`

- [ ] Add `boardadmin` command (Masters only):
  - `boardadmin create <id> <name>` - Create new board
  - `boardadmin delete <id>` - Remove board
  - `boardadmin edit <id> <property> <value>` - Modify settings
  - `boardadmin purge <id>` - Clear all messages
  - `boardadmin move <msg#> <target_board>` - Move message

#### 5.5 Message Threading Display
**Enhancement to `MessageFormatter`**

- [ ] Show reply chain in message header:
  - "In reply to message #12 by Kilvin"
- [ ] Option to view full thread:
  - `thread <number>` command shows parent and all replies

#### 5.6 ANSI Art Welcome Screens
**File:** `src/waystone/game/systems/bulletin.py`

- [ ] Add board-specific ASCII art headers:
  - University: Scholarly symbols (books, quills)
  - Eolian: Musical notes
  - Marketplace: Coins and goods
- [ ] Use ANSI colors (adapted for terminal support)

### Validation
- [ ] Test search finds relevant messages
- [ ] Verify subscriptions work (if implemented)
- [ ] Test message export creates item
- [ ] Verify admin commands restricted properly
- [ ] Check threading display shows correct relationships
- [ ] Review ASCII art on different terminals

---

## Phase 6: Testing & Documentation (Days 11-12)

### Goal
Comprehensive testing and documentation for maintainability.

### Tasks

#### 6.1 Unit Tests
**File:** `tests/game/systems/test_bulletin.py`

- [ ] Test `BoardManager.get_boards_in_room()`
- [ ] Test access control with different ranks
- [ ] Test message CRUD operations
- [ ] Test read tracking
- [ ] Test message pruning
- [ ] Test attribute requirements (CHA check)

**File:** `tests/game/systems/test_npc_poster.py`

- [ ] Test template generation
- [ ] Test scheduling logic
- [ ] Test NPC posting creates messages
- [ ] Test probability and time windows

#### 6.2 Integration Tests
**File:** `tests/game/commands/test_board_commands.py`

- [ ] Test full workflow: list boards → select → read → post → reply
- [ ] Test multi-character scenarios (one posts, another reads)
- [ ] Test access denial (non-student tries to post to student board)
- [ ] Test navigation commands (next/prev)
- [ ] Test moderator actions (pin, delete other's posts)

#### 6.3 Performance Tests
**Load testing**

- [ ] Create 1000 messages across multiple boards
- [ ] Benchmark message retrieval time
- [ ] Test read tracking with 100 characters
- [ ] Verify pruning doesn't cause lag

#### 6.4 Update Documentation

**File:** `COMMANDS.md`

- [ ] Add BBS commands section:
  - `board` - List boards
  - `board <name>` - Select board
  - `list [new]` - List messages
  - `read [number|new|all]` - Read messages
  - `post <subject>` - Create post
  - `reply <number>` - Reply to post
  - `remove <number>` - Delete post
  - `pin <number>` - Pin message
  - `next/prev` - Navigate messages
  - `search <keyword>` - Search board

**File:** `PLAYER_GUIDE.md`

- [ ] Add "Bulletin Boards" section:
  - What are bulletin boards
  - Where to find them
  - How to post and reply
  - Board etiquette
  - Examples of NPC posts

**File:** `docs/BBS_ADMIN_GUIDE.md` (new)

- [ ] Create admin guide:
  - Creating new boards
  - Managing access levels
  - Moderating content
  - NPC posting configuration
  - Troubleshooting

#### 6.5 Migration Guide
**File:** `docs/BBS_MIGRATION.md` (new)

- [ ] Document database migration steps
- [ ] Rollback procedures
- [ ] Data seeding instructions
- [ ] Production deployment checklist

### Validation
- [ ] All unit tests pass
- [ ] Integration tests cover happy path
- [ ] Performance benchmarks acceptable (<100ms for message reads)
- [ ] Documentation reviewed for clarity
- [ ] Migration tested on staging environment

---

## Phase 7: Production Deployment (Day 13)

### Goal
Deploy BBS feature to production with monitoring.

### Tasks

#### 7.1 Pre-Deployment Checks
- [ ] Run full test suite on staging
- [ ] Review all database migrations
- [ ] Check for SQL injection vulnerabilities
- [ ] Verify access control prevents privilege escalation
- [ ] Test rollback procedure

#### 7.2 Database Migration
- [ ] Backup production database
- [ ] Run migrations on production
- [ ] Verify boards created successfully
- [ ] Smoke test: Create and read test message

#### 7.3 Feature Activation
- [ ] Deploy new code to production
- [ ] Restart game server
- [ ] Verify commands registered correctly
- [ ] Test with real players

#### 7.4 NPC Posting Activation
- [ ] Enable NPC poster manager
- [ ] Monitor first scheduled posts
- [ ] Verify posts match expected personality
- [ ] Check timing and frequency

#### 7.5 Monitoring
**File:** Setup logging and alerts

- [ ] Log all board operations (reads, posts, deletes)
- [ ] Monitor message creation rate
- [ ] Alert on errors (failed posts, access violations)
- [ ] Track user engagement (messages per day)

#### 7.6 Player Communication
**Announce feature to players**

- [ ] In-game broadcast about new BBS feature
- [ ] Post on Discord/forums with examples
- [ ] Create tutorial quest introducing boards
- [ ] Highlight Elodin's first cryptic post

### Validation
- [ ] Production deployment successful
- [ ] No errors in first 24 hours
- [ ] Players posting messages
- [ ] NPCs posting on schedule
- [ ] Monitoring shows healthy metrics

---

## Success Metrics

### Technical Metrics
- [ ] All 7 boards created and accessible
- [ ] At least 3 NPC posts in first week
- [ ] <100ms average message read time
- [ ] Zero data loss or corruption
- [ ] <5 bugs reported in first month

### Player Engagement Metrics
- [ ] 50% of players read at least one message
- [ ] 25% of players post at least one message
- [ ] 10+ messages per day across all boards
- [ ] Positive feedback from players

### Content Quality Metrics
- [ ] NPC posts match personality (qualitative review)
- [ ] No inappropriate content posted
- [ ] Boards used for intended purposes (University for academic, Eolian for performances)

---

## Risk Mitigation

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Message spam | High | Medium | Rate limiting, moderator tools |
| Performance with 1000+ messages | Medium | High | Pagination, indexing, pruning |
| Access control bypass | Low | High | Thorough testing, code review |
| NPC posting failure | Medium | Low | Error handling, monitoring |

### Content Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Inappropriate posts | High | Medium | Report command, moderator review |
| OOC content on IC boards | Medium | Low | Player education, guidelines |
| Metagaming via boards | Low | Medium | Enforce IC communication rules |

---

## Future Enhancements (Post-Launch)

### Phase 8 Possibilities
- [ ] Private message boards (guilds, factions)
- [ ] Encrypted boards (require key item to read)
- [ ] Cross-location board access via sympathy
- [ ] Message voting/reactions
- [ ] Attachments (link items to posts)
- [ ] Mail system (personal messages)
- [ ] Board categories and tags
- [ ] RSS-style feed for subscribed boards
- [ ] Integration with quest system (quest postings on boards)
- [ ] Reputation system (helpful poster badges)

---

## Agent Assignment Recommendations

### Architect Agent (Already Complete)
- ✅ Design system architecture
- ✅ Define database schema
- ✅ Specify command interfaces

### Engineer Agent (Phases 1-3)
- Implement database models
- Create `BoardManager` system
- Build player commands
- Write unit tests

### Intern Agent (Phase 4)
- Create NPC personality templates
- Implement `NPCPosterManager`
- Populate message content
- Test NPC scheduling

### QA Tester Agent (Phase 6)
- Run comprehensive test suite
- Perform integration testing
- Load testing and benchmarking
- Bug hunting and edge case testing

### Documentation Agent (Phase 6)
- Update player guide
- Create admin documentation
- Write migration guide
- Code documentation review

---

## Implementation Timeline

| Phase | Days | Dependencies | Agents |
|-------|------|--------------|--------|
| Phase 1: Database | 2 | None | Engineer |
| Phase 2: Game System | 2 | Phase 1 | Engineer |
| Phase 3: Commands | 2 | Phase 2 | Engineer |
| Phase 4: NPC Integration | 2 | Phase 3 | Intern |
| Phase 5: Polish | 2 | Phase 4 | Engineer, Intern |
| Phase 6: Testing | 2 | Phase 5 | QA Tester, Documentation |
| Phase 7: Deployment | 1 | Phase 6 | DevOps |

**Total: 13 days**

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** (can we ship after Phase 3?)
3. **Assign agents** to specific phases
4. **Set up project tracking** (GitHub issues, task board)
5. **Begin Phase 1** database implementation

---

*This plan synthesizes research from vintage BBS systems (Renegade, WWIV, FidoNet) with Waystone MUD architecture patterns to create an immersive, thematic bulletin board experience for the Kingkiller Chronicle world.*
