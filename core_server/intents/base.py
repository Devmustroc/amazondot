"""
Base Intent abstractions and @intent decorator for SovereignDot.
Allows creating new voice skills in isolated files without touching core logic.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, AsyncGenerator, Any, Callable, Type
import re
import logging

logger = logging.getLogger("intents")


@dataclass
class IntentContext:
    prompt: str
    clean_prompt: str
    speaker: Any
    obsidian: Any
    circuit_breaker: Any
    mcp: Optional[Any] = None
    extra: Optional[dict] = None


class BaseIntent(ABC):
    name: str = "base"
    priority: int = 50  # Lower number = higher priority (0 = highest)
    requires_admin: bool = False

    @abstractmethod
    def can_handle(self, ctx: IntentContext) -> bool:
        """Returns True if this intent matches the user voice prompt."""
        pass

    @abstractmethod
    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        """Yields spoken response sentences."""
        pass


# Global intent registry container
_REGISTERED_INTENTS: List[Type[BaseIntent]] = []


def register_intent(cls: Type[BaseIntent]) -> Type[BaseIntent]:
    """Class decorator to register a voice intent skill."""
    if cls not in _REGISTERED_INTENTS:
        _REGISTERED_INTENTS.append(cls)
        logger.debug("Registered voice intent: %s (priority=%d)", cls.name, cls.priority)
    return cls


intent = register_intent
