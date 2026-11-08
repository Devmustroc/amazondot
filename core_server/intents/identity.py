"""
Assistant Identity and VoiceID biometric query intents.
"""
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server import config


@intent
class AssistantIdentityIntent(BaseIntent):
    name = "assistant_identity"
    priority = 10

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return any(k in p for k in ["qui es-tu", "comment tu t'appelles", "présente-toi", "t'es qui"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        name = getattr(config, "ASSISTANT_NAME", "Régis")
        admin = getattr(config, "FAMILY_ADMIN_NAME", "El Mustapha")
        yield f"Je m'appelle {name}, je suis l'assistant vocal IA familial pour la maison de {admin}."


@intent
class VoiceIDWhoAmIIntent(BaseIntent):
    name = "voiceid_whoami"
    priority = 10

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return any(k in p for k in ["qui suis-je", "qui est-ce qui parle", "qui parle", "reconnais-tu ma voix", "tu reconnais ma voix"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        name = getattr(ctx.speaker, "name", "Utilisateur")
        role_val = getattr(ctx.speaker.role, "value", str(ctx.speaker.role))
        yield f"D'après ton empreinte vocale, tu es {name}, avec le profil {role_val}."
