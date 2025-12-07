"""Telnet protocol constants and ANSI color helpers for Waystone MUD."""

import re
from typing import Final

# ANSI color codes
ANSI_COLORS: Final[dict[str, str]] = {
    "RED": "\x1b[31m",
    "GREEN": "\x1b[32m",
    "YELLOW": "\x1b[33m",
    "BLUE": "\x1b[34m",
    "MAGENTA": "\x1b[35m",
    "CYAN": "\x1b[36m",
    "WHITE": "\x1b[37m",
    "RESET": "\x1b[0m",
    "BOLD": "\x1b[1m",
    "DIM": "\x1b[2m",
    "UNDERLINE": "\x1b[4m",
}

# ANSI regex pattern for stripping
ANSI_ESCAPE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*m")

# Welcome banner
WELCOME_BANNER: Final[str] = f"""{ANSI_COLORS['CYAN']}{ANSI_COLORS['BOLD']}
╦ ╦┌─┐┬ ┬┌─┐┌┬┐┌─┐┌┐┌┌─┐
║║║├─┤└┬┘└─┐ │ │ │││├┤
╚╩╝┴ ┴ ┴ └─┘ ┴ └─┘┘└┘└─┘
{ANSI_COLORS['RESET']}
{ANSI_COLORS['GREEN']}A Multi-User Dungeon set in the Kingkiller Chronicle universe{ANSI_COLORS['RESET']}
{ANSI_COLORS['DIM']}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{ANSI_COLORS['RESET']}
"""


def colorize(text: str, color: str) -> str:
    """
    Apply ANSI color to text.

    Args:
        text: The text to colorize
        color: Color name from ANSI_COLORS dict (e.g., 'RED', 'GREEN')

    Returns:
        Text wrapped with ANSI color codes
    """
    color_code = ANSI_COLORS.get(color.upper(), "")
    if not color_code:
        return text
    return f"{color_code}{text}{ANSI_COLORS['RESET']}"


def strip_ansi(text: str) -> str:
    """
    Remove ANSI escape codes from text.

    Args:
        text: Text containing ANSI codes

    Returns:
        Text with all ANSI codes removed
    """
    return ANSI_ESCAPE_PATTERN.sub("", text)
