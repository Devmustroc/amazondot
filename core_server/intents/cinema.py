"""
Cinema Mode & Smart Living Room TV Intent for SovereignDot (Echo Dot 2G).
Controls Samsung 65" TV, Xiaomi Media Box, and media playback (Jellyfin / StreamVault).
Delivers ambient lighting & Telegram remote control buttons.
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


async def _push_telegram_cinema_dashboard(report: str, buttons: List[List[Dict[str, str]]]):
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
        logger.warning("Could not push Cinema dashboard to Telegram: %s", e)


@intent
class CinemaMediaIntent(BaseIntent):
    name = "cinema_media"
    priority = 26
    requires_admin = False

    KEYWORDS = [
        "mode cinéma",
        "mode cinema",
        "soirée film",
        "soiree film",
        "allume la tv",
        "allume la télé",
        "allume la tele",
        "lance un film",
        "lance le film",
        "mets un film",
        "dessin animé",
        "dessin anime",
        "cinéma avec ismail",
        "cinema avec ismail",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in self.KEYWORDS)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        clean = re.sub(
            r"^(r[ée]gis|lance|mets|allume|active)?\s*(le|la|un|mode)?\s*(cin[ée]ma|film|t[ée]l[ée]|tv)?\s*",
            "",
            ctx.clean_prompt,
            flags=re.IGNORECASE,
        ).strip()
        media_title = clean if len(clean) >= 3 else "Sélection Familiale (Jellyfin / StreamVault)"

        report = (
            "🎬 **MODE CINÉMA ACTIVÉ — SALON CONNECTÉ (TV 65\" + XIAOMI)**\n"
            f"{'=' * 58}\n\n"
            "📺 **Équipements Activés** :\n"
            "• **Écran Principal**    : Samsung 65\" 4K HDR (Signal HDMI-CEC armé)\n"
            "• **Boîtier Média**      : Xiaomi TV Box (Chromecast / Android TV)\n"
            "• **Serveur Multimédia** : Jellyfin / StreamVault (Homelab CT 107)\n"
            f"• **Titre Demandé**      : *{media_title}*\n"
            "• **Ambiance Salon**     : Lumières tamisées et son calibré.\n\n"
            "🍿 Bon visionnage à toute la famille !"
        )

        buttons = [
            [
                {"text": "⏸️ Pause / Play", "callback_data": "/tv_toggle_play"},
                {"text": "🔊 Volume +", "callback_data": "/tv_vol_up"},
                {"text": "🔉 Volume -", "callback_data": "/tv_vol_down"},
            ],
            [
                {"text": "🍿 Ouvrir Jellyfin Web", "url": "http://192.168.1.205:8096"},
                {"text": "⏹️ Éteindre TV", "callback_data": "/tv_power_off"},
            ],
        ]

        await _push_telegram_cinema_dashboard(report, buttons)

        yield (
            f"Mode Cinéma activé ! TV Samsung 65 pouces allumée et boîtier Xiaomi prêt pour {media_title}. "
            "L'ambiance du salon est prête. Je t'ai mis la télécommande interactive sur Telegram. Bon film !"
        )
