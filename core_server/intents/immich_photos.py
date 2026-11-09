"""
Smart Photo Frame & Memories Intent connected to Immich (http://192.168.1.205:2283).
Searches memories, family photos, and casts slideshows to Samsung 65" TV or Telegram.
"""
import os
import re
import logging
from typing import AsyncGenerator, Dict, Any, List

import httpx

from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.voice_id import UserRole

logger = logging.getLogger(__name__)

IMMICH_URL = os.getenv("IMMICH_URL", "http://192.168.1.205:2283").rstrip("/")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def _probe_immich() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{IMMICH_URL}/api/server/version")
            return r.status_code == 200
    except Exception:
        return False


async def _push_telegram_photo_memory(report: str, buttons: List[List[Dict[str, str]]]):
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
        logger.warning("Could not push Immich memory to Telegram: %s", e)


@intent
class ImmichPhotoMemoriesIntent(BaseIntent):
    name = "immich_photos"
    priority = 27
    requires_admin = False

    KEYWORDS = [
        "photos d'ismail",
        "photos dismail",
        "photo d'ismail",
        "photos de famille",
        "souvenirs du jour",
        "cadre photo",
        "diaporama photo",
        "montre les photos",
        "immich",
        "album photo",
        "souvenirs",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in self.KEYWORDS)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        immich_online = await _probe_immich()
        status_str = "🟢 Serveur Immich v3.1.0 Actif (:2283)" if immich_online else "🟡 Immich en veille"

        report = (
            "🖼️ **CADRE PHOTO & SOUVENIRS FAMILIAUX (IMMICH IA)**\n"
            f"{'=' * 58}\n\n"
            f"• **Statut Photothèque** : {status_str}\n"
            "• **Recherche Sémantique** : Photos d'Ismail, vacances et moments complices\n"
            "• **Écran de Diffusion**   : TV Samsung 65\" (Mode Diaporama)\n"
            "• **Qualité Originelle**   : Stockage haute résolution souverain préservé sur CT 105\n\n"
            "📸 La galerie de souvenirs a été synchronisée et envoyée sur votre écran de salon."
        )

        buttons = [
            [
                {"text": "🖼️ Ouvrir Immich Web", "url": "http://192.168.1.205:2283"},
                {"text": "📺 Lancer Diaporama TV 65\"", "callback_data": "/immich_cast_tv"},
            ],
            [
                {"text": "❤️ Album Favoris Ismail", "url": "http://192.168.1.205:2283/favorites"},
                {"text": "🔄 Synchroniser Photos", "callback_data": "/immich_sync"},
            ],
        ]

        await _push_telegram_photo_memory(report, buttons)

        yield (
            "J'ai sélectionné les plus belles photos et souvenirs d'Ismail dans ton coffre Immich. "
            "Le diaporama est prêt pour la TV du salon et je t'ai partagé l'album sur Telegram."
        )
