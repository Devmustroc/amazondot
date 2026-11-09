"""
Stop / Silence Voice Intent for SovereignDot (Echo Dot 2G).
Provides instantaneous interruption and silence when user says 'Stop Régis', 'Silence', 'Pause', 'Tais-toi'.
Priority: 1 (Highest possible, evaluated before all other intents).
"""
import logging
from typing import AsyncGenerator

from core_server.intents.base import BaseIntent, IntentContext, intent

logger = logging.getLogger(__name__)


@intent
class StopPlaybackIntent(BaseIntent):
    name = "stop_playback"
    priority = 1
    requires_admin = False

    STOP_PHRASES = [
        "stop",
        "arrête",
        "arrete",
        "pause",
        "tais-toi",
        "tais toi",
        "silence",
        "chut",
        "ferme-la",
        "coupe le son",
        "arrête de parler",
        "arrete de parler",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower().strip()
        clean = ctx.clean_prompt.lower().strip()
        words = clean.split()
        if len(words) <= 3 and any(sp in clean for sp in self.STOP_PHRASES):
            return True
        return any(p.startswith(sp) for sp in self.STOP_PHRASES)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        logger.info("StopPlaybackIntent triggered: immediate silence requested.")
        yield "D'accord, je m'arrête."
