"""
SovereignDot Intent Subsystem.
Automatically loads and exposes all registered voice intent skills.
"""
from core_server.intents.base import BaseIntent, IntentContext, intent, register_intent
from core_server.intents.registry import IntentRegistry, global_intent_registry

# Import built-in intents to trigger registration
from core_server.intents import time_date
from core_server.intents import identity
from core_server.intents import memory
from core_server.intents import homelab
from core_server.intents import paperless
from core_server.intents import resilience

# Reload registry once all modules are loaded
global_intent_registry._reload_intents()

__all__ = [
    "BaseIntent",
    "IntentContext",
    "intent",
    "register_intent",
    "IntentRegistry",
    "global_intent_registry",
]
