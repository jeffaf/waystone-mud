"""MUD Agent - AI-powered player for Waystone MUD.

Uses Claude Haiku (primary) or Ollama (optional) for decision-making.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

# Load .env file for API keys
try:
    from dotenv import load_dotenv

    # Look for .env in project root
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use environment variables directly

from waystone.agent.client import MUDClient
from waystone.agent.parser import Direction, GameState, GameStateParser

logger = structlog.get_logger(__name__)


class GoalType(Enum):
    """Types of goals the agent can pursue."""

    EXPLORE = "explore"  # Explore the world
    GATHER_MONEY = "gather_money"  # Earn currency
    LEVEL_UP = "level_up"  # Gain experience
    SOCIAL = "social"  # Interact with other players
    QUEST = "quest"  # Complete quests
    TRADE = "trade"  # Buy/sell items
    IDLE = "idle"  # Wait for events


@dataclass
class Goal:
    """A goal for the agent to pursue."""

    goal_type: GoalType
    priority: int = 1  # Higher = more important
    target: str = ""  # Optional target (room, item, player, etc.)
    progress: float = 0.0  # 0.0 to 1.0
    max_steps: int = 100  # Give up after this many steps


@dataclass
class AgentConfig:
    """Configuration for the MUD agent."""

    host: str = "localhost"
    port: int = 4000
    username: str = ""
    password: str = ""
    character_name: str = ""

    # LLM settings
    use_haiku: bool = True  # Use Claude Haiku (primary)
    use_ollama: bool = False  # Use Ollama as alternative
    ollama_model: str = "llama3.2"  # Ollama model name
    ollama_host: str = "http://localhost:11434"

    # Behavior settings
    action_delay: float = 2.0  # Seconds between actions
    max_idle_actions: int = 10  # Max actions without progress before switching goals
    verbose: bool = True  # Log detailed output


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    async def decide_action(self, context: str, available_actions: list[str]) -> str:
        """
        Decide which action to take.

        Args:
            context: Current game state context
            available_actions: List of available actions

        Returns:
            Action string to execute
        """
        pass


class HaikuBackend(LLMBackend):
    """Claude Haiku backend for decision-making."""

    def __init__(self) -> None:
        """Initialize Haiku backend."""
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required for Haiku")

        # Import here to avoid dependency issues if not using Haiku
        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package required: pip install anthropic")

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        logger.info("haiku_backend_initialized")

    async def decide_action(self, context: str, available_actions: list[str]) -> str:
        """Use Claude Haiku to decide action."""
        prompt = f"""You are an AI agent playing a text-based MUD. Your goals in priority order:

1. COMBAT: If you see creatures (rats, bandits, training dummies), attack them to gain XP
2. FIND COMBAT: Go SOUTH from the University to reach Imre where combat areas exist
3. EXPLORE: Move to new areas, prefer unexplored directions
4. SURVIVE: If low on health, rest or flee
5. CHECK PROGRESS: Periodically use "score" to check XP/level

WORLD GEOGRAPHY:
- University (north) = mostly safe zone, requires E'lir rank for many areas
- Stonebridge (south from University gates) = connects to Imre
- Imre (south across Stonebridge) = has combat areas:
  - Training Yard (west from main square) = training dummy
  - Back Alley (southwest) = sewer rats
  - North Road (northeast from main square) = bandits

CREATURE INDICATORS (attack these):
- "is here" = creature present (e.g. "a giant sewer rat is here")
- "training dummy" = safe combat practice
- RED colored text = hostile creature

AVAILABLE COMMANDS:
Movement: north/n, south/s, east/e, west/w, up/u, down/d, look/l, exits
Combat: attack <target>, defend, flee, consider <npc>, combatstatus/cs
Info: score/stats, who, help, wealth, time
Items: inventory/i, get <item>, drop <item>, equip <item>, examine <item>
Communication: say '<msg>, chat <msg>, tell <player> <msg>
Sympathy Magic: hold <source>, bind <type> <src> <tgt>, heat, push, unbind

XP SYSTEM:
- Killing enemies gives 10 XP × enemy level
- Level 2 requires 100 XP total, Level 3 requires 400 XP
- Use "score" to check your current level and XP progress

