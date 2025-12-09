"""Tests for the economy and currency system."""

import pytest

from waystone.game.systems.economy import (
    Currency,
    CurrencyUnit,
    format_money,
    parse_money,
    drabs_to_jots,
    drabs_to_talents,
    jots_to_drabs,
    talents_to_drabs,
    marks_to_drabs,
)
from waystone.game.systems.merchant import get_charisma_modifier


class TestCurrencyUnit:
    """Tests for currency unit constants."""

    def test_drab_is_smallest(self):
        """Test drab is the base unit."""
        assert CurrencyUnit.DRAB == 1

    def test_jot_equals_10_drabs(self):
        """Test jot conversion."""
        assert CurrencyUnit.JOT == 10

    def test_talent_equals_100_drabs(self):
        """Test talent conversion."""
        assert CurrencyUnit.TALENT == 100

    def test_mark_equals_1000_drabs(self):
        """Test mark conversion."""
        assert CurrencyUnit.MARK == 1000

    def test_currency_hierarchy(self):
        """Test currency units increase correctly."""
        assert CurrencyUnit.DRAB < CurrencyUnit.JOT < CurrencyUnit.TALENT < CurrencyUnit.MARK


class TestCurrency:
    """Tests for Currency dataclass."""

    def test_from_drabs_simple(self):
        """Test converting drabs to Currency."""
        currency = Currency.from_drabs(5)
        assert currency.drabs == 5
        assert currency.jots == 0
        assert currency.talents == 0
        assert currency.marks == 0

    def test_from_drabs_mixed(self):
        """Test converting mixed amount."""
        # 1234 drabs = 1 talent, 2 jots, 3 drabs, 4 remains... wait
        # 1234 = 1000 (1 mark) + 200 (2 talents) + 30 (3 jots) + 4 drabs
        currency = Currency.from_drabs(1234)
        assert currency.marks == 1
        assert currency.talents == 2
        assert currency.jots == 3
        assert currency.drabs == 4

    def test_from_drabs_exact_talent(self):
        """Test exact talent conversion."""
        currency = Currency.from_drabs(100)
        assert currency.marks == 0
        assert currency.talents == 1
        assert currency.jots == 0
        assert currency.drabs == 0

    def test_from_drabs_zero(self):
        """Test zero amount."""
        currency = Currency.from_drabs(0)
        assert currency.marks == 0
        assert currency.talents == 0
        assert currency.jots == 0
        assert currency.drabs == 0

    def test_from_drabs_negative(self):
        """Test negative amount is treated as zero."""
        currency = Currency.from_drabs(-100)
        assert currency.to_drabs() == 0

    def test_to_drabs(self):
        """Test converting Currency back to drabs."""
        currency = Currency(marks=2, talents=3, jots=4, drabs=5)
        # 2*1000 + 3*100 + 4*10 + 5 = 2000 + 300 + 40 + 5 = 2345
        assert currency.to_drabs() == 2345

    def test_roundtrip(self):
        """Test drabs -> Currency -> drabs roundtrip."""
        original = 9876
        currency = Currency.from_drabs(original)
        assert currency.to_drabs() == original


class TestFormatMoney:
    """Tests for format_money function."""

    def test_format_single_drab(self):
        """Test formatting 1 drab."""
        assert format_money(1) == "1 drab"

    def test_format_multiple_drabs(self):
        """Test formatting multiple drabs."""
        assert format_money(5) == "5 drabs"

    def test_format_single_jot(self):
        """Test formatting 1 jot."""
        assert format_money(10) == "1 jot"

    def test_format_single_talent(self):
        """Test formatting 1 talent."""
        assert format_money(100) == "1 talent"

    def test_format_single_mark(self):
        """Test formatting 1 mark."""
        assert format_money(1000) == "1 mark"

    def test_format_mixed_two_units(self):
        """Test formatting two denominations."""
        assert format_money(15) == "1 jot and 5 drabs"

    def test_format_mixed_three_units(self):
        """Test formatting three denominations."""
        assert format_money(115) == "1 talent, 1 jot, and 5 drabs"

    def test_format_mixed_all_units(self):
        """Test formatting all denominations."""
        assert format_money(1234) == "1 mark, 2 talents, 3 jots, and 4 drabs"

    def test_format_zero(self):
        """Test formatting zero money."""
        assert format_money(0) == "no money"

    def test_format_negative(self):
        """Test formatting negative money."""
        assert format_money(-100) == "no money"

    def test_format_compact(self):
        """Test compact formatting."""
        assert format_money(1234, compact=True) == "1m 2t 3j 4d"

    def test_format_compact_partial(self):
        """Test compact format with missing units."""
        assert format_money(105, compact=True) == "1t 5d"

    def test_format_compact_zero(self):
        """Test compact format for zero."""
        assert format_money(0, compact=True) == "0d"


