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

    async def test_paperless_caf_and_tax_and_demo_intents(self):
        """Verify CAF prime d'activité, tax optimizer, and demo mode answers."""
        # 1. CAF
        caf_ctx = IntentContext(
            prompt="Régis, calcule ma prime d'activité CAF pour le trimestre",
            clean_prompt="calcule ma prime d'activité caf pour le trimestre",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_caf = await self.registry.handle_prompt(caf_ctx)
        self.assertIsNotNone(gen_caf)
        res_caf = [r async for r in gen_caf]
        self.assertIn("C A F", res_caf[0])
        self.assertIn("net social", res_caf[0])

        # 2. Tax Optimizer
        tax_ctx = IntentContext(
            prompt="Régis, lance l'optimisation fiscale de mes impôts",
            clean_prompt="lance l'optimisation fiscale de mes impôts",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_tax = await self.registry.handle_prompt(tax_ctx)
        self.assertIsNotNone(gen_tax)
        res_tax = [r async for r in gen_tax]
        self.assertIn("frais réels", res_tax[0])

        # 3. Demo Mode
        demo_ctx = IntentContext(
            prompt="Régis, passe en mode démo pour la vidéo",
            clean_prompt="passe en mode démo pour la vidéo",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_demo = await self.registry.handle_prompt(demo_ctx)
        self.assertIsNotNone(gen_demo)
        res_demo = [r async for r in gen_demo]
        self.assertIn("Mode Démo activé", res_demo[0])
        self.assertIn("Régis", res_demo[0])

    async def test_mamitales_child_story_intent(self):
        """Verify Ismail (CHILD) voice prompt triggers Mamitales story routing."""
        child_ctx = IntentContext(
            prompt="Régis, raconte-moi une histoire de robot",
            clean_prompt="raconte-moi une histoire de robot",
            speaker=self.child,
            obsidian=None,
            circuit_breaker=None,
        )
        gen = await self.registry.handle_prompt(child_ctx)
        self.assertIsNotNone(gen)
        res = [r async for r in gen]
        self.assertTrue(len(res) >= 2)
        self.assertIn("Coucou Ismail", res[0])
        self.assertIn("Mamitales", res[0])
        self.assertTrue("Ismail" in res[1] or "robot" in res[1].lower())

    async def test_shift_aware_night_routine_intent(self):
        """Verify night shift routine: departure at 21h30, sleep mode at 07h20, and watchdog."""
        # Departure
        dep_ctx = IntentContext(
            prompt="Régis, je pars au travail à l'hôtel",
            clean_prompt="je pars au travail à l'hôtel",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_dep = await self.registry.handle_prompt(dep_ctx)
        self.assertIsNotNone(gen_dep)
        res_dep = [r async for r in gen_dep]
        self.assertIn("Bonne garde", res_dep[0])
        self.assertIn("Ilévia", res_dep[0])

        # Return & Sleep
        ret_ctx = IntentContext(
            prompt="Régis, je rentre du travail, je vais dormir",
            clean_prompt="je rentre du travail je vais dormir",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_ret = await self.registry.handle_prompt(ret_ctx)
        self.assertIsNotNone(gen_ret)
        res_ret = [r async for r in gen_ret]
        self.assertIn("Bon retour", res_ret[0])
        self.assertIn("mode silence réparateur", res_ret[0])

    async def test_stop_playback_intent(self):
        """Verify instantaneous stop intent (priority=1)."""
        stop_ctx = IntentContext(
            prompt="Régis, stop !",
            clean_prompt="stop",
            speaker=self.child,
            obsidian=None,
            circuit_breaker=None,
        )
        gen = await self.registry.handle_prompt(stop_ctx)
        self.assertIsNotNone(gen)
        res = [r async for r in gen]
        self.assertIn("je m'arrête", res[0])

    async def test_sprint_3_ceo_and_lead_dev_intents(self):
        """Verify CEO Cockpit, Voice-to-PR, CI Watchdog, and SaaS Scout intents."""
        # 1. CEO Cockpit
        ceo_ctx = IntentContext(
            prompt="Régis, fais-moi le point CEO pour les 9400 euros MRR",
            clean_prompt="fais-moi le point ceo pour les 9400 euros mrr",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_ceo = await self.registry.handle_prompt(ceo_ctx)
        self.assertIsNotNone(gen_ceo)
        res_ceo = [r async for r in gen_ceo]
        self.assertIn("C E O", res_ceo[0])
        self.assertIn("Mamitales", res_ceo[0])

        # 2. Voice-to-PR
        pr_ctx = IntentContext(
            prompt="Régis, ouvre une branche pour corriger le bug de login",
            clean_prompt="ouvre une branche pour corriger le bug de login",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_pr = await self.registry.handle_prompt(pr_ctx)
        self.assertIsNotNone(gen_pr)
        res_pr = [r async for r in gen_pr]
        self.assertIn("feat/voice-", res_pr[0])
        self.assertIn("Telegram", res_pr[0])

        # 3. CI Watchdog
        ci_ctx = IntentContext(
            prompt="Régis, quel est l'état du watchdog CI ?",
            clean_prompt="quel est l'état du watchdog ci",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_ci = await self.registry.handle_prompt(ci_ctx)
        self.assertIsNotNone(gen_ci)
        res_ci = [r async for r in gen_ci]
        self.assertIn("watchdog C I C D", res_ci[0])

        # 4. SaaS Scout
        scout_ctx = IntentContext(
            prompt="Régis, lance la veille concurrentielle et idées SaaS",
            clean_prompt="lance la veille concurrentielle et idées saas",
            speaker=self.admin,
            obsidian=None,
            circuit_breaker=None,
        )
        gen_scout = await self.registry.handle_prompt(scout_ctx)
        self.assertIsNotNone(gen_scout)
        res_scout = [r async for r in gen_scout]
        self.assertIn("Veille concurrentielle terminée", res_scout[0])


if __name__ == "__main__":
    unittest.main()
