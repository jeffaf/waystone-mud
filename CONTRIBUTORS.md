# Contributing to Waystone MUD

Welcome! We're excited you're interested in contributing to Waystone MUD.

## Vibe Coding Welcome

This project embraces **vibe coding** - contributions don't need to be perfect. If you have an idea that makes the game more fun, interesting, or immersive, we want to see it! Don't worry about:

- Perfect code style (we have linters for that)
- Complete test coverage (add what you can)
- Comprehensive documentation (basic is fine)

Focus on the **vibe** - does it feel right for the Kingkiller Chronicle world? Does it make the game more fun?

## Ways to Contribute

### Add Content
- **New rooms and areas** - Expand the world with new locations
- **NPCs and creatures** - Add characters to interact with or fight
- **Items and equipment** - Weapons, armor, magical artifacts
- **Quests and storylines** - Adventures for players to undertake
- **Dialogue and lore** - Deepen the world's story

### Improve Gameplay
- **New commands** - Player actions and interactions
- **Combat enhancements** - Skills, abilities, tactics
- **Magic systems** - Sympathy, naming, alchemy
- **Economy features** - Trading, crafting, jobs

### Technical Contributions
- **Bug fixes** - Something broken? Fix it!
- **Performance improvements** - Make it faster
- **Test coverage** - Help ensure stability
- **Documentation** - Help others understand the code

### AI Agent Improvements
- **Better decision-making** - Smarter exploration and combat
- **New goals** - Trading, socializing, questing
- **Prompt engineering** - Better LLM interactions

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/waystone.git
cd waystone
```

### 2. Set Up Development Environment

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Run tests to make sure everything works
uv run pytest
```

### 3. Make Your Changes

Create a branch for your work:
```bash
git checkout -b my-awesome-feature
```

### 4. Test Your Changes

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_game/test_commands.py

# Lint and format
uv run ruff check .
uv run ruff format .
```

### 5. Submit a Pull Request

Push your branch and open a PR. Include:
- What you changed
- Why you changed it
- How to test it (if applicable)

## Project Structure

```
waystone/
├── src/waystone/
│   ├── network/           # Telnet server
│   ├── database/          # SQLAlchemy models
│   ├── game/
│   │   ├── commands/      # Player commands
│   │   ├── systems/       # Combat, economy, magic
│   │   └── world/         # Room and NPC loading
│   └── agent/             # AI agent
├── data/world/            # YAML content files
│   ├── rooms/             # Room definitions
│   ├── npcs/              # NPC definitions
│   └── items/             # Item definitions
└── tests/                 # pytest test suite
```

## Adding Content (The Easy Way)

Most content is defined in YAML files - no Python required!

### Add a New Room

Edit `data/world/rooms/<area>.yaml`:

```yaml
- id: my_new_room
  name: "A Mysterious Cave"
  description: |
    The cave walls glisten with moisture. Strange symbols
    are carved into the rock, their meaning lost to time.
  exits:
    north: existing_room_id
  properties:
    lit: false
    safe_zone: false
```

### Add a New NPC

Edit `data/world/npcs/enemies.yaml`:

```yaml
- id: cave_spider
  name: "a giant cave spider"
  description: |
    A spider the size of a dog, with glistening black
    carapace and venomous fangs.
  level: 2
  max_hp: 25
  behavior: aggressive
  respawn_time: 180
```

### Add a New Item

Edit `data/world/items/<category>.yaml`:

```yaml
- id: iron_sword
  name: "an iron sword"
  description: "A simple but sturdy iron blade."
  item_type: weapon
  weight: 3.0
  value: 50
  properties:
    damage: "1d8"
    slot: main_hand
```

## Code Style

We use:
- **Ruff** for linting and formatting
- **Type hints** for all functions
- **Docstrings** for public APIs

Don't stress too much about style - the CI will catch issues, and we can help clean things up in review.

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions or ideas

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

**Remember: The best contribution is one that makes the game more fun. Don't overthink it - just vibe with it!**