Current game state:
{context}

Available actions: {", ".join(available_actions)}

RULES:
- If you see "is here" with a creature name, use "attack <creature>"
- Example: "a giant sewer rat is here" -> respond: attack rat
- GO SOUTH to find combat areas - the University is mostly off-limits
- If "Access denied" or "requires rank", go a different direction (try SOUTH)
- Don't repeat the same action more than twice
- After combat, use "score" to check XP progress

Respond with ONLY the command. No explanation.

Action:"""

        try:
            # Run sync client in executor to not block
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=50,
                    messages=[{"role": "user", "content": prompt}],
                ),
            )

            # Track token usage
            if hasattr(response, "usage"):
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens

            content_block = response.content[0]
            action = (
                content_block.text.strip().lower() if hasattr(content_block, "text") else "look"
            )
            logger.debug(
                "haiku_decision",
                action=action,
                input_tokens=response.usage.input_tokens if hasattr(response, "usage") else 0,
                output_tokens=response.usage.output_tokens if hasattr(response, "usage") else 0,
            )
            return action

        except Exception as e:
            logger.error("haiku_error", error=str(e))
            # Fallback to first available action
            return available_actions[0] if available_actions else "look"

    def get_token_usage(self) -> tuple[int, int]:
        """Get total token usage (input, output)."""
        return self.total_input_tokens, self.total_output_tokens

    def get_estimated_cost(self) -> float:
        """Get estimated cost in USD based on Haiku pricing."""
        # Haiku pricing: $0.80/M input, $4.00/M output
        input_cost = (self.total_input_tokens / 1_000_000) * 0.80
        output_cost = (self.total_output_tokens / 1_000_000) * 4.00
        return input_cost + output_cost


class OllamaBackend(LLMBackend):
    """Ollama backend for local LLM decision-making."""

    def __init__(self, model: str = "llama3.2", host: str = "http://localhost:11434") -> None:
        """Initialize Ollama backend."""
        self.model = model
        self.host = host.rstrip("/")

        logger.info("ollama_backend_initialized", model=model, host=host)

    async def decide_action(self, context: str, available_actions: list[str]) -> str:
        """Use Ollama to decide action."""
        prompt = f"""You are playing a text MUD game. Given the state below, respond with ONLY the single command to execute.

State:
{context}

Available: {", ".join(available_actions[:10])}

