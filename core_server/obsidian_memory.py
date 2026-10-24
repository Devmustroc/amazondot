"""
TAD Obsidian Memory Module.
Connects Regis directly to the local Obsidian Vault (/home/devmust/Documents/obsidian).
Maintains persistent family memory, preferences, and Homelab knowledge in Markdown.
"""
import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("obsidian_memory")

class ObsidianMemory:
    def __init__(self, vault_path: str = "/home/devmust/Documents/obsidian"):
        self.vault_path = Path(vault_path)
        self.memory_dir = self.vault_path / "Memory"
        self._ensure_structure()

    def _ensure_structure(self):
        """Ensures memory directory and baseline notes exist."""
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            
            famille_file = self.memory_dir / "Famille.md"
            if not famille_file.exists():
                famille_file.write_text(
                    "# 👨‍👩‍👧‍👦 Mémoire Familiale — Profils & Foyer\n\n"
                    "- **Chef de famille** : El Mustapha\n"
                    "- **Identité de l'assistant** : Régis (membre bienveillant, poli, concis et protecteur)\n"
                    "- **Règles du foyer** : Répondre toujours en français, privilégier des phrases courtes à voix haute.\n",
                    encoding="utf-8"
                )

            prefs_file = self.memory_dir / "Preferences.md"
            if not prefs_file.exists():
                prefs_file.write_text(
                    "# 🎵 Préférences & Habitudes\n\n"
                    "- **Services musicaux** : Spotify, Tidal\n"
                    "- **Habitudes** : Météo le matin, veille des serveurs en soirée.\n",
                    encoding="utf-8"
                )

            homelab_file = self.memory_dir / "Homelab.md"
            if not homelab_file.exists():
                homelab_file.write_text(
                    "# 🖥️ Infrastructure Homelab\n\n"
                    "- **Hyperviseur** : Proxmox VE\n"
                    "- **Firewall & IDS/IPS** : OPNsense + Suricata\n"
                    "- **Domotique** : Home Assistant (lumières, capteurs, media_players)\n"
                    "- **Assistant Vocal** : Amazon Echo Dot 2G ('biscuit') piloté par TAD Core\n",
                    encoding="utf-8"
                )
            logger.info("Obsidian memory initialized at %s", self.memory_dir)
        except Exception as e:
            logger.warning("Could not initialize Obsidian structure at %s: %s", self.vault_path, e)

    def get_context_summary(self) -> str:
        """Returns a condensed string of all memory notes for LLM system prompt injection."""
        summary_lines = []
        try:
            for file in sorted(self.memory_dir.glob("*.md")):
                content = file.read_text(encoding="utf-8").strip()
                # Take key bullet points
                bullets = [line.strip() for line in content.splitlines() if line.strip().startswith("- ")]
                if bullets:
                    summary_lines.append(f"[{file.stem}] " + " | ".join(bullets[:5]))
        except Exception as e:
            logger.warning("Error reading Obsidian memory: %s", e)

        return "\n".join(summary_lines)

    def record_fact(self, category: str, fact: str):
        """Appends a new learned fact or preference into Obsidian memory."""
        try:
            cat_file = self.memory_dir / f"{category.capitalize()}.md"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"\n- [{timestamp}] {fact.strip()}"
            with open(cat_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info("Recorded new fact in %s: %s", cat_file.name, fact)
        except Exception as e:
            logger.error("Failed to record fact in Obsidian: %s", e)
