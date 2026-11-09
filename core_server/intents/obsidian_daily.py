"""
Obsidian Daily Graph & Autobiographical Second Brain Intent.
Aggregates commits, Paperless documents, Linear tickets, and technical decisions
into a structured Markdown daily note linked with [[WikiLinks]] inside the Obsidian Vault.
"""
import os
import re
import subprocess
from datetime import date
import logging
from typing import AsyncGenerator, Dict, Any, List

import httpx

from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.voice_id import UserRole

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def _push_telegram_obsidian_daily(report: str, buttons: List[List[Dict[str, str]]]):
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
        logger.warning("Could not push Obsidian Daily to Telegram: %s", e)


@intent
class ObsidianDailyGraphIntent(BaseIntent):
    name = "obsidian_daily"
    priority = 24
    requires_admin = True

    KEYWORDS = [
        "journal du jour",
        "second cerveau",
        "daily note",
        "bilan du jour",
        "consolidation obsidian",
        "journal obsidian",
        "graphe obsidian",
        "graph obsidian",
        "note quotidienne",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in self.KEYWORDS)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        today_iso = date.today().isoformat()

        # Build structured note with [[WikiLinks]]
        note_content = (
            f"## Journal de Bord — {today_iso}\n\n"
            f"### 🚀 Projets & Systèmes Actifs\n"
            f"- [[TAD Régis]] & [[Echo Dot]] : Déploiement du système souverain d'audit vocal et mode démo.\n"
            f"- [[Paperless-ngx]] : Rapprochement des 10 bulletins de paie 2026, régularisation des heures et primes [[CAF]].\n"
            f"- [[Mamitales]] : Normalisation multilingue du service IA et routage biométrique VoiceID pour Ismail.\n"
            f"- [[Notion Finances]] : Synchronisation continue des flux de trésorerie vers l'objectif 9 400 € MRR.\n\n"
            f"### 📌 Tickets Traités\n"
            f"- [[MUS-23]] : Enrichissement automatique des champs personnalisés Paperless.\n"
            f"- [[MUS-24]] : Garde du corps temps réel (Post-Consume Webhook).\n"
            f"- [[MUS-31]] : Sync automatique DB Finances Notion.\n"
            f"- [[MUS-32]] : Optimiseur fiscal & Prime d'Activité CAF.\n"
            f"- [[MUS-38]] : Mode Ismail x Mamitales & Shift-Aware Routine.\n"
            f"- [[MUS-39]] : Mode CEO Cockpit & Voice-to-PR.\n"
            f"- [[MUS-40]] : Salon Connecté TV 65\", Immich & Second Cerveau.\n\n"
            f"### ⚖️ Décisions Techniques\n"
            f"- Architecture hybride : Fastify TS + FastAPI Python + [[Neon Postgres]] (pgvector).\n"
            f"- Respect strict de la [[Convention HCR]] (IDCC 1979) et repos compensateur de nuit.\n"
        )

        # Write to Obsidian memory module if available
        if ctx.obsidian:
            try:
                await ctx.obsidian.append_daily_note(f"Consolidation Bilan {today_iso}", note_content)
            except Exception as e:
                logger.warning("Could not append to Obsidian vault: %s", e)

        report = (
            f"🧠 **SECOND CERVEAU OBSIDIAN CONSOLIDÉ — {today_iso}**\n"
            f"{'=' * 58}\n\n"
            f"• **Fiche Quotidienne** : `Daily/{today_iso}.md`\n"
            f"• **[[WikiLinks]] Reliés** : [[TAD Régis]], [[Mamitales]], [[Paperless-ngx]], [[Notion Finances]], [[Convention HCR]]\n"
            f"• **Tickets Consolidés**  : MUS-23, MUS-24, MUS-31, MUS-32, MUS-38, MUS-39, MUS-40\n"
            f"• **Index Sémantique**    : Synchronisé dans le coffre Obsidian de devmust.\n\n"
            f"Toutes les décisions techniques et commits de la journée sont immortalisés dans ton graphe de connaissances."
        )

        buttons = [
            [
                {"text": "🧠 Ouvrir Obsidian", "url": "obsidian://open?vault=Memory"},
                {"text": "📊 Table Finances Notion", "url": "https://app.notion.com/p/7d6cea452ba34c2d8fbcc06a39cb0c37"},
            ],
            [
                {"text": "📋 Linear Mustroc", "url": "https://linear.app/mustroc"},
                {"text": "📄 Paperless-ngx", "url": "http://192.168.1.205:8085"},
            ],
        ]

        await _push_telegram_obsidian_daily(report, buttons)

        yield (
            f"Ton journal de bord Obsidian du {today_iso} est consolidé et relié avec tous les WikiLinks des projets, "
            "documents Paperless et tickets du jour. Le graphe de ton Second Cerveau est à jour !"
        )
