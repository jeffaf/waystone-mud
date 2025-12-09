"""CLI entry point for the MUD agent."""

import asyncio

from waystone.agent.agent import run_agent_cli


def main() -> None:
    """Run the MUD agent CLI."""
    asyncio.run(run_agent_cli())


if __name__ == "__main__":
    main()