class TestParseMoney:
    """Tests for parse_money function."""

    def test_parse_simple_number(self):
        """Test parsing simple number as drabs."""
        assert parse_money("100") == 100

    def test_parse_talent_singular(self):
        """Test parsing 'X talent'."""
        assert parse_money("5 talents") == 500

    def test_parse_jot_singular(self):
        """Test parsing 'X jot'."""
        assert parse_money("3 jots") == 30

    def test_parse_mark_singular(self):
        """Test parsing 'X mark'."""
        assert parse_money("2 marks") == 2000

    def test_parse_compact(self):
        """Test parsing compact format."""
        assert parse_money("1m 2t 3j 4d") == 1234

    def test_parse_compact_partial(self):
        """Test parsing partial compact format."""
        assert parse_money("5t") == 500

    def test_parse_with_and(self):
        """Test parsing with 'and'."""
        assert parse_money("1 talent and 5 drabs") == 105

    def test_parse_with_commas(self):
        """Test parsing with commas."""
        assert parse_money("1 mark, 2 talents") == 1200

    def test_parse_empty(self):
        """Test parsing empty string."""
        assert parse_money("") is None

    def test_parse_invalid(self):
        """Test parsing invalid input."""
        assert parse_money("lots of money") is None


class TestConversions:
    """Tests for conversion helper functions."""

    def test_drabs_to_jots(self):
        """Test drab to jot conversion."""
        assert drabs_to_jots(25) == 2.5

    def test_drabs_to_talents(self):
        """Test drab to talent conversion."""
        assert drabs_to_talents(250) == 2.5

    def test_jots_to_drabs(self):
        """Test jot to drab conversion."""
        assert jots_to_drabs(5) == 50

    def test_talents_to_drabs(self):
        """Test talent to drab conversion."""
        assert talents_to_drabs(3) == 300

    def test_marks_to_drabs(self):
        """Test mark to drab conversion."""
        assert marks_to_drabs(2) == 2000


class TestCharismaModifier:
    """Tests for charisma-based price modifiers."""

    def test_low_charisma_penalty(self):
        """Test very low charisma gives worse prices."""
        assert get_charisma_modifier(7) == 1.15  # 15% penalty
        assert get_charisma_modifier(5) == 1.15

    def test_below_average_charisma(self):
        """Test below average charisma gives slight penalty."""
        assert get_charisma_modifier(8) == 1.10
        assert get_charisma_modifier(9) == 1.10

    def test_average_charisma(self):
        """Test average charisma has no modifier."""
        assert get_charisma_modifier(10) == 1.0
        assert get_charisma_modifier(11) == 1.0

    def test_above_average_charisma(self):
        """Test above average charisma gives small discount."""
        assert get_charisma_modifier(12) == 0.95
        assert get_charisma_modifier(13) == 0.95

    def test_good_charisma(self):
        """Test good charisma gives better discount."""
        assert get_charisma_modifier(14) == 0.90
        assert get_charisma_modifier(15) == 0.90

    def test_great_charisma(self):
        """Test great charisma gives good discount."""
        assert get_charisma_modifier(16) == 0.85
        assert get_charisma_modifier(17) == 0.85

    def test_exceptional_charisma(self):
        """Test exceptional charisma gives best discount."""
        assert get_charisma_modifier(18) == 0.80
        assert get_charisma_modifier(20) == 0.80  # Also high values
