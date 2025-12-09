"""Base command classes and registry for Waystone MUD command system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine
    from waystone.network import Connection, Session

logger = structlog.get_logger(__name__)


@dataclass
class CommandContext:
    """
    Context passed to command execution.

    Contains all the necessary information for a command to execute,
    including session, connection, engine, and parsed arguments.
    """

    session: "Session"
    connection: "Connection"
    engine: "GameEngine"
    args: list[str]
    raw_input: str


class Command(ABC):
    """
    Base class for all MUD commands.

    Commands handle specific player inputs and perform game actions.
    Each command defines its name, aliases, help text, and execution logic.
    """

    name: str = ""
    aliases: list[str] = []
    help_text: str = ""
    min_args: int = 0
    requires_character: bool = True  # Most commands need an active character

    @abstractmethod
    async def execute(self, ctx: CommandContext) -> None:
        """
        Execute the command with the given context.

        Args:
            ctx: Command context with session, connection, engine, and arguments

        Raises:
            Can raise exceptions for error conditions
        """
        raise NotImplementedError

    def validate_args(self, args: list[str]) -> tuple[bool, str | None]:
        """
        Validate command arguments.

        Args:
            args: List of command arguments

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) < self.min_args:
            return False, f"Usage: {self.help_text}"
        return True, None


class CommandRegistry:
    """
    Registry for all available commands.

    Manages command registration, lookup, and retrieval by name or alias.
    """

    def __init__(self) -> None:
        """Initialize empty command registry."""
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}  # alias -> command name
        logger.info("command_registry_initialized")

    def register(self, command: Command) -> None:
        """
        Register a command in the registry.

        Args:
            command: Command instance to register

        Raises:
            ValueError: If command name or alias already registered
        """
        if not command.name:
            raise ValueError("Command must have a name")

        if command.name in self._commands:
            raise ValueError(f"Command '{command.name}' already registered")

        # Register the command
        self._commands[command.name] = command

        # Register all aliases
        for alias in command.aliases:
            if alias in self._aliases:
                raise ValueError(
                    f"Alias '{alias}' already registered for command '{self._aliases[alias]}'"
                )
            self._aliases[alias] = command.name

        logger.debug(
            "command_registered",
            name=command.name,
            aliases=command.aliases,
            requires_character=command.requires_character,
        )

    def get(self, name: str) -> Command | None:
        """
        Get a command by name or alias.

        Args:
            name: Command name or alias

        Returns:
            Command instance if found, None otherwise
        """
        # Try direct lookup
        if name in self._commands:
            return self._commands[name]

        # Try alias lookup
        if name in self._aliases:
            command_name = self._aliases[name]
            return self._commands[command_name]

        return None

    def get_all_commands(self) -> list[Command]:
        """
        Get all registered commands.

        Returns:
            List of all command instances
        """
        return list(self._commands.values())

    def get_commands_for_help(self, requires_character: bool | None = None) -> list[Command]:
        """
        Get commands filtered by character requirement.

        Args:
            requires_character: If True, only commands requiring character.
                               If False, only commands not requiring character.
                               If None, all commands.

        Returns:
            Filtered list of commands
        """
        if requires_character is None:
            return self.get_all_commands()

        return [
            cmd for cmd in self._commands.values() if cmd.requires_character == requires_character
        ]


# Global command registry instance
_registry: CommandRegistry | None = None


def get_registry() -> CommandRegistry:
    """
    Get the global command registry instance.

    Returns:
        The global CommandRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
    return _registry
