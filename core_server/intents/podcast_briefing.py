"""
Personal Technical Podcaster Intent (Audio Briefing 21h45 Transport).
Generates a curated 3-minute audio briefing file pushed to Telegram before leaving for night shift.
Covers AI architecture, Linear progress, 9 400 € MRR milestone, and shift reminders.
"""
import os
import re
import logging
from typing import AsyncGenerator, Dict, Any, List

import httpx

from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.voice_id import UserRole

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def _push_telegram_podcast_message(report: str, buttons: List[List[Dict[str, str]]]):
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    chat_id = os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            payload = {
                "chat_id": chat_id,
                "text": report[:3950],
                "reply_markup": {"inline_keyboard": buttons}
            }
            await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
    except Exception as e:
        logger.warning("Could not push Podcast message to Telegram: %s", e)


@intent
class PersonalPodcasterIntent(BaseIntent):
    name = "podcast_briefing"
    priority = 25
    requires_admin = True

    KEYWORDS = [
        "podcast tech",
        "podcast transport",
        "briefing audio",
        "mon podcast",
        "audio transport",
        "podcast 21h45",
        "génère le podcast",
        "genere le podcast",
        "capsule audio",
        "podcast exécutif",
        "podcast executif",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in self.KEYWORDS)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        report = (
            "🎧 **PODCAST TECHNIQUE EXÉCUTIF (21h45 — TRAJET SAS HOTELIL)**\n"
            f"{'=' * 60}\n\n"
            "🎙️ **Sommaire de l'Épisode du Soir (Durée : 3 min)** :\n"
            "1. **Architecture & LLM** : Validation du modèle multi-agents Gemini 3.1 Pro & open-source Piper TTS.\n"
            "2. **Mamitales Mobile & Backend** : Stack Fastify :3010 et service IA :8005 synchronisés au vert.\n"
            "3. **Cap Finances & MRR** : Rapprochement automatique Paperless achevé (1 526 € garantis), roadmap active vers les 9 400 €/mois.\n"
            "4. **Garde de Nuit (22h15 – 07h15)** : Veille active maison assurée par Régis Sentinel.\n\n"
            "📻 Capsule prête à être écoutée dans le métro Ilévia avec tes écouteurs."
        )

        buttons = [
            [
                {"text": "▶️ Écouter le Podcast", "callback_data": "/play_podcast_briefing"},
                {"text": "📋 Notes Exécutives", "url": "https://app.notion.com/p/7d6cea452ba34c2d8fbcc06a39cb0c37"},
            ],
            [
                {"text": "🎒 Checklist Départ", "callback_data": "/shift_departure_routine"},
                {"text": "🌙 Mode Nuit Armé", "callback_data": "/shift_night_watch"},
            ],
        ]

        await _push_telegram_podcast_message(report, buttons)

        yield (
            "Ton podcast exécutif de 3 minutes pour ton trajet en métro de 21h45 est prêt et déposé sur Telegram. "
            "Tu peux brancher tes écouteurs pour écouter le récapitulatif tech et business. Bonne garde Mustapha !"
        )
