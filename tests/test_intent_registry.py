"""
Unit tests for SovereignDot Decoupled Intent Registry Subsystem.
Tests dynamic intent registration, priority resolution, and RBAC enforcement.
"""
import unittest
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent
from core_server.intents.registry import IntentRegistry
from core_server.voice_id import SpeakerProfile, UserRole


class TestIntentRegistrySubsystem(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.registry = IntentRegistry()
        self.admin = SpeakerProfile(name="Mustapha", role=UserRole.ADMIN, f0_mean_hz=125.0, spectral_centroid_hz=1400.0)
        self.child = SpeakerProfile(name="Ismail", role=UserRole.CHILD, f0_mean_hz=320.0, spectral_centroid_hz=2900.0)

    async def test_builtin_intents_registered(self):
        """Verify built-in intents (time, date, identity, memory, homelab, resilience) are registered."""
        intent_names = [i.name for i in self.registry._intents]
        self.assertIn("time", intent_names)
        self.assertIn("date", intent_names)
        self.assertIn("assistant_identity", intent_names)
        self.assertIn("voiceid_whoami", intent_names)
        self.assertIn("memory_learn", intent_names)
        self.assertIn("memory_recall", intent_names)
        self.assertIn("proxmox_status", intent_names)
        self.assertIn("docker_status", intent_names)
        self.assertIn("paperless_legal_advisor", intent_names)
        self.assertIn("network_resilience", intent_names)

    async def test_time_intent_execution(self):
        """Verify TimeIntent handles query and yields formatted time."""
        ctx = IntentContext(
            prompt="Régis, quelle heure est-il ?",
            clean_prompt="quelle heure est-il",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None
        )
        gen = await self.registry.handle_prompt(ctx)
        self.assertIsNotNone(gen)
        responses = [r async for r in gen]
        self.assertEqual(len(responses), 1)
        self.assertIn("Il est actuellement", responses[0])

    async def test_custom_plugin_intent_registration(self):
        """Verify adding a 3rd-party voice skill dynamically via @intent."""
        class WeatherSkill(BaseIntent):
            name = "custom_weather"
            priority = 5

            def can_handle(self, ctx: IntentContext) -> bool:
                return "météo" in ctx.prompt.lower()

            async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
                yield "Il fait 21 degrés avec un grand soleil."

        custom_registry = IntentRegistry()
        custom_registry.register(WeatherSkill())

        ctx = IntentContext(
            prompt="Donne-moi la météo",
            clean_prompt="météo",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None
        )
        gen = await custom_registry.handle_prompt(ctx)
        self.assertIsNotNone(gen)
        res = [r async for r in gen]
        self.assertEqual(res[0], "Il fait 21 degrés avec un grand soleil.")

    async def test_rbac_child_denial_on_protected_intent(self):
        """Verify child speaker is denied access to intents with requires_admin=True."""
        ctx = IntentContext(
            prompt="Régis, quel est l'état du serveur Proxmox ?",
            clean_prompt="quel est l'état du serveur proxmox",
            speaker=self.child,
            obsidian=None,
            circuit_breaker=None
        )
        gen = await self.registry.handle_prompt(ctx)
        self.assertIsNotNone(gen)
        res = [r async for r in gen]
        self.assertIn("Désolé Ismail", res[0])
        self.assertIn("réservé aux adultes", res[0])

    async def test_paperless_legal_advisor_intent(self):
        """Verify PaperlessLegalAdvisorIntent answers contract queries for admin and blocks child."""
        admin_ctx = IntentContext(
            prompt="Régis, quel est mon préavis dans mon contrat de travail ?",
            clean_prompt="quel est mon préavis dans mon contrat de travail",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen = await self.registry.handle_prompt(admin_ctx)
        self.assertIsNotNone(gen)
        res = [r async for r in gen]
        self.assertIn("préavis est d'un mois", res[0])
        self.assertIn("Telegram", res[0])

        child_ctx = IntentContext(
            prompt="Régis, montre-moi les fiches de paie dans Paperless",
            clean_prompt="montre-moi les fiches de paie dans paperless",
            speaker=self.child,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_child = await self.registry.handle_prompt(child_ctx)
        self.assertIsNotNone(gen_child)
        res_child = [r async for r in gen_child]
        self.assertIn("Désolé Ismail", res_child[0])
        self.assertIn("réservé aux adultes", res_child[0])


if __name__ == "__main__":
    unittest.main()
