"""Telnet client for connecting to Waystone MUD as a player."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
import telnetlib3

logger = structlog.get_logger(__name__)


class ConnectionState(Enum):
    """Connection state of the MUD client."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    LOGGED_IN = "logged_in"
    PLAYING = "playing"


@dataclass
class GameMessage:
    """A message received from the MUD server."""

    raw: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: str = "unknown"  # prompt, room, combat, chat, system, etc.


class MUDClient:
    """
    Async telnet client for connecting to Waystone MUD.

    Connects like a real player via telnet, sending commands and
    receiving responses. Designed to work with an AI agent controller.
    """

    # ANSI escape code pattern for stripping colors
    ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

    # Common prompts and patterns
    PROMPT_PATTERNS = [
        re.compile(r"^> ?$"),  # Standard prompt
        re.compile(r"^Password: ?$"),  # Password prompt
        re.compile(r"^Username: ?$"),  # Username prompt
        re.compile(r"^\[.*\] > ?$"),  # Status prompt
    ]

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1337,
        on_message: Callable[[GameMessage], None] | None = None,
    ) -> None:
        """
        Initialize the MUD client.

        Args:
            host: Server hostname
            port: Server port
            on_message: Optional callback for received messages
        """
        self.host = host
        self.port = port
        self.on_message = on_message

        # telnetlib3 returns TelnetReader/TelnetWriter which work with strings
        self._reader: Any | None = None
        self._writer: Any | None = None
        self._state = ConnectionState.DISCONNECTED
        self._buffer: list[str] = []
        self._running = False
        self._read_task: asyncio.Task[None] | None = None

        # Message history for context
        self._message_history: list[GameMessage] = []
        self._max_history = 100

        logger.info("mud_client_initialized", host=host, port=port)

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected to server."""
        return self._state not in (ConnectionState.DISCONNECTED, ConnectionState.CONNECTING)

    @property
    def message_history(self) -> list[GameMessage]:
        """Get recent message history."""
        return self._message_history.copy()

    def strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes from text."""
        return self.ANSI_PATTERN.sub("", text)

    def _classify_message(self, text: str) -> str:
        """
        Classify message type based on content patterns.

        Returns: Message type string
        """
        clean = self.strip_ansi(text).strip()

        # Check for prompts
        for pattern in self.PROMPT_PATTERNS:
            if pattern.match(clean):
                return "prompt"

        # Room descriptions typically start with a name
        if clean and clean[0].isupper() and "\n" in text:
            return "room"

        # Combat messages
        if any(word in clean.lower() for word in ["attack", "damage", "hit", "miss", "kill"]):
            return "combat"

        # Chat/communication
        if any(word in clean.lower() for word in ["says", "tells you", "chat:", "[ooc]"]):
            return "chat"

        # System messages
        if any(word in clean.lower() for word in ["welcome", "goodbye", "error", "invalid"]):
            return "system"

        return "unknown"

    async def connect(self) -> bool:
        """
        Connect to the MUD server using telnetlib3.

        Returns:
            True if connection successful, False otherwise
        """
        if self._state != ConnectionState.DISCONNECTED:
            logger.warning("client_already_connected", state=self._state.value)
            return False

        self._state = ConnectionState.CONNECTING
        logger.info("connecting_to_mud", host=self.host, port=self.port)

        try:
            # Use telnetlib3 for proper telnet protocol handling
            self._reader, self._writer = await asyncio.wait_for(
                telnetlib3.open_connection(self.host, self.port, encoding="utf-8"), timeout=10.0
            )

            self._state = ConnectionState.CONNECTED
            self._running = True

            # Start background reader
            self._read_task = asyncio.create_task(self._read_loop())

            logger.info("connected_to_mud", host=self.host, port=self.port)
            return True

        except TimeoutError:
            logger.error("connection_timeout", host=self.host, port=self.port)
            self._state = ConnectionState.DISCONNECTED
            return False
        except OSError as e:
            logger.error("connection_failed", host=self.host, port=self.port, error=str(e))
            self._state = ConnectionState.DISCONNECTED
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MUD server."""
        if self._state == ConnectionState.DISCONNECTED:
            return

        logger.info("disconnecting_from_mud")

        self._running = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception as e:
                logger.warning("disconnect_error", error=str(e))
            self._writer = None
            self._reader = None

        self._state = ConnectionState.DISCONNECTED
        logger.info("disconnected_from_mud")

    async def send(self, command: str) -> None:
        """
        Send a command to the MUD server.

        Args:
            command: Command text to send
        """
        if not self._writer or not self.is_connected:
            logger.warning("send_while_disconnected", command=command)
            return

        try:
            # telnetlib3 uses strings and handles encoding
            self._writer.write(f"{command}\r\n")
            await self._writer.drain()

            logger.debug("command_sent", command=command)

        except Exception as e:
            logger.error("send_failed", command=command, error=str(e))
            self._state = ConnectionState.DISCONNECTED

    async def send_and_wait(
        self,
        command: str,
        timeout: float = 5.0,
        wait_for_prompt: bool = True,
    ) -> list[GameMessage]:
        """
        Send a command and wait for response.

        Args:
            command: Command to send
            timeout: Maximum wait time in seconds
            wait_for_prompt: Wait for a prompt to appear

        Returns:
            List of messages received after command
        """
        # Clear buffer before sending
        start_index = len(self._message_history)

        await self.send(command)

        # Wait for response
        end_time = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < end_time:
            await asyncio.sleep(0.1)

            # Check for new messages
            new_messages = self._message_history[start_index:]

            if wait_for_prompt:
                # Check if we received a prompt
                if any(m.message_type == "prompt" for m in new_messages):
                    break
            elif new_messages:
                # Got some response, wait a bit more for complete output
                await asyncio.sleep(0.2)
                break

        return self._message_history[start_index:]

    async def _read_loop(self) -> None:
        """Background task to read server output."""
        if not self._reader:
            return

        buffer = ""

        while self._running and self._reader:
            try:
                # telnetlib3 returns strings directly
                text = await asyncio.wait_for(self._reader.read(4096), timeout=1.0)

                if not text:
                    # Connection closed
                    logger.info("server_closed_connection")
                    self._state = ConnectionState.DISCONNECTED
                    break

                buffer += text

                # Debug: log raw data received
                logger.debug(
                    "raw_data_received", length=len(text), preview=text[:100].replace("\n", "\\n")
                )

                # Process complete lines
                while "\n" in buffer or "\r" in buffer:
                    # Find line boundary
                    end_pos = -1
                    for delim in ["\r\n", "\n", "\r"]:
                        pos = buffer.find(delim)
                        if pos >= 0 and (end_pos < 0 or pos < end_pos):
                            end_pos = pos
                            delim_len = len(delim)

                    if end_pos < 0:
                        break

                    line = buffer[:end_pos]
                    buffer = buffer[end_pos + delim_len :]

                    if line:  # Skip empty lines
                        self._process_line(line)

                # Check for prompt (no newline)
                if buffer and any(
                    p.match(self.strip_ansi(buffer).strip()) for p in self.PROMPT_PATTERNS
                ):
                    self._process_line(buffer)
                    buffer = ""

            except TimeoutError:
                # Normal - just no data right now
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("read_error", error=str(e))
                self._state = ConnectionState.DISCONNECTED
                break

    def _process_line(self, line: str) -> None:
        """Process a received line."""
        message = GameMessage(
            raw=line,
            message_type=self._classify_message(line),
        )

        # Add to history
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        # Callback
        if self.on_message:
            try:
                self.on_message(message)
            except Exception as e:
                logger.error("message_callback_error", error=str(e))

        logger.debug(
            "message_received",
            type=message.message_type,
            content=self.strip_ansi(line)[:80],
        )

    async def login(self, username: str, password: str) -> bool:
        """
        Log in to an existing account.

        Args:
            username: Account username
            password: Account password

        Returns:
            True if login successful
        """
        if self._state != ConnectionState.CONNECTED:
            logger.warning("login_while_not_connected", state=self._state.value)
            return False

        # Wait for initial prompt/welcome
        await asyncio.sleep(1.0)

        # Send login command with username and password
        # Server expects: login <username> <password>
        await self.send(f"login {username} {password}")
        await asyncio.sleep(1.0)

        # Check for success
        recent = (
            self._message_history[-10:]
            if len(self._message_history) >= 10
            else self._message_history
        )
        for msg in recent:
            clean = self.strip_ansi(msg.raw).lower()
            if "welcome back" in clean or "logged in" in clean or "characters" in clean:
                self._state = ConnectionState.LOGGED_IN
                logger.info("login_successful", username=username)
                return True
            if "invalid" in clean or "incorrect" in clean or "failed" in clean:
                logger.warning("login_failed", username=username)
                return False

        # Assume success if no error
        self._state = ConnectionState.LOGGED_IN
        return True

    async def play_character(self, character_name: str) -> bool:
        """
        Select a character to play.

        Args:
            character_name: Name of character to play

        Returns:
            True if character selection successful
        """
        if self._state != ConnectionState.LOGGED_IN:
            logger.warning("play_while_not_logged_in", state=self._state.value)
            return False

        # Send play command and wait for room description
        await self.send(f"play {character_name}")

        # Give the background reader time to process response
        # Check multiple times with small delays
        for _ in range(10):  # Check up to 5 seconds
            await asyncio.sleep(0.5)

            recent = (
                self._message_history[-30:]
                if len(self._message_history) >= 30
                else self._message_history
            )

            # Check for success early
            for msg in recent:
                clean = self.strip_ansi(msg.raw).lower()
                if "welcome to the world" in clean or "[exits:" in clean:
                    logger.debug("play_success_detected", message=clean[:60])
                    self._state = ConnectionState.PLAYING
                    logger.info("playing_character", character=character_name)
                    return True

        # Final check with debug
        recent = (
            self._message_history[-30:]
            if len(self._message_history) >= 30
            else self._message_history
        )

        # Debug: log what messages we received after play command
        logger.debug(
            "play_response_messages",
            count=len(recent),
            messages=[self.strip_ansi(m.raw)[:60] for m in recent[-10:]],
        )

        for msg in recent:
            clean = self.strip_ansi(msg.raw).lower()
            # Success patterns from Waystone
            if "welcome to the world" in clean:
                self._state = ConnectionState.PLAYING
                logger.info("playing_character", character=character_name)
                return True
            # Error patterns
            if "don't have a character named" in clean:
                logger.warning("character_not_found", character=character_name)
                return False
            if "already being played" in clean:
                logger.warning("character_in_use", character=character_name)
                return False

        # Check for room description (Exits: indicates we're in the game world)
        for msg in recent:
            clean = self.strip_ansi(msg.raw).lower()
            if "[exits:" in clean or "exits:" in clean:
                self._state = ConnectionState.PLAYING
                logger.info("playing_character", character=character_name)
                return True

        # Check if prompt changed to game prompt (not Character Select)
        for msg in recent:
            clean = self.strip_ansi(msg.raw).strip()
            if clean == ">" or clean.endswith(" >"):
                if "(character select)" not in clean.lower() and "(login)" not in clean.lower():
                    self._state = ConnectionState.PLAYING
                    return True

        return False

    def get_recent_output(self, count: int = 10, strip_ansi: bool = True) -> str:
        """
        Get recent output as a single string for AI context.

        Args:
            count: Number of recent messages to include
            strip_ansi: Whether to remove ANSI codes

        Returns:
            Concatenated recent output
        """
        recent = (
            self._message_history[-count:]
            if len(self._message_history) >= count
            else self._message_history
        )
        lines = []
        for msg in recent:
            text = self.strip_ansi(msg.raw) if strip_ansi else msg.raw
            if text.strip():
                lines.append(text)
        return "\n".join(lines)

    async def __aenter__(self) -> "MUDClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.disconnect()
