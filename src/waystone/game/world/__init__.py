"""World management - rooms, areas, items, NPCs, and navigation."""

from .item import Item, calculate_carry_capacity, calculate_total_weight
from .loader import (
    RoomValidationError,
    WorldLoadError,
    get_room_by_id,
    get_rooms_by_area,
    load_all_rooms,
    load_rooms_from_directory,
)
from .npc_loader import (
    NPCLoadError,
    NPCTemplate,
    NPCValidationError,
    get_npc_by_id,
    get_npcs_by_behavior,
    load_all_npcs,
)
from .room import Room

__all__ = [
    "Room",
    "load_all_rooms",
    "load_rooms_from_directory",
    "get_room_by_id",
    "get_rooms_by_area",
    "WorldLoadError",
    "RoomValidationError",
    "Item",
    "calculate_carry_capacity",
    "calculate_total_weight",
    "NPCTemplate",
    "load_all_npcs",
    "get_npc_by_id",
    "get_npcs_by_behavior",
    "NPCLoadError",
    "NPCValidationError",
]
