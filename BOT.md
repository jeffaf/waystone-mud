# Waystone MUD Bot (Simulated Player)

An AI-powered bot that plays the game autonomously - useful for testing, populating the world, or just watching an AI explore.

**This is NOT an AI assistant.** It's a simulated player (bot) that connects to the MUD server and plays the game like a human would, making decisions about movement, combat, and exploration.

## Overview

The bot uses Claude Haiku (or optionally Ollama) to decide what commands to send to the game. It can:

- Explore the world and discover new rooms
- Fight NPCs and gain experience
- Navigate to combat areas (Imre sewers, training yard)
- Track session statistics and provide reports

## Prerequisites

1. **Running MUD Server**: Start the server first:
   ```bash
   uv run python -m waystone
   ```

2. **API Key** (for Claude Haiku):
   ```bash
   export ANTHROPIC_API_KEY="your-key-here"
   ```
   Or create a `.env` file in the project root:
   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

3. **Game Account**: Register an account and create a character via telnet first:
   ```bash
   telnet localhost 4000
   # Then: register <username> <password> <email>
   # Then: create <character_name>
   ```

## Running the Bot

### Basic Usage

```bash
uv run python -m waystone.agent.agent \
  --username YOUR_USERNAME \
  --password YOUR_PASSWORD \
  --character YOUR_CHARACTER_NAME \
  --steps 50
```

### Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--host` | | `localhost` | Server hostname |
| `--port` | | `4000` | Server port |
| `--username` | `-u` | (required) | Account username |
| `--password` | `-p` | (required) | Account password |
| `--character` | `-c` | (required) | Character name to play |
| `--steps` | `-s` | `50` | Maximum actions to take |
| `--delay` | `-d` | `2.0` | Seconds between actions |
| `--ollama` | | false | Use Ollama instead of Haiku |
| `--ollama-model` | | `llama3.2` | Ollama model name |

### Examples

```bash
# Run for 100 steps with faster actions
uv run python -m waystone.agent.agent -u myuser -p mypass -c Kvothe -s 100 -d 1.0

# Use Ollama instead of Claude Haiku
uv run python -m waystone.agent.agent -u myuser -p mypass -c Kvothe --ollama

# Use a specific Ollama model
uv run python -m waystone.agent.agent -u myuser -p mypass -c Kvothe --ollama --ollama-model mistral
```

## Session Report

After the agent finishes, it prints a detailed session report:

```
============================================================
AGENT SESSION REPORT
============================================================

STATISTICS:
   Actions taken: 50
   Rooms visited: 12
   NPCs encountered: 5
   Items found: 3
   Combat encounters: 15
   Repeated actions (stuck): 2

API USAGE:
   Input tokens: 45,230
   Output tokens: 1,847
   Estimated cost: $0.0438

ROOMS EXPLORED:
   - Dark Back Alley
   - Imre Main Square
   - Sewers Entrance
   ...

NPCs SEEN:
   - a giant sewer rat
   - a straw training dummy
   ...

OBSERVATIONS:
   - Session ran smoothly with no major issues!
============================================================
```

## World Geography

The agent is programmed to navigate toward combat areas:

```
University (north) - Mostly safe zones, requires E'lir rank
    |
Stonebridge (south from University gates)
    |
Imre Main Square
    ├── Training Yard (west) - Training dummy for practice
    ├── Back Alley (southwest) - Sewer rats
    ├── Sewers (down from alley) - More rats
    └── North Road (northeast) - Bandits
```

## Combat Tips

The bot will:
- Attack any creature it sees ("is here" in room description)
- Prioritize combat over exploration when enemies are present
- Go south from University to find Imre combat areas
- Use partial matching (e.g., "attack rat" works for "a giant sewer rat")

## Troubleshooting

### Bot gets stuck
- Increase `--steps` to give it more time
- The agent may hit rank-restricted areas - it will try alternate routes

### No combat occurring
- Make sure the character is in Imre (south of University)
- Check that NPCs have respawned (rats respawn every 2 minutes)

### API errors
- Verify `ANTHROPIC_API_KEY` is set correctly
- Check you have API credits available

### Using Ollama
- Make sure Ollama is running: `ollama serve`
- Pull the model first: `ollama pull llama3.2`

## Architecture

```
src/waystone/agent/
├── agent.py    # Main agent logic and LLM backends
├── client.py   # Telnet client for MUD connection
└── parser.py   # Game state parser (rooms, NPCs, exits)
```

The bot uses a simple loop:
1. Read game output
2. Parse into structured state
3. Ask LLM for next action
4. Send command to game
5. Wait and repeat

## Cost Estimation

Using Claude Haiku (claude-3-5-haiku):
- ~$0.80 per million input tokens
- ~$4.00 per million output tokens
- Typical 50-step session: ~$0.04-0.05
