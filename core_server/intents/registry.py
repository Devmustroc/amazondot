"""
Central Intent Registry orchestrator for SovereignDot.
Routes user voice queries to registered skills with priority ordering and RBAC enforcement.
"""
import logging
from typing import List, Optional, AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, _REGISTERED_INTENTS
from core_server.voice_id import UserRole

logger = logging.getLogger("intent_registry")


class IntentRegistry:
    def __init__(self):
        self._intents: List[BaseIntent] = []
        self._reload_intents()

    def _reload_intents(self):
        # Sort registered classes by priority (ascending: 0, 10, 50, ...)
        sorted_classes = sorted(_REGISTERED_INTENTS, key=lambda c: getattr(c, "priority", 50))
        self._intents = [cls() for cls in sorted_classes]
        logger.info("IntentRegistry initialized with %d active intent handler(s).", len(self._intents))

    def register(self, intent_instance: BaseIntent):
        """Allows dynamic programmatic intent registration."""
        self._intents.append(intent_instance)
        self._intents.sort(key=lambda i: getattr(i, "priority", 50))

    async def handle_prompt(self, ctx: IntentContext) -> Optional[AsyncGenerator[str, None]]:
        """
        Evaluates registered intents in priority order.
        Returns a generator of spoken responses if an intent matched, or None if routing to LLM is needed.
        """
        for handler in self._intents:
            try:
                if handler.can_handle(ctx):
                    logger.info("Matched voice intent '%s' (priority=%d)", handler.name, handler.priority)

                    # RBAC Guard for protected intents
                    if handler.requires_admin:
                        is_child = getattr(ctx.speaker, "is_protected_child", False) or getattr(ctx.speaker, "role", None) == UserRole.CHILD
                        if is_child:
                            name = getattr(ctx.speaker, "name", "Enfant")
                            denial = f"Désolé {name}, l'accès aux commandes d'administration du serveur est réservé aux adultes."
                            logger.warning("RBAC Security Alert: Blocked protected intent '%s' for child speaker '%s'", handler.name, name)
                            
                            async def _denial_gen():
                                yield denial
                            return _denial_gen()

                    return handler.execute(ctx)
            except Exception as e:
                logger.error("Error evaluating intent '%s': %s", handler.name, e)

        return None


# Global singleton instance
global_intent_registry = IntentRegistry()
