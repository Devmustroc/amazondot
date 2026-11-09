"""
Mamitales Child Voice Story Intent & Biometric Routing.
When VoiceID detects Ismail (role=CHILD), or when a story is requested,
this intent routes to Mamitales AI Service (http://192.168.1.205:8005)
to deliver warm, interactive bedtime and adventure stories on Echo Dot 2G.
"""
import os
import re
import logging
from typing import AsyncGenerator, Dict, Any, Optional

import httpx

from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.voice_id import UserRole

logger = logging.getLogger(__name__)

MAMITALES_AI_URL = os.getenv("MAMITALES_AI_URL", "http://192.168.1.205:8005").rstrip("/")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Fallback sovereign bedtime stories when offline
OFFLINE_ISMAIL_STORIES = [
    (
        "Ismail et le Petit Robot Étoilé",
        "Il était une fois, dans un ciel rempli d'étoiles scintillantes, un petit robot nommé Bip-Bop. "
        "Bip-Bop avait des yeux bleus lumineux et un grand sourire. Chaque nuit, il cherchait le plus beau "
        "rêve pour l'offrir à un petit garçon très courageux nommé Ismail. Ce soir-là, Bip-Bop trouva une étoile filante "
        "dorée qui murmurait : 'Ismail est le champion des aventuriers, passe une douce nuit pleine de magie !' "
        "Bip-Bop posa doucement l'étoile sur l'oreiller d'Ismail et murmura : Dors bien, petit prince des étoiles."
    ),
    (
        "Ismail et la Forêt des Dinosaures Gentils",
        "Au cœur d'une forêt magique où les arbres chantaient doucement, vivait T-Rexou, un tout petit dinosaure vert "
        "qui adorait manger des fraises des bois. T-Rexou attendait son meilleur ami, Ismail, pour faire une course de trottinette volante. "
        "Ensemble, ils glissèrent sur un arc-en-ciel jusqu'au pays des nuages en coton. T-Rexou dit alors à Ismail : "
        "'Merci pour cette belle journée mon ami, maintenant ferme les yeux et fais de magnifiques rêves !'"
    )
]


async def _notify_telegram_story(title: str, text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    chat_id = os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    if not token or not chat_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            msg = f"🧒 **HISTOIRE DU SOIR RACONTÉE À ISMAIL (MAMITALES)**\n📖 **{title}**\n\n{text}"
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg[:3950]}
            )
    except Exception as e:
        logger.warning("Could not push story to Telegram: %s", e)


async def generate_mamitales_story(prompt: str, child_name: str = "Ismail", child_age: int = 5) -> str:
    """Calls Mamitales AI Service pipeline or falls back to sovereign cached tales."""
    url = f"{MAMITALES_AI_URL}/ai/stories/generate"
    clean_theme = re.sub(r"^(raconte|histoire|conte|dis-moi|je veux|une)\s*", "", prompt, flags=re.IGNORECASE).strip()
    theme = clean_theme if len(clean_theme) > 2 else "une aventure magique et rassurante"

    payload = {
        "prompt": f"Histoire merveilleuse et bienveillante pour {child_name} ({child_age} ans) sur le thème : {theme}",
        "lengthTier": "SHORT",
        "ambiance": "DOUX",
        "illustrationStyle": "PIXAR",
        "childProfile": {
            "name": child_name,
            "age": child_age,
            "interests": ["robots", "espace", "animaux"]
        }
    }

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", f"L'Aventure Magique d'{child_name}")
                chapters = data.get("chapters", [])
                full_text = " ".join([ch.get("text", "") for ch in chapters if ch.get("text")]).strip()
                if full_text:
                    await _notify_telegram_story(title, full_text)
                    return f"{title}. {full_text}"
    except Exception as e:
        logger.info("Mamitales AI service call bypassed (%s), using sovereign fallback.", e)

    # Sovereign fallback tale
    title, text = OFFLINE_ISMAIL_STORIES[0]
    await _notify_telegram_story(title, text)
    return f"{title}. {text}"


@intent
class MamitalesChildStoryIntent(BaseIntent):
    name = "mamitales_child_story"
    priority = 25
    requires_admin = False

    CHILD_KEYWORDS = [
        "histoire",
        "raconte-moi",
        "raconte moi",
        "un conte",
        "mamitales",
        "dodo",
        "bonne nuit",
        "dinosaure",
        "robot",
        "étoile",
        "etoile",
        "magie",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        # If speaker is specifically child Ismail, any story or conversation gets routed to Mamitales
        is_child = ctx.speaker is not None and ctx.speaker.role == UserRole.CHILD
        has_keywords = any(k in p for k in self.CHILD_KEYWORDS)

        return (is_child and has_keywords) or (is_child and "raconte" in p) or has_keywords

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        is_child = ctx.speaker is not None and ctx.speaker.role == UserRole.CHILD
        child_name = ctx.speaker.name if is_child else "Ismail"

        intro = f"Coucou {child_name} ! Installe-toi bien sous la couette. Régis va te raconter une belle histoire avec Mamitales."
        yield intro

        story_text = await generate_mamitales_story(ctx.prompt, child_name=child_name, child_age=5)
        yield story_text
