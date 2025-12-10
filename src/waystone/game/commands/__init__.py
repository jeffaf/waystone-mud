"""Command system for Waystone MUD."""

from waystone.game.commands.auth import (
    LoginCommand,
    LogoutCommand,
    QuitCommand,
    RegisterCommand,
)
from waystone.game.commands.base import (
    Command,
    CommandContext,
    CommandRegistry,
    get_registry,
)
from waystone.game.commands.character import (
    CharactersCommand,
    CreateCommand,
    DeleteCommand,
    PlayCommand,
)
from waystone.game.commands.communication import (
    ChatCommand,
    EmoteCommand,
    SayCommand,
    TellCommand,
)
from waystone.game.commands.info import (
    HelpCommand,
    IncreaseCommand,
    SaveCommand,
    ScoreCommand,
    TimeCommand,
    WhoCommand,
)
from waystone.game.commands.merchant import (
    AppraiseCommand,
    BuyCommand,
    ListCommand,
    SellCommand,
)
from waystone.game.commands.movement import (
    DownCommand,
    EastCommand,
    ExitsCommand,
    GoCommand,
    LookCommand,
    NorthCommand,
    NortheastCommand,
    NorthwestCommand,
    SouthCommand,
    SoutheastCommand,
    SouthwestCommand,
    UpCommand,
    WestCommand,
)
from waystone.game.commands.skills import (
    SkillsCommand,
    TrainCommand,
)
from waystone.game.commands.social import (
    EmoteCommands,
    EmotesCommand,
)

__all__ = [
    # Base classes
    "Command",
    "CommandContext",
    "CommandRegistry",
    "get_registry",
    # Auth commands
    "RegisterCommand",
    "LoginCommand",
    "LogoutCommand",
    "QuitCommand",
    # Character commands
    "CharactersCommand",
    "CreateCommand",
    "PlayCommand",
    "DeleteCommand",
    # Movement commands
    "NorthCommand",
    "SouthCommand",
    "EastCommand",
    "WestCommand",
    "UpCommand",
    "DownCommand",
    "NortheastCommand",
    "NorthwestCommand",
    "SoutheastCommand",
    "SouthwestCommand",
    "GoCommand",
    "LookCommand",
    "ExitsCommand",
    # Communication commands
    "SayCommand",
    "EmoteCommand",
    "ChatCommand",
    "TellCommand",
    # Info commands
    "HelpCommand",
    "WhoCommand",
    "ScoreCommand",
    "TimeCommand",
    "IncreaseCommand",
    "SaveCommand",
    # Skill commands
    "SkillsCommand",
    "TrainCommand",
    # Merchant commands
    "ListCommand",
    "BuyCommand",
    "SellCommand",
    "AppraiseCommand",
    # Social emote commands
    "EmoteCommands",
    "EmotesCommand",
]
