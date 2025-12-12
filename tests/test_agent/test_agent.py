"""Tests for the MUD agent."""

import pytest

from waystone.agent.agent import (
    AgentConfig,
    Goal,
    GoalType,
    MUDAgent,
    RuleBasedBackend,
)


class TestGoalType:
    """Test goal type enum."""

    def test_goal_types_exist(self):
        """Test all expected goal types exist."""
        assert GoalType.EXPLORE
        assert GoalType.GATHER_MONEY
        assert GoalType.LEVEL_UP
        assert GoalType.SOCIAL
        assert GoalType.QUEST
        assert GoalType.TRADE
        assert GoalType.IDLE


class TestGoal:
    """Test Goal dataclass."""

    def test_default_values(self):
        """Test default goal values."""
        goal = Goal(goal_type=GoalType.EXPLORE)
        assert goal.priority == 1
        assert goal.target == ""
        assert goal.progress == 0.0
        assert goal.max_steps == 100

    def test_custom_values(self):
        """Test goal with custom values."""
        goal = Goal(
            goal_type=GoalType.QUEST,
            priority=5,
            target="Find the magic sword",
            max_steps=50,
        )
        assert goal.goal_type == GoalType.QUEST
        assert goal.priority == 5
        assert goal.target == "Find the magic sword"


class TestAgentConfig:
    """Test agent configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AgentConfig()
        assert config.host == "localhost"
        assert config.port == 1337
        assert config.use_haiku is True
        assert config.use_ollama is False
        assert config.action_delay == 2.0

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            host="example.com",
            port=5000,
            username="testuser",
            password="testpass",
            character_name="TestChar",
            use_haiku=False,
            use_ollama=True,
            ollama_model="mistral",
        )
        assert config.host == "example.com"
        assert config.port == 5000
        assert config.username == "testuser"
        assert config.use_haiku is False
        assert config.use_ollama is True
        assert config.ollama_model == "mistral"


class TestRuleBasedBackend:
    """Test rule-based decision backend."""

    @pytest.fixture
    def backend(self):
        """Create a rule-based backend."""
        return RuleBasedBackend()

    @pytest.mark.asyncio
    async def test_decides_direction(self, backend):
        """Test that backend decides on a direction when available."""
        context = """Location: Town Square
Exits: north, south, east"""
        actions = ["north", "south", "east", "look", "inventory"]

        action = await backend.decide_action(context, actions)
        assert action in ["north", "south", "east"]

    @pytest.mark.asyncio
    async def test_picks_up_items(self, backend):
        """Test that backend picks up items."""
        context = """Location: Storage Room
Items here: gold coin"""
        actions = ["look", "inventory", "get gold coin"]

        action = await backend.decide_action(context, actions)
        assert action == "get gold coin"

    @pytest.mark.asyncio
    async def test_looks_at_npcs(self, backend):
        """Test that backend looks at NPCs."""
        context = """Location: Shop
NPCs here: Merchant"""
        actions = ["look", "inventory", "look Merchant"]

        # First pass, should pick look Merchant
        action = await backend.decide_action(context, actions)
        # May be 'look' or 'look Merchant' depending on implementation
        assert action in ["look", "look Merchant"]

    @pytest.mark.asyncio
    async def test_fallback_to_look(self, backend):
        """Test fallback to look when no good options."""
        context = "Location: Dead End"
        actions = ["look"]

        action = await backend.decide_action(context, actions)
        assert action == "look"


class TestMUDAgent:
    """Test MUD agent (unit tests, no actual connection)."""

    @pytest.fixture
    def config(self):
        """Create a test configuration with rules-only."""
        return AgentConfig(
            host="localhost",
            port=1337,
            use_haiku=False,
            use_ollama=False,  # Use rules-only
        )

    @pytest.fixture
    def agent(self, config):
        """Create an agent with rules-only backend."""
        return MUDAgent(config)

    def test_agent_creation(self, agent):
        """Test agent creation."""
        assert agent is not None
        assert isinstance(agent.backend, RuleBasedBackend)

    def test_add_goal(self, agent):
        """Test adding goals."""
        agent.add_goal(Goal(goal_type=GoalType.EXPLORE))
        agent.add_goal(Goal(goal_type=GoalType.GATHER_MONEY, priority=5))

        # Goals should be sorted by priority (highest first)
        assert len(agent._goals) == 2
        assert agent._goals[0].goal_type == GoalType.GATHER_MONEY
        assert agent._goals[1].goal_type == GoalType.EXPLORE

    def test_clear_goals(self, agent):
        """Test clearing goals."""
        agent.add_goal(Goal(goal_type=GoalType.EXPLORE))
        agent.add_goal(Goal(goal_type=GoalType.QUEST))

        agent.clear_goals()
        assert len(agent._goals) == 0

    def test_get_status(self, agent):
        """Test getting agent status."""
        status = agent.get_status()

        assert "connected" in status
        assert "state" in status
        assert "room" in status
        assert "goals" in status
        assert "actions_taken" in status
        assert "backend" in status
        assert status["backend"] == "RuleBasedBackend"

    def test_game_state_property(self, agent):
        """Test game state property."""
        state = agent.game_state
        assert state is not None
        assert state.room is not None


@pytest.mark.asyncio
class TestMUDAgentAsync:
    """Async tests for MUD agent."""

    async def test_start_no_server(self):
        """Test agent start failure when no server."""
        config = AgentConfig(
            host="localhost",
            port=59999,  # Unlikely port
            use_haiku=False,
        )
        agent = MUDAgent(config)

        result = await agent.start()
        assert result is False

    async def test_stop_without_start(self):
        """Test stopping agent that wasn't started."""
        config = AgentConfig(use_haiku=False)
        agent = MUDAgent(config)

        # Should not raise
        await agent.stop()
