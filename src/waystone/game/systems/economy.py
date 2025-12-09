"""Economy and currency system for Waystone MUD.

Implements the Cealdish currency system from the Kingkiller Chronicle:
- Iron Drabs (smallest unit)
- Copper Jots (10 drabs)
- Silver Talents (10 jots = 100 drabs)
- Gold Marks (10 talents = 1000 drabs)

All money is stored internally as drabs (smallest denomination).
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from waystone.database.models import Character

logger = structlog.get_logger(__name__)


class CurrencyUnit(IntEnum):
    """Currency denominations in drabs."""

    DRAB = 1  # Iron drab - smallest unit
    JOT = 10  # Copper jot = 10 drabs
    TALENT = 100  # Silver talent = 10 jots = 100 drabs
    MARK = 1000  # Gold mark = 10 talents = 1000 drabs


# Currency display names
CURRENCY_NAMES = {
    CurrencyUnit.DRAB: ("drab", "drabs"),
    CurrencyUnit.JOT: ("jot", "jots"),
    CurrencyUnit.TALENT: ("talent", "talents"),
    CurrencyUnit.MARK: ("mark", "marks"),
}

# Short names for compact display
CURRENCY_SHORT = {
    CurrencyUnit.DRAB: "d",
    CurrencyUnit.JOT: "j",
    CurrencyUnit.TALENT: "t",
    CurrencyUnit.MARK: "m",
}


@dataclass
class Currency:
    """Represents an amount of money in mixed denominations."""

    marks: int = 0
    talents: int = 0
    jots: int = 0
    drabs: int = 0

    @classmethod
    def from_drabs(cls, total_drabs: int) -> "Currency":
        """Create Currency from total drabs, breaking down into denominations."""
        if total_drabs < 0:
            total_drabs = 0

        marks = total_drabs // CurrencyUnit.MARK
        remaining = total_drabs % CurrencyUnit.MARK

        talents = remaining // CurrencyUnit.TALENT
        remaining = remaining % CurrencyUnit.TALENT

        jots = remaining // CurrencyUnit.JOT
        drabs = remaining % CurrencyUnit.JOT

        return cls(marks=marks, talents=talents, jots=jots, drabs=drabs)

    def to_drabs(self) -> int:
        """Convert to total drabs."""
        return (
            self.marks * CurrencyUnit.MARK
            + self.talents * CurrencyUnit.TALENT
            + self.jots * CurrencyUnit.JOT
            + self.drabs
        )

    def __str__(self) -> str:
        """Format as readable string."""
        return format_money(self.to_drabs())

    def __repr__(self) -> str:
        """Technical representation."""
        return f"Currency(marks={self.marks}, talents={self.talents}, jots={self.jots}, drabs={self.drabs})"


def format_money(drabs: int, compact: bool = False) -> str:
    """
    Format money amount for display.

    Args:
        drabs: Amount in drabs (smallest unit)
        compact: If True, use short format (e.g., "3m 4t 2j 1d")

    Returns:
        Formatted string like "3 marks, 4 talents, 2 jots, 1 drab"
    """
    if drabs <= 0:
        return "no money" if not compact else "0d"

    currency = Currency.from_drabs(drabs)
    parts = []

    if compact:
        if currency.marks:
            parts.append(f"{currency.marks}m")
        if currency.talents:
            parts.append(f"{currency.talents}t")
        if currency.jots:
            parts.append(f"{currency.jots}j")
        if currency.drabs:
            parts.append(f"{currency.drabs}d")
        return " ".join(parts) if parts else "0d"
    else:
        if currency.marks:
            name = CURRENCY_NAMES[CurrencyUnit.MARK][0 if currency.marks == 1 else 1]
            parts.append(f"{currency.marks} {name}")
        if currency.talents:
            name = CURRENCY_NAMES[CurrencyUnit.TALENT][0 if currency.talents == 1 else 1]
            parts.append(f"{currency.talents} {name}")
        if currency.jots:
            name = CURRENCY_NAMES[CurrencyUnit.JOT][0 if currency.jots == 1 else 1]
            parts.append(f"{currency.jots} {name}")
        if currency.drabs:
            name = CURRENCY_NAMES[CurrencyUnit.DRAB][0 if currency.drabs == 1 else 1]
            parts.append(f"{currency.drabs} {name}")

        if len(parts) == 0:
            return "no money"
        elif len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        else:
            return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def parse_money(text: str) -> int | None:
    """
    Parse a money amount from text.

    Accepts formats like:
    - "100" (assumed drabs)
    - "5 talents"
    - "2t 3j" (compact)
    - "1 mark, 5 talents"

    Returns:
        Amount in drabs, or None if parsing fails
    """
    text = text.lower().strip()

    if not text:
        return None

    # Try simple number (drabs)
    try:
        return int(text)
    except ValueError:
        pass

    total = 0
    parts = text.replace(",", " ").replace("and", " ").split()

    i = 0
    while i < len(parts):
        part = parts[i]

        # Check for compact format (e.g., "5t", "3j")
        if part[-1] in "mjtd" and part[:-1].isdigit():
            amount = int(part[:-1])
            unit_char = part[-1]
            if unit_char == "m":
                total += amount * CurrencyUnit.MARK
            elif unit_char == "t":
                total += amount * CurrencyUnit.TALENT
            elif unit_char == "j":
                total += amount * CurrencyUnit.JOT
            elif unit_char == "d":
                total += amount * CurrencyUnit.DRAB
            i += 1
            continue

        # Check for "number unit" format
        if part.isdigit() and i + 1 < len(parts):
            amount = int(part)
            unit = parts[i + 1].rstrip("s")  # Remove plural

            if unit in ("mark", "marks"):
                total += amount * CurrencyUnit.MARK
            elif unit in ("talent", "talents"):
                total += amount * CurrencyUnit.TALENT
            elif unit in ("jot", "jots"):
                total += amount * CurrencyUnit.JOT
            elif unit in ("drab", "drabs"):
                total += amount * CurrencyUnit.DRAB
            else:
                return None  # Unknown unit

            i += 2
            continue

        # Just a number by itself
        if part.isdigit():
            total += int(part)
            i += 1
            continue

        # Skip unknown words
        i += 1

    return total if total > 0 else None


def add_money(character: "Character", amount: int, reason: str = "") -> int:
    """
    Add money to a character.

    Args:
        character: The character to give money to
        amount: Amount in drabs to add
        reason: Optional reason for logging

    Returns:
        New total money
    """
    if amount <= 0:
        return character.money

    character.money += amount

    logger.info(
        "money_added",
        character_id=str(character.id),
        character_name=character.name,
        amount=amount,
        new_total=character.money,
        reason=reason,
    )

    return character.money


def remove_money(character: "Character", amount: int, reason: str = "") -> bool:
    """
    Remove money from a character.

    Args:
        character: The character to take money from
        amount: Amount in drabs to remove
        reason: Optional reason for logging

    Returns:
        True if successful, False if insufficient funds
    """
    if amount <= 0:
        return True

    if character.money < amount:
        logger.debug(
            "money_removal_failed",
            character_id=str(character.id),
            amount=amount,
            current=character.money,
            reason=reason,
        )
        return False

    character.money -= amount

    logger.info(
        "money_removed",
        character_id=str(character.id),
        character_name=character.name,
        amount=amount,
        new_total=character.money,
        reason=reason,
    )

    return True


def transfer_money(
    from_char: "Character", to_char: "Character", amount: int, reason: str = ""
) -> bool:
    """
    Transfer money between characters.

    Args:
        from_char: Character sending money
        to_char: Character receiving money
        amount: Amount in drabs to transfer
        reason: Optional reason for logging

    Returns:
        True if successful, False if insufficient funds
    """
    if amount <= 0:
        return True

    if from_char.money < amount:
        return False

    from_char.money -= amount
    to_char.money += amount

    logger.info(
        "money_transferred",
        from_id=str(from_char.id),
        from_name=from_char.name,
        to_id=str(to_char.id),
        to_name=to_char.name,
        amount=amount,
        reason=reason,
    )

    return True


# Common price constants (in drabs)
PRICE_BREAD = 1  # 1 drab
PRICE_ALE = 2  # 2 drabs
PRICE_MEAL = 5  # 5 drabs
PRICE_ROOM_NIGHT = 20  # 2 jots
PRICE_SIMPLE_WEAPON = 100  # 1 talent
PRICE_QUALITY_WEAPON = 500  # 5 talents
PRICE_BASIC_ARMOR = 300  # 3 talents
PRICE_SYMPATHY_LAMP = 2000  # 2 marks


# Conversion helpers
def drabs_to_jots(drabs: int) -> float:
    """Convert drabs to jots (may have remainder)."""
    return drabs / CurrencyUnit.JOT


def drabs_to_talents(drabs: int) -> float:
    """Convert drabs to talents (may have remainder)."""
    return drabs / CurrencyUnit.TALENT


def drabs_to_marks(drabs: int) -> float:
    """Convert drabs to marks (may have remainder)."""
    return drabs / CurrencyUnit.MARK


def jots_to_drabs(jots: int) -> int:
    """Convert jots to drabs."""
    return jots * CurrencyUnit.JOT


def talents_to_drabs(talents: int) -> int:
    """Convert talents to drabs."""
    return talents * CurrencyUnit.TALENT


def marks_to_drabs(marks: int) -> int:
    """Convert marks to drabs."""
    return marks * CurrencyUnit.MARK
