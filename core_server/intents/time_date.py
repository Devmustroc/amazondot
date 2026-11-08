"""
Time and Date voice intents.
Provides instant 0ms responses for clock and calendar queries.
"""
from datetime import datetime
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent


@intent
class TimeIntent(BaseIntent):
    name = "time"
    priority = 10

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return any(k in p for k in ["heure est-il", "l'heure", "il est quelle heure", "donne-moi l'heure", "donne l'heure"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        now = datetime.now()
        h, m = now.hour, now.minute
        m_str = "pile" if m == 0 else f"{m:02d}" if m < 10 else str(m)
        h_str = f"{h} heure{'s' if h > 1 else ''}"
        yield f"Il est actuellement {h_str} {m_str}."


@intent
class DateIntent(BaseIntent):
    name = "date"
    priority = 10

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return any(k in p for k in ["quel jour", "la date", "date d'aujourd'hui", "on est quel jour"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        now = datetime.now()
        jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
        yield f"Nous sommes le {jours[now.weekday()]} {now.day} {mois[now.month - 1]} {now.year}."
