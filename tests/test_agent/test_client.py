"""Tests for the MUD client."""

import pytest

from waystone.agent.client import (
    ConnectionState,
    GameMessage,
    MUDClient,
)


class TestConnectionState:
    """Test connection state enum."""

    def test_states_exist(self):
        """Test all expected states exist."""
        assert ConnectionState.DISCONNECTED
        assert ConnectionState.CONNECTING
        assert ConnectionState.CONNECTED
        assert ConnectionState.LOGGED_IN
        assert ConnectionState.PLAYING


class TestGameMessage:
    """Test GameMessage dataclass."""

    def test_creation(self):
        """Test message creation."""
        msg = GameMessage(raw="Hello world", message_type="chat")
        assert msg.raw == "Hello world"
        assert msg.message_type == "chat"
        assert msg.timestamp is not None

    def test_default_type(self):
        """Test default message type."""
        msg = GameMessage(raw="test")
        assert msg.message_type == "unknown"


class TestMUDClient:
    """Test MUD client (unit tests, no actual connection)."""

    @pytest.fixture
    def client(self):
        """Create a client instance."""
        return MUDClient(host="localhost", port=1337)

    def test_initial_state(self, client):
        """Test initial client state."""
        assert client.state == ConnectionState.DISCONNECTED
        assert client.is_connected is False
        assert client.message_history == []

    def test_strip_ansi(self, client):
        """Test ANSI stripping."""
        text = "\x1b[32mGreen\x1b[0m \x1b[31mRed\x1b[0m"
        assert client.strip_ansi(text) == "Green Red"

    def test_classify_prompt(self, client):
        """Test prompt classification."""
        assert client._classify_message("> ") == "prompt"
        assert client._classify_message("Password: ") == "prompt"

    def test_classify_room(self, client):
        """Test room classification."""
        room_text = """Town Square
A large plaza with a fountain in the center."""
        assert client._classify_message(room_text) == "room"

    def test_classify_combat(self, client):
        """Test combat classification."""
        assert client._classify_message("The orc attacks you!") == "combat"
        assert client._classify_message("You deal 10 damage.") == "combat"

    def test_classify_chat(self, client):
        """Test chat classification."""
        assert client._classify_message("John says 'Hello!'") == "chat"
        assert client._classify_message("[OOC] Player: Hi everyone") == "chat"

    def test_classify_system(self, client):
        """Test system message classification."""
        assert client._classify_message("Welcome to Waystone MUD!") == "system"
        assert client._classify_message("Error: Command not found") == "system"

    def test_get_recent_output_empty(self, client):
        """Test recent output when empty."""
        output = client.get_recent_output()
        assert output == ""

    def test_host_port_config(self, client):
        """Test host and port configuration."""
        assert client.host == "localhost"
        assert client.port == 1337

        custom = MUDClient(host="example.com", port=5000)
        assert custom.host == "example.com"
        assert custom.port == 5000


class TestMUDClientMessageCallback:
    """Test message callback functionality."""

    def test_callback_on_message(self):
        """Test that callback is stored."""
        messages = []

        def callback(msg: GameMessage):
            messages.append(msg)

        client = MUDClient(on_message=callback)
        assert client.on_message is callback


@pytest.mark.asyncio
class TestMUDClientAsync:
    """Async tests for MUD client."""

    async def test_connect_no_server(self):
        """Test connection failure when no server."""
        client = MUDClient(host="localhost", port=59999)  # Unlikely port
        result = await client.connect()
        assert result is False
        assert client.state == ConnectionState.DISCONNECTED

    async def test_send_while_disconnected(self):
        """Test sending while disconnected does nothing."""
        client = MUDClient()
        # Should not raise
        await client.send("test command")
        assert client.state == ConnectionState.DISCONNECTED

    async def test_disconnect_while_disconnected(self):
        """Test disconnecting while already disconnected."""
        client = MUDClient()
        # Should not raise
        await client.disconnect()
        assert client.state == ConnectionState.DISCONNECTED
