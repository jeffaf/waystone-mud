"""Network connection abstraction for Waystone MUD."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog
import telnetlib3

if TYPE_CHECKING:
    from telnetlib3 import TelnetReader, TelnetWriter

    from waystone.network.session import Session

logger = structlog.get_logger(__name__)


class Connection:
    """
    Represents a client connection to the MUD server.

    Wraps telnetlib3 reader/writer and provides a clean interface
    for sending/receiving messages with ANSI support.
    """

    def __init__(
        self,
        reader: "TelnetReader",
        writer: "TelnetWriter",
        ip_address: str,
    ) -> None:
        """
        Initialize a new connection.

        Args:
            reader: Telnetlib3 reader for receiving data
            writer: Telnetlib3 writer for sending data
            ip_address: Client IP address
        """
        self.id: UUID = uuid4()
        self.reader = reader
        self.writer = writer
        self.ip_address = ip_address
        self.connected_at = datetime.now(UTC)
        self.session: Session | None = None
        self._closed = False
        self._echo_enabled = True  # Server-side echo for visibility

        # Enable server-side echo via telnet negotiation
        # This tells the client that we will handle echo
        try:
            writer.iac(telnetlib3.WILL, telnetlib3.ECHO)
        except Exception:
            pass  # Some clients may not support option negotiation

        logger.info(
            "connection_created",
            connection_id=str(self.id),
            ip_address=self.ip_address,
        )

    async def send(self, message: str) -> None:
        """
        Send a message to the client.

        Args:
            message: Text to send (can contain ANSI codes)
        """
        if self._closed:
            logger.warning(
                "send_on_closed_connection",
                connection_id=str(self.id),
            )
            return

        try:
            # Normalize line endings for telnet (must be \r\n)
            # First convert any \r\n to \n, then convert all \n to \r\n
            normalized = message.replace("\r\n", "\n").replace("\n", "\r\n")
            self.writer.write(normalized)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as e:
            logger.warning(
                "send_failed",
                connection_id=str(self.id),
                error=str(e),
            )
            self._closed = True
        except Exception as e:
            logger.error(
                "send_error",
                connection_id=str(self.id),
                error=str(e),
                exc_info=True,
            )
            self._closed = True

    async def send_line(self, message: str) -> None:
        """
        Send a message followed by a newline.

        Args:
            message: Text to send
        """
        await self.send(f"{message}\r\n")

    async def readline(self, echo: bool = True) -> str:
        """
        Read a line of input from the client with optional echo.

        Args:
            echo: Whether to echo characters back to client (default True)

        Returns:
            The line read from the client (stripped of whitespace)

        Raises:
            ConnectionError: If connection is closed or read fails
        """
        if self._closed:
            raise ConnectionError("Connection is closed")

        try:
            # Read character by character with echo for better UX
            line_buffer = []
            while True:
                char = await asyncio.wait_for(
                    self.reader.read(1),
                    timeout=300.0,  # 5 minute timeout
                )

                if not char:
                    # Connection closed
                    raise ConnectionError("Connection closed by client")

                # Handle special characters
                if char in ('\r', '\n'):
                    # End of line - send newline and return
                    if echo and self._echo_enabled:
                        self.writer.write('\r\n')
                        await self.writer.drain()
                    break
                elif char == '\x7f' or char == '\b':
                    # Backspace - remove last character if any
                    if line_buffer:
                        line_buffer.pop()
                        if echo and self._echo_enabled:
                            # Move cursor back, overwrite with space, move back again
                            self.writer.write('\b \b')
                            await self.writer.drain()
                elif char == '\x03':
                    # Ctrl+C - cancel current input
                    raise ConnectionError("Input cancelled")
                elif ord(char) >= 32:  # Printable characters
                    line_buffer.append(char)
                    if echo and self._echo_enabled:
                        self.writer.write(char)
                        await self.writer.drain()

            return ''.join(line_buffer).strip()
        except TimeoutError:
            logger.warning(
                "readline_timeout",
                connection_id=str(self.id),
            )
            raise ConnectionError("Read timeout") from None
        except (ConnectionResetError, BrokenPipeError) as e:
            logger.info(
                "readline_connection_lost",
                connection_id=str(self.id),
                error=str(e),
            )
            self._closed = True
            raise ConnectionError("Connection lost") from e
        except Exception as e:
            logger.error(
                "readline_error",
                connection_id=str(self.id),
                error=str(e),
                exc_info=True,
            )
            self._closed = True
            raise ConnectionError(f"Read error: {e}") from e

    async def read_password(self) -> str:
        """
        Read a password from the client without echo.

        Returns:
            The password entered by the user
        """
        return await self.readline(echo=False)

    def close(self) -> None:
        """Close the connection gracefully."""
        if self._closed:
            return

        logger.info(
            "connection_closing",
            connection_id=str(self.id),
            ip_address=self.ip_address,
        )

        try:
            self.writer.close()
            self._closed = True
        except Exception as e:
            logger.error(
                "connection_close_error",
                connection_id=str(self.id),
                error=str(e),
            )

    @property
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self._closed

    def __str__(self) -> str:
        """String representation of connection."""
        return f"Connection({self.id}, {self.ip_address})"

    def __repr__(self) -> str:
        """Detailed representation of connection."""
        return (
            f"Connection(id={self.id}, ip={self.ip_address}, "
            f"connected_at={self.connected_at}, closed={self._closed})"
        )
