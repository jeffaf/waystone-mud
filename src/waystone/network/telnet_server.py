"""Async Telnet server for Waystone MUD using telnetlib3."""

import asyncio
from collections.abc import Callable
from typing import Any

import structlog
import telnetlib3

from waystone.config import get_settings
from waystone.network.connection import Connection

logger = structlog.get_logger(__name__)


class TelnetServer:
    """
    Async Telnet server managing client connections.

    Uses telnetlib3 to handle the Telnet protocol and creates
    Connection objects for each client that connects.
    """

    def __init__(
        self,
        connection_callback: Callable[[Connection], Any] | None = None,
    ) -> None:
        """
        Initialize the Telnet server.

        Args:
            connection_callback: Optional async callback for new connections
        """
        self._settings = get_settings()
        self._server: asyncio.Server | None = None
        self._connections: dict[str, Connection] = {}
        self._connection_callback = connection_callback
        self._running = False

        logger.info("telnet_server_initialized")

    async def _handle_client(
        self,
        reader: telnetlib3.TelnetReader,
        writer: telnetlib3.TelnetWriter,
    ) -> None:
        """
        Handle a new client connection.

        Args:
            reader: Telnetlib3 reader for the connection
            writer: Telnetlib3 writer for the connection
        """
        # Get client IP address
        peername = writer.transport.get_extra_info("peername")
        ip_address = peername[0] if peername else "unknown"

        logger.info(
            "client_connected",
            ip_address=ip_address,
            total_connections=len(self._connections) + 1,
        )

        # Check connection limit per IP
        ip_connection_count = sum(
            1 for conn in self._connections.values() if conn.ip_address == ip_address
        )

        if ip_connection_count >= self._settings.max_connections_per_ip:
            logger.warning(
                "connection_limit_exceeded",
                ip_address=ip_address,
                limit=self._settings.max_connections_per_ip,
            )
            writer.write("Too many connections from your IP address.\r\n")
            await writer.drain()
            writer.close()
            return

        # Create connection object
        connection = Connection(reader, writer, ip_address)
        self._connections[str(connection.id)] = connection

        try:
            # Call the connection callback if provided
            if self._connection_callback:
                if asyncio.iscoroutinefunction(self._connection_callback):
                    await self._connection_callback(connection)
                else:
                    self._connection_callback(connection)

            # Wait for connection to close
            # The callback should handle the actual communication
            while not connection.is_closed:
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            logger.info(
                "client_handler_cancelled",
                connection_id=str(connection.id),
            )
        except Exception as e:
            logger.error(
                "client_handler_error",
                connection_id=str(connection.id),
                error=str(e),
                exc_info=True,
            )
        finally:
            # Clean up connection
            connection.close()
            self._connections.pop(str(connection.id), None)

            logger.info(
                "client_disconnected",
                connection_id=str(connection.id),
                ip_address=ip_address,
                total_connections=len(self._connections),
            )

    async def start(self, host: str | None = None, port: int | None = None) -> None:
        """
        Start the Telnet server.

        Args:
            host: Host address to bind to (defaults to settings)
            port: Port to listen on (defaults to settings)
        """
        if self._running:
            logger.warning("telnet_server_already_running")
            return

        host = host or self._settings.host
        port = port or self._settings.telnet_port

        logger.info(
            "telnet_server_starting",
            host=host,
            port=port,
        )

        try:
            # Create the telnetlib3 server
            self._server = await telnetlib3.create_server(
                host=host,
                port=port,
                shell=self._handle_client,
                encoding="utf-8",
            )

            self._running = True

            logger.info(
                "telnet_server_started",
                host=host,
                port=port,
            )

        except OSError as e:
            logger.error(
                "telnet_server_start_failed",
                host=host,
                port=port,
                error=str(e),
            )
            raise

    async def stop(self) -> None:
        """Stop the Telnet server gracefully."""
        if not self._running:
            logger.warning("telnet_server_not_running")
            return

        logger.info("telnet_server_stopping")

        # Close all active connections
        for connection in list(self._connections.values()):
            try:
                await connection.send_line("Server shutting down...")
                connection.close()
            except Exception as e:
                logger.error(
                    "connection_close_error_on_shutdown",
                    connection_id=str(connection.id),
                    error=str(e),
                )

        # Close the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._running = False
        self._connections.clear()

        logger.info("telnet_server_stopped")

    def get_connections(self) -> list[Connection]:
        """
        Get all active connections.

        Returns:
            List of active Connection objects
        """
        return list(self._connections.values())

    def get_connection_count(self) -> int:
        """
        Get the number of active connections.

        Returns:
            Count of active connections
        """
        return len(self._connections)

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    async def __aenter__(self) -> "TelnetServer":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.stop()
