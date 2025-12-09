"""Waystone MUD AI Agent.

An autonomous agent that plays the MUD using Claude Haiku for decision-making,
with optional Ollama support for local LLM inference.

Usage:
    # With Haiku (requires ANTHROPIC_API_KEY):
    python -m waystone.agent -u username -p password -c CharName

    # With Ollama (local):
    python -m waystone.agent -u username -p password -c CharName --ollama

    # Rules-only (no LLM):
    python -m waystone.agent -u username -p password -c CharName --rules-only
"""

from waystone.agent.client import MUDClient, ConnectionState, GameMessage
from waystone.agent.parser import GameStateParser, GameState, Direction, RoomInfo
from waystone.agent.agent import (
    MUDAgent,
    AgentConfig,
    Goal,
    GoalType,
    LLMBackend,
    HaikuBackend,
    OllamaBackend,
    RuleBasedBackend,
)

__all__ = [
    # Client
    "MUDClient",
    "ConnectionState",
    "GameMessage",
    # Parser
    "GameStateParser",
    "GameState",
    "Direction",
    "RoomInfo",
    # Agent
    "MUDAgent",
    "AgentConfig",
    "Goal",
    "GoalType",
    "LLMBackend",
    "HaikuBackend",
    "OllamaBackend",
    "RuleBasedBackend",
]
