"""
Obsidian Memory intents for voice fact learning and spoken recall.
"""
import re
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent


@intent
class MemoryLearnIntent(BaseIntent):
    name = "memory_learn"
    priority = 15

    def can_handle(self, ctx: IntentContext) -> bool:
        return bool(re.search(r'(retiens que|souviens-toi que|note que|enregistre que|n\'oublie pas que)\s+(.*)', ctx.clean_prompt, flags=re.IGNORECASE))

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        m = re.search(r'(retiens que|souviens-toi que|note que|enregistre que|n\'oublie pas que)\s+(.*)', ctx.clean_prompt, flags=re.IGNORECASE)
        fact_text = m.group(2).strip()
        res = ctx.obsidian.record_fact(fact=fact_text)
        cat = res.get("category", "Famille")
        yield f"C'est bien noté dans ma mémoire {cat}, j'ai enregistré que {fact_text}."


@intent
class MemoryRecallIntent(BaseIntent):
    name = "memory_recall"
    priority = 15

    def can_handle(self, ctx: IntentContext) -> bool:
        return bool(re.search(r'^(que\s+sais-tu\s+sur|qu\'est-ce\s+que\s+tu\s+sais\s+sur|rappelle-moi\s+(ce\s+que\s+j\'ai\s+dit\s+sur|sur)?|parle-moi\s+de)\s*(.*)', ctx.clean_prompt.lower(), flags=re.IGNORECASE))

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        m = re.search(r'^(que\s+sais-tu\s+sur|qu\'est-ce\s+que\s+tu\s+sais\s+sur|rappelle-moi\s+(ce\s+que\s+j\'ai\s+dit\s+sur|sur)?|parle-moi\s+de)\s*(.*)', ctx.clean_prompt.lower(), flags=re.IGNORECASE)
        topic = m.group(len(m.groups())).strip()
        topic = re.sub(r'[.?!\s]+$', '', topic).strip()
        if len(topic) >= 2:
            yield ctx.obsidian.recall_memory_spoken(topic)
        else:
            yield "De quel sujet souhaites-tu que je me rappelle ?"
