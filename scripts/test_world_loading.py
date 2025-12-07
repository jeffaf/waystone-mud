#!/usr/bin/env python3
"""
Test script for Waystone MUD world loading system.

This script demonstrates loading the world data and basic room navigation.
"""

from waystone.game.world.loader import load_all_rooms


def main():
    """Main test function."""
    print("=" * 70)
    print("Waystone MUD - World Loading Test")
    print("=" * 70)

    # Load all rooms
    print("\n🌍 Loading world data...")
    rooms = load_all_rooms()

    print(f"\n✅ Successfully loaded {len(rooms)} rooms")

    # Statistics
    areas = {}
    for room in rooms.values():
        areas[room.area] = areas.get(room.area, 0) + 1

    print("\n📊 World Statistics:")
    print(f"   Total rooms: {len(rooms)}")
    print(f"   Areas: {len(areas)}")
    for area, count in sorted(areas.items()):
        print(f"     - {area}: {count} rooms")

    # Test room display
    print("\n" + "=" * 70)
    print("Sample Room Display")
    print("=" * 70)

    test_room = rooms['university_main_gates']
    print(test_room.format_description())

    # Test navigation
    print("\n" + "=" * 70)
    print("Navigation Test: University → Imre")
    print("=" * 70)

    current_room = rooms['university_main_gates']
    print(f"\n📍 Current location: {current_room.name}")
    print(f"   Exits: {', '.join(current_room.get_available_exits())}")

    # Go south to Stonebridge
    next_room_id = current_room.get_exit('south')
    if next_room_id:
        current_room = rooms[next_room_id]
        print(f"\n📍 Moved south to: {current_room.name}")
        print(f"   Exits: {', '.join(current_room.get_available_exits())}")

        # Go south to Imre Main Square
        next_room_id = current_room.get_exit('south')
        if next_room_id:
            current_room = rooms[next_room_id]
            print(f"\n📍 Moved south to: {current_room.name}")
            print(f"   Exits: {', '.join(current_room.get_available_exits())}")

            # Show all connected rooms
            print(f"\n   From here you can access:")
            for direction, dest_id in sorted(current_room.exits.items()):
                dest = rooms[dest_id]
                print(f"     {direction:10} → {dest.name}")

    # Test room properties
    print("\n" + "=" * 70)
    print("Room Properties Test")
    print("=" * 70)

    test_rooms = [
        'university_main_gates',
        'university_underthing_entrance',
        'imre_eolian',
        'imre_devi_shop'
    ]

    for room_id in test_rooms:
        room = rooms[room_id]
        print(f"\n{room.name}:")
        print(f"   Area: {room.area}")
        print(f"   Outdoor: {'Yes' if room.is_outdoor() else 'No'}")
        print(f"   Lit: {'Yes' if room.is_lit() else 'No'}")
        print(f"   Safe Zone: {'Yes' if room.is_safe_zone() else 'No'}")
        print(f"   Exits: {len(room.exits)}")

    # Test player tracking
    print("\n" + "=" * 70)
    print("Player Tracking Test")
    print("=" * 70)

    # Simulate players moving between rooms
    room = rooms['imre_eolian']
    print(f"\n{room.name}")
    print(f"   Players in room: {room.get_player_count()}")

    room.add_player("player_001")
    room.add_player("player_002")
    print(f"   After two players enter: {room.get_player_count()}")
    print(f"   Player IDs: {sorted(room.players)}")

    room.remove_player("player_001")
    print(f"   After one player leaves: {room.get_player_count()}")
    print(f"   Player IDs: {sorted(room.players)}")

    print("\n" + "=" * 70)
    print("✅ All tests completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
