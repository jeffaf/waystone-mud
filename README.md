# Waystone MUD

A Multi-User Dungeon set in Patrick Rothfuss's Kingkiller Chronicle universe.

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server
uv run python -m waystone.server

# Connect (in another terminal)
telnet localhost 4000
```

## Development

```bash
# Install dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/
```

## Project Structure

```
waystone/
├── src/waystone/
│   ├── network/       # Telnet/WebSocket servers
│   ├── database/      # SQLAlchemy models
│   ├── game/
│   │   ├── world/     # Rooms, areas, navigation
│   │   └── commands/  # Player command handlers
│   └── utils/         # Helpers and formatters
├── data/world/        # YAML world definitions
├── tests/             # pytest test suite
└── scripts/           # Admin and setup scripts
```

## License

MIT
