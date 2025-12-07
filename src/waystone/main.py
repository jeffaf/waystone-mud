"""Main entry point for Waystone MUD server."""

import asyncio
import signal
import sys

import structlog

from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


async def main() -> None:
    """
    Main async entry point for the MUD server.

    Starts the game engine and runs until interrupted.
    """
    engine = GameEngine()

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig: int) -> None:
        """Handle shutdown signals."""
        logger.info(
            "shutdown_signal_received",
            signal=signal.Signals(sig).name,
        )
        asyncio.create_task(engine.stop())

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda s, f: signal_handler(s))
        except ValueError:
            # Some signals may not be available on all platforms
            pass

    try:
        # Start the game engine
        await engine.start()

        logger.info(
            "waystone_mud_running",
            message="Waystone MUD is now running. Press Ctrl+C to stop.",
        )

        # Run forever (or until interrupted)
        while engine._running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    except Exception as e:
        logger.error(
            "main_loop_error",
            error=str(e),
            exc_info=True,
        )
        raise
    finally:
        # Ensure cleanup happens
        if engine._running:
            await engine.stop()


def run() -> None:
    """
    Synchronous entry point that runs the async main function.

    This is the function that should be called from the command line.
    """
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("server_stopped_by_user")
    except Exception as e:
        logger.error(
            "server_fatal_error",
            error=str(e),
            exc_info=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    run()
