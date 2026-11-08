"""
Resilience & Network Status intents.
Provides spoken diagnostics on Circuit-Breaker state and offline fallback.
"""
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent


@intent
class NetworkResilienceIntent(BaseIntent):
    name = "network_resilience"
    priority = 20

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in ["état du réseau", "etat du reseau", "mode hors ligne", "statut de connexion", "circuit breaker", "santé réseau", "secours vocal"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        st = ctx.circuit_breaker.get_status()
        state_fr = "connecté au cloud" if st["state"] == "CLOSED" else "hors ligne avec repli local Piper ONNX" if st["state"] == "OPEN" else "en test de reconnexion cloud"
        yield f"Le circuit réseau est {st['state']}. Nous sommes {state_fr}. {st['total_fallbacks']} bascules de secours enregistrées."
