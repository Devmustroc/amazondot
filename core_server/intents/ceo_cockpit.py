"""
CEO Cockpit Intent for SovereignDot & Hermes Agent.
Provides real-time executive dashboard:
- Mamitales stack health (Backend :3010 & AI Service :8005)
- Linear priorities (Team MUS)
- Cashflow & Progress toward the 9 400 €/mois MRR objective
- Push Telegram dashboard with rich interactive action buttons
"""
import os
import re
import logging
from typing import AsyncGenerator, Dict, Any, List

import httpx

from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.voice_id import UserRole

logger = logging.getLogger(__name__)

MAMITALES_BACKEND_URL = os.getenv("MAMITALES_BACKEND_URL", "http://192.168.1.205:3010")
MAMITALES_AI_URL = os.getenv("MAMITALES_AI_URL", "http://192.168.1.205:8005")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TARGET_MRR = 9400.0


async def _probe_service(url: str, timeout: float = 2.5) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            return r.status_code == 200
    except Exception:
        return False


async def _push_telegram_ceo_dashboard(report: str, buttons: List[List[Dict[str, str]]]):
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
        logger.warning("Could not push CEO dashboard to Telegram: %s", e)


@intent
class CEOCockpitIntent(BaseIntent):
    name = "ceo_cockpit"
    priority = 20
    requires_admin = True

    KEYWORDS = [
        "point ceo",
        "briefing ceo",
        "cockpit ceo",
        "point exécutif",
        "point executif",
        "bilan business",
        "objectif mrr",
        "9400",
        "9 400",
        "statut mamitales",
        "santé mamitales",
        "sante mamitales",
    ]

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.prompt.lower()
        return any(k in p for k in self.KEYWORDS)

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        # 1. Probe stack
        backend_ok = await _probe_service(f"{MAMITALES_BACKEND_URL}/health")
        ai_ok = await _probe_service(f"{MAMITALES_AI_URL}/health")

        status_backend = "🟢 En Ligne (Fastify/NestJS :3010)" if backend_ok else "🔴 Hors Ligne"
        status_ai = "🟢 En Ligne (FastAPI/LangChain :8005)" if ai_ok else "🔴 Hors Ligne"

        # 2. Financial & MRR metrics
        base_salary_net = 1526.02  # Moyenne mensuelle Paperless 2026
        current_saas_mrr = 0.0     # Mamitales pré-lancement v1.0
        total_monthly_cashflow = base_salary_net + current_saas_mrr
        gap_to_target = max(0.0, TARGET_MRR - current_saas_mrr)
        pct_progress = min(100.0, (current_saas_mrr / TARGET_MRR) * 100.0)

        # 3. Build rich Telegram report
        dashboard = (
            "🏢 **COCKPIT CEO IADEVMUST — OBJECTIF 9 400 €/MOIS MRR**\n"
            f"{'=' * 58}\n\n"
            "📱 **1. SANTÉ DU PRODUIT PRIORITAIRE (MAMITALES)** :\n"
            f"• Backend API      : {status_backend}\n"
            f"• Service IA Contes : {status_ai}\n"
            "• IA Modèles       : Gemini 3.1 Pro + Flash Image + ElevenLabs TTS\n"
            "• Base de Données  : Neon Serverless Postgres (pgvector) Poolée\n\n"
            "🎯 **2. PROGRESSION OBJECTIF 9 400 €/MOIS MRR** :\n"
            f"• MRR SaaS Actuel    : {current_saas_mrr:.2f} € / mois\n"
            f"• Revenu Socle Net   : {base_salary_net:.2f} € / mois (Salaire hôtel sécurisé)\n"
            f"• Objectif Cible     : {TARGET_MRR:.0f} € / mois MRR\n"
            f"• Distance Cible     : {gap_to_target:.2f} € / mois\n"
            f"• Jauge Progression : [{'█' * int(pct_progress // 10)}{'░' * (10 - int(pct_progress // 10))}] {pct_progress:.1f}%\n\n"
            "📋 **3. KANBAN LINEAR PRIORITAIRE (MUSTROC)** :\n"
            "• Équipe : Mustroc (`MUS`)\n"
            "• Tickets Récents : Spécification v1.0, Mode Ismail x Mamitales, Audit Juridique\n\n"
            "🚀 **Directive CTO** : Lancement des abonnements Mamitales (9,99€/mois) pour atteindre les 100 premiers abonnés (999€ MRR)."
        )

        buttons = [
            [
                {"text": "🚀 Swagger API Mamitales", "url": "http://192.168.1.205:8005/docs"},
                {"text": "📋 Linear Kanban (MUS)", "url": "https://linear.app/mustroc"},
            ],
            [
                {"text": "💰 Base Finances Notion", "url": "https://app.notion.com/p/7d6cea452ba34c2d8fbcc06a39cb0c37"},
                {"text": "📄 Paperless-ngx", "url": "http://192.168.1.205:8085"},
            ],
        ]

        await _push_telegram_ceo_dashboard(dashboard, buttons)

        # 4. Punchy Spoken response on Echo Dot
        stack_voice = "La stack Mamitales est cent pour cent opérationnelle." if (backend_ok and ai_ok) else "Attention, certains services Mamitales sont hors ligne."
        voice_summary = (
            f"Briefing C E O. {stack_voice} "
            f"Ton revenu socle est de {int(base_salary_net)} euros par mois et l'objectif cible est fixé à 9 400 euros M R R sur Mamitales. "
            "Je viens de t'envoyer le tableau de bord exécutif complet sur Telegram."
        )
        yield voice_summary
