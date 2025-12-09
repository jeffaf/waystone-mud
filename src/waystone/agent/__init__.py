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

from waystone.agent.agent import (
    AgentConfig,
    Goal,
    GoalType,
    HaikuBackend,
    LLMBackend,
    MUDAgent,
    OllamaBackend,
    RuleBasedBackend,
)
from waystone.agent.client import ConnectionState, GameMessage, MUDClient
from waystone.agent.parser import Direction, GameState, GameStateParser, RoomInfo

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
