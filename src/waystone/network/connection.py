"""Network connection abstraction for Waystone MUD."""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

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
            self.writer.write(message)
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

    async def readline(self) -> str:
        """
        Read a line of input from the client.

        Returns:
            The line read from the client (stripped of whitespace)

        Raises:
            ConnectionError: If connection is closed or read fails
        """
        if self._closed:
            raise ConnectionError("Connection is closed")

        try:
            # Read until newline with timeout
            line = await asyncio.wait_for(
                self.reader.readline(),
                timeout=300.0,  # 5 minute timeout
            )
            return line.strip()
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
