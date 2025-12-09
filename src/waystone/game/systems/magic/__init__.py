"""Magic systems for Waystone MUD."""

from .sympathy import (
    Binding,
    BindingType,
    EnergySource,
    HeatSourceType,
    SympatheticBacklash,
    SympatheticLink,
    calculate_binding_efficiency,
    calculate_similarity_score,
    create_binding,
    release_binding,
)

__all__ = [
    "Binding",
    "BindingType",
    "EnergySource",
    "HeatSourceType",
    "SympatheticBacklash",
    "SympatheticLink",
    "calculate_binding_efficiency",
    "calculate_similarity_score",
    "create_binding",
    "release_binding",
]