Command:"""

        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": 20},
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp,
            ):
                if resp.status == 200:
                    data = await resp.json()
                    action = data.get("response", "").strip().lower()
                    # Clean up - take first word/command
                    action = action.split("\n")[0].split()[0] if action else "look"
                    logger.debug("ollama_decision", action=action)
                    return action

        except ImportError:
            logger.error("aiohttp required for ollama: pip install aiohttp")
        except Exception as e:
            logger.error("ollama_error", error=str(e))

        return available_actions[0] if available_actions else "look"


class RuleBasedBackend(LLMBackend):
    """Simple rule-based fallback (no LLM needed)."""

    def __init__(self) -> None:
        """Initialize rule-based backend."""
        self._visited_rooms: set[str] = set()
        self._last_direction: Direction | None = None
        logger.info("rule_based_backend_initialized")

    async def decide_action(self, context: str, available_actions: list[str]) -> str:
        """Use simple rules to decide action."""
        # Parse context for room name
        room_name = ""
        for line in context.split("\n"):
            if line.startswith("Location:"):
                room_name = line.split(":", 1)[1].strip()
                break

        # Add room to visited
        if room_name:
            self._visited_rooms.add(room_name)

        # Priority: unexplored directions > items > random direction > look
        directions = [
            "north",
            "south",
            "east",
            "west",
            "up",
            "down",
            "northeast",
            "northwest",
            "southeast",
            "southwest",
        ]

        # Try unexplored directions first
        for action in available_actions:
            if action in directions and action != self._opposite(self._last_direction):
                self._last_direction = Direction.from_string(action)
                return action

        # Pick up items
        for action in available_actions:
            if action.startswith("get "):
                return action

        # Look at NPCs
        for action in available_actions:
            if action.startswith("look ") and action != "look":
                return action

        # Fallback
        return "look"

    def _opposite(self, direction: Direction | None) -> str:
        """Get opposite direction name."""
        if not direction:
            return ""
        opposites = {
            Direction.NORTH: "south",
            Direction.SOUTH: "north",
            Direction.EAST: "west",
            Direction.WEST: "east",
            Direction.UP: "down",
            Direction.DOWN: "up",
            Direction.NORTHEAST: "southwest",
            Direction.SOUTHWEST: "northeast",
            Direction.NORTHWEST: "southeast",
            Direction.SOUTHEAST: "northwest",
        }
        return opposites.get(direction, "")


class MUDAgent:
    """
    AI agent that plays Waystone MUD autonomously.

    Uses telnet connection to interact like a real player,
    with Claude Haiku (or Ollama) for decision-making.
    """

    def __init__(self, config: AgentConfig) -> None:
        """
        Initialize the MUD agent.

        Args:
            config: Agent configuration
        """
        self.config = config
        self.client = MUDClient(host=config.host, port=config.port)
        self.parser = GameStateParser()

        # Initialize LLM backend
        self.backend: LLMBackend
        if config.use_haiku:
            try:
                self.backend = HaikuBackend()
            except (ValueError, ImportError) as e:
                logger.warning("haiku_unavailable", error=str(e))
                if config.use_ollama:
                    self.backend = OllamaBackend(config.ollama_model, config.ollama_host)
                else:
                    logger.info("falling_back_to_rules")
                    self.backend = RuleBasedBackend()
        elif config.use_ollama:
            self.backend = OllamaBackend(config.ollama_model, config.ollama_host)
        else:
            self.backend = RuleBasedBackend()

        # State
        self._running = False
        self._goals: list[Goal] = []
        self._action_history: list[str] = []
        self._steps_since_progress = 0

        # Session tracking for report
        self._session_data: dict[str, Any] = {
            "rooms_visited": set(),
            "npcs_seen": set(),
            "items_found": set(),
            "combat_encounters": 0,
            "errors_encountered": [],
            "access_denied": [],
            "interesting_messages": [],
            "repeated_actions": 0,
            "tokens_input": 0,
            "tokens_output": 0,
        }

        logger.info(
            "mud_agent_initialized",
            host=config.host,
            port=config.port,
            backend=type(self.backend).__name__,
        )

    @property
    def game_state(self) -> GameState:
        """Get current parsed game state."""
        return self.parser.state

    def add_goal(self, goal: Goal) -> None:
        """Add a goal for the agent to pursue."""
        self._goals.append(goal)
        self._goals.sort(key=lambda g: -g.priority)
        logger.info("goal_added", goal_type=goal.goal_type.value, priority=goal.priority)

    def clear_goals(self) -> None:
        """Clear all goals."""
        self._goals.clear()

    async def start(self) -> bool:
        """
        Start the agent - connect, login, and begin playing.

        Returns:
            True if started successfully
        """
        # Connect
        if not await self.client.connect():
            logger.error("agent_connect_failed")
            return False

        # Wait for welcome
        await asyncio.sleep(1.0)

        # Login
        if self.config.username and self.config.password:
            if not await self.client.login(self.config.username, self.config.password):
                logger.error("agent_login_failed")
                await self.client.disconnect()
                return False

            await asyncio.sleep(0.5)

            # Play character
            if self.config.character_name:
                if not await self.client.play_character(self.config.character_name):
                    logger.error("agent_play_failed", character=self.config.character_name)
                    await self.client.disconnect()
                    return False

        self._running = True
        logger.info("agent_started")
        return True

    async def stop(self) -> None:
        """Stop the agent and print session report."""
        self._running = False

        # Fetch final stats before quitting
        if self.client.is_connected:
            messages = await self.client.send_and_wait("stats", timeout=2.0)
            for msg in messages:
                self.parser.parse(msg.raw)

        # Send quit command
        if self.client.is_connected:
            await self.client.send("quit")
            await asyncio.sleep(0.5)

        await self.client.disconnect()
        logger.info("agent_stopped")

        # Print session report
        self._print_session_report()

    def _print_session_report(self) -> None:
        """Print a summary report of the session."""
        print("\n" + "=" * 60)
        print("📊 AGENT SESSION REPORT")
        print("=" * 60)

        print("\n🎯 STATISTICS:")
        print(f"   Actions taken: {len(self._action_history)}")
        print(f"   Rooms visited: {len(self._session_data['rooms_visited'])}")
        print(f"   NPCs encountered: {len(self._session_data['npcs_seen'])}")
        print(f"   Items found: {len(self._session_data['items_found'])}")
        print(f"   Combat encounters: {self._session_data['combat_encounters']}")
        print(f"   Repeated actions (stuck): {self._session_data['repeated_actions']}")

        # Token usage and cost (if using Haiku)
        if isinstance(self.backend, HaikuBackend):
            input_tokens, output_tokens = self.backend.get_token_usage()
            cost = self.backend.get_estimated_cost()
            print("\n💰 API USAGE:")
            print(f"   Input tokens: {input_tokens:,}")
            print(f"   Output tokens: {output_tokens:,}")
            print(f"   Estimated cost: ${cost:.4f}")

        # Character stats
        char = self.parser.state.character
        print("\n🧙 CHARACTER STATS:")
        print(f"   Name: {char.name or self.config.character_name}")
        print(f"   Level: {char.level}")
        print(f"   XP: {char.experience}")
        print(f"   Health: {char.health}/{char.max_health}")
        if char.gold > 0:
            print(f"   Gold: {char.gold}")
        if char.inventory:
            print(f"   Inventory: {len(char.inventory)} items")

        if self._session_data["rooms_visited"]:
            print("\n🗺️  ROOMS EXPLORED:")
            for room in sorted(self._session_data["rooms_visited"]):
                print(f"   - {room}")

        if self._session_data["npcs_seen"]:
            print("\n👥 NPCs SEEN:")
            for npc in sorted(self._session_data["npcs_seen"]):
                print(f"   - {npc}")

        if self._session_data["access_denied"]:
            print("\n🚫 ACCESS DENIED (need higher rank):")
            for msg in self._session_data["access_denied"][:5]:
                print(f"   - {msg}")

        if self._session_data["errors_encountered"]:
            print("\n⚠️  POTENTIAL ISSUES/BUGS:")
            for error in self._session_data["errors_encountered"][:10]:
                print(f"   - {error}")

        # Suggestions
        print("\n💡 OBSERVATIONS:")
        if self._session_data["repeated_actions"] > 3:
            print("   - Agent got stuck repeating actions - may need better exploration logic")
        if self._session_data["combat_encounters"] == 0:
            print("   - No combat occurred - consider adding hostile NPCs to starting areas")
        if len(self._session_data["rooms_visited"]) < 3:
            print("   - Limited exploration - check for movement blockers")
        if self._session_data["access_denied"]:
            print("   - Some areas require University rank - agent needs to advance first")
        if (
            not self._session_data["errors_encountered"]
            and self._session_data["repeated_actions"] <= 3
        ):
            print("   - Session ran smoothly with no major issues!")

        print("\n" + "=" * 60 + "\n")

    async def run(self, max_steps: int | None = None) -> None:
        """
        Main agent loop - take actions until stopped.

        Args:
            max_steps: Maximum actions to take (None = unlimited)
        """
        if not self._running:
            if not await self.start():
                return

        # Add default exploration goal if none set
        if not self._goals:
            self.add_goal(Goal(goal_type=GoalType.EXPLORE, priority=1))

        step_count = 0
        logger.info("agent_run_starting", max_steps=max_steps)

        while self._running:
            # Check step limit
            if max_steps and step_count >= max_steps:
                logger.info("max_steps_reached", steps=step_count)
                break

            try:
                # Take one action
                await self._take_action()
                step_count += 1

                # Delay between actions
                await asyncio.sleep(self.config.action_delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("agent_action_error", error=str(e), exc_info=True)
                await asyncio.sleep(1.0)

        await self.stop()

    async def _take_action(self) -> None:
        """Execute one action cycle."""
        # Get current context
        output = self.client.get_recent_output(count=15)
        self.parser.parse(output)

        # Track session data from output
        self._track_session_data(output)

        context = self.parser.to_context_string()
        available = self.parser.get_available_actions()

        if self.config.verbose:
            logger.info("agent_context", context=context[:200])

        # Get action from LLM
        action = await self.backend.decide_action(context, available)

        # Check for repeated actions
        if (
            len(self._action_history) >= 2
            and self._action_history[-1] == action
            and self._action_history[-2] == action
        ):
            self._session_data["repeated_actions"] += 1

        # Record and execute
        self._action_history.append(action)
        if len(self._action_history) > 100:
            self._action_history.pop(0)

        logger.info("agent_action", action=action)

        # Send command
        await self.client.send(action)

        # Wait for response
        await asyncio.sleep(0.5)

    def _track_session_data(self, output: str) -> None:
        """Track interesting data from game output for session report."""
        output_lower = output.lower()

        # Track room visits
        if self.parser.state.room.name:
            self._session_data["rooms_visited"].add(self.parser.state.room.name)

        # Track NPCs seen
        for npc in self.parser.state.room.npcs:
            self._session_data["npcs_seen"].add(npc)

        # Track items found
        for item in self.parser.state.room.items:
            self._session_data["items_found"].add(item)

        # Track combat
        if "attack" in output_lower or "damage" in output_lower or "hit" in output_lower:
            self._session_data["combat_encounters"] += 1

        # Track access denied messages (potential areas to explore later)
        if "access denied" in output_lower or "requires" in output_lower and "rank" in output_lower:
            # Extract the message
            for line in output.split("\n"):
                if "access denied" in line.lower() or "requires" in line.lower():
                    if line not in self._session_data["access_denied"]:
                        self._session_data["access_denied"].append(line.strip())

        # Track error messages (potential bugs)
        error_indicators = ["error", "invalid", "failed", "unknown command", "can't", "cannot"]
        for indicator in error_indicators:
            if indicator in output_lower:
                for line in output.split("\n"):
                    if indicator in line.lower() and line.strip():
                        if line.strip() not in self._session_data["errors_encountered"]:
                            self._session_data["errors_encountered"].append(line.strip())

    async def run_once(self) -> str:
        """
        Take a single action and return the result.

        Returns:
            The action taken
        """
        if not self.client.is_connected:
            if not await self.start():
                return ""

        await self._take_action()

        # Get response
        await asyncio.sleep(0.5)
        return self._action_history[-1] if self._action_history else ""

    def get_status(self) -> dict[str, Any]:
        """Get current agent status."""
        return {
            "connected": self.client.is_connected,
            "state": self.client.state.value,
            "room": self.parser.state.room.name,
            "goals": [g.goal_type.value for g in self._goals],
            "actions_taken": len(self._action_history),
            "backend": type(self.backend).__name__,
        }


async def run_agent_cli() -> None:
    """Simple CLI to run the agent."""
    import argparse

    argparser = argparse.ArgumentParser(description="Waystone MUD AI Agent")
    argparser.add_argument("--host", default="localhost", help="Server host")
    argparser.add_argument("--port", type=int, default=4000, help="Server port")
    argparser.add_argument("--username", "-u", required=True, help="Account username")
    argparser.add_argument("--password", "-p", required=True, help="Account password")
    argparser.add_argument("--character", "-c", required=True, help="Character name")
    argparser.add_argument("--steps", "-s", type=int, default=50, help="Max steps")
    argparser.add_argument("--delay", "-d", type=float, default=2.0, help="Action delay")
    argparser.add_argument("--ollama", action="store_true", help="Use Ollama instead of Haiku")
    argparser.add_argument("--ollama-model", default="llama3.2", help="Ollama model")
    argparser.add_argument("--rules-only", action="store_true", help="Use rule-based only")

    args = argparser.parse_args()

    config = AgentConfig(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        character_name=args.character,
        use_haiku=not args.ollama and not args.rules_only,
        use_ollama=args.ollama,
        ollama_model=args.ollama_model,
        action_delay=args.delay,
    )

    agent = MUDAgent(config)

    try:
        await agent.run(max_steps=args.steps)
    except KeyboardInterrupt:
        print("\nStopping agent...")
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(run_agent_cli())
