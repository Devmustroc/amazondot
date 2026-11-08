"""
Unit Tests for TAD Obsidian Memory Module & SRE Tool Integration.
"""
import unittest
import tempfile
import shutil
import asyncio
from pathlib import Path
from core_server.obsidian_memory import ObsidianMemory
from core_server.brain import Brain
from core_server.mcp_client import McpManager


class TestObsidianMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.mem = ObsidianMemory(vault_path=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_structure_initialization(self):
        """Verifies initial structure and baseline markdown files are created."""
        mem_dir = Path(self.test_dir) / "Memory"
        self.assertTrue(mem_dir.exists())
        self.assertTrue((mem_dir / "Famille.md").exists())
        self.assertTrue((mem_dir / "Homelab.md").exists())
        self.assertTrue((mem_dir / "Preferences.md").exists())

    def test_auto_categorization(self):
        """Verifies intelligent heuristic categorization of incoming facts."""
        self.assertEqual(self.mem.categorize_fact("Ismail préfère les histoires de dragons"), "Famille")
        self.assertEqual(self.mem.categorize_fact("Le conteneur Caddy tourne sur le port 443"), "Homelab")
        self.assertEqual(self.mem.categorize_fact("El Mustapha adore le café noir le matin"), "Preferences")
        self.assertEqual(self.mem.categorize_fact("Le projet Mamitales sort sur le Play Store"), "Projets")
        self.assertEqual(self.mem.categorize_fact("La clé du cadenas est dans la boîte jaune"), "Notes")

    def test_record_and_search_fact(self):
        """Tests recording facts into Obsidian and retrieving them by keyword."""
        # 1. Record fact
        res = self.mem.record_fact(fact="Ismail a cours de natation tous les samedis matin à 10h")
        self.assertTrue(res["success"])
        self.assertEqual(res["category"], "Famille")

        # Check file content
        content = (Path(self.test_dir) / "Memory" / "Famille.md").read_text(encoding="utf-8")
        self.assertIn("natation tous les samedis", content)

        # 2. Search fact
        search_res = self.mem.search_memory("cours de natation")
        self.assertGreaterEqual(len(search_res), 1)
        self.assertIn("natation", search_res[0]["text"].lower())

    def test_recall_spoken(self):
        """Tests spoken summary generation for voice queries."""
        self.mem.record_fact(fact="Le mot de passe du wifi invité est bienvenue2026")
        spoken = self.mem.recall_memory_spoken("Régis, quel est le wifi invité ?")
        self.assertIn("bienvenue2026", spoken)

        unknown_spoken = self.mem.recall_memory_spoken("Quelle est la marque de la tondeuse ?")
        self.assertIn("Je n'ai pas trouvé d'information", unknown_spoken)

    def test_relevant_context_injection(self):
        """Tests dynamic context retrieval for LLM prompts."""
        self.mem.record_fact(fact="Suricata analyse tout le trafic sur l'interface vmbr0")
        ctx = self.mem.get_relevant_context("Est-ce que Suricata est configuré ?")
        self.assertIn("Suricata", ctx)


class TestAsyncBrainMemoryIntents(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.brain = Brain()
        self.brain.obsidian = ObsidianMemory(vault_path=self.test_dir)

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_brain_learning_intent(self):
        """Tests voice order 'Régis, retiens que...'"""
        responses = []
        async for chunk in self.brain.generate_response_stream("Régis, retiens que Ismail adore jouer aux échecs"):
            responses.append(chunk)

        full_reply = " ".join(responses)
        self.assertIn("C'est bien noté dans ma mémoire", full_reply)
        self.assertIn("Ismail adore jouer aux échecs", full_reply)

        # Verify fact was recorded in Obsidian
        famille_content = (Path(self.test_dir) / "Memory" / "Famille.md").read_text(encoding="utf-8")
        self.assertIn("Ismail adore jouer aux échecs", famille_content)

    async def test_brain_recall_intent(self):
        """Tests voice recall order 'Régis, que sais-tu sur...'"""
        self.brain.obsidian.record_fact(fact="Ismail adore jouer aux échecs")

        responses = []
        async for chunk in self.brain.generate_response_stream("Régis, que sais-tu sur les échecs ?"):
            responses.append(chunk)

        full_reply = " ".join(responses)
        self.assertIn("échecs", full_reply)


if __name__ == "__main__":
    unittest.main()
