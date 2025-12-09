"""Fixtures for systems tests."""

import pytest

from waystone.game.systems import merchant as merchant_system


@pytest.fixture(autouse=True)
def reset_merchant_cache():
    """Reset merchant cache before each test for proper isolation."""
    # Clear and reload merchant inventories before each test
    merchant_system._merchant_inventories.clear()
    merchant_system.load_merchant_inventories()
    yield
    # Clean up after test
    merchant_system._merchant_inventories.clear()
