#!/usr/bin/env python3
"""Quick script to spawn a test Explorer simulated player."""

import asyncio

from waystone.database.engine import get_session
from waystone.game.systems.simulated_players import (
    BartleType,
    SimulatedPlayerConfig,
    get_sim_manager,
)
from waystone.game.world.loader import load_world


async def main():
    """Spawn a test Explorer simulated player."""
    print("Loading world...")
    world = await load_world()

    # Get starting room (University Gates)
    starting_room = world.rooms.get("university_main_gates")
    if not starting_room:
        print("ERROR: Could not find university_main_gates room")
        return

    print(f"Starting room: {starting_room.name}")

    # Get sim manager
    sim_manager = get_sim_manager()

    # Create Explorer config
    explorer_config = SimulatedPlayerConfig(
        id="test_explorer_1",
        name="Wanderer",
        bartle_type=BartleType.EXPLORER,
        background="A curious traveler exploring the University.",
        active_hours=(0, 23),  # Always active for testing
        starting_room_id="university_main_gates",
    )

    # Add config
    sim_manager.add_config(explorer_config)
    print(f"Added config for {explorer_config.name} (ID: {explorer_config.id})")

    # Login the player
    async with get_session() as db:
        sim_player = await sim_manager.login_player(
            sim_id="test_explorer_1",
            db_session=db,
            room=starting_room,
        )

        if sim_player:
            print(f"✓ Explorer '{sim_player.config.name}' logged in successfully!")
            print(f"  Character ID: {sim_player.character_id}")
            print(f"  Room: {sim_player.current_room.name if sim_player.current_room else 'None'}")
            print(f"\nThe Explorer should now appear in the 'who' list.")
            print(f"They will move around every 60 seconds when the tick runs.")
        else:
            print("ERROR: Failed to login simulated player")


if __name__ == "__main__":
    asyncio.run(main())
