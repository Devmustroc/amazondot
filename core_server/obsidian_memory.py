"""
TAD Obsidian Memory Module.
Connects Regis directly to the local Obsidian Vault (/home/devmust/Documents/obsidian).
Maintains persistent family memory, preferences, and Homelab knowledge in structured Markdown.
Provides semantic keyword search and dynamic prompt context retrieval.
"""
import os
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("obsidian_memory")

STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "en", "à", "a",
    "au", "aux", "pour", "par", "sur", "dans", "avec", "sans", "est", "sont",
    "que", "qui", "quoi", "dont", "où", "mon", "ma", "mes", "ton", "ta", "tes",
    "son", "sa", "ses", "notre", "votre", "leur", "ce", "cet", "cette", "ces",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "et", "ou", "mais",
    "donc", "or", "ni", "car", "ne", "pas", "plus", "très", "tout", "tous", "toute"
}

CATEGORY_RULES = {
    "Homelab": [
        "proxmox", "docker", "conteneur", "container", "port", "caddy", "suricata",
        "lxc", "vm", "ip", "serveur", "réseau", "reseau", "opnsense", "adguard",
        "ct", "homelab", "paperless", "immich", "vaultwarden", "ssh", "routeur"
    ],
    "Famille": [
        "mustapha", "ismail", "papa", "maman", "enfant", "enfants", "fils", "fille",
        "anniversaire", "famille", "maison", "chambre", "école", "ecole", "repas", "foyer"
    ],
    "Preferences": [
        "café", "cafe", "thé", "the", "jazz", "musique", "spotify", "tidal", "aime",
        "adore", "déteste", "deteste", "préfère", "prefere", "veille", "sommeil", "lit",
        "heure", "réveil", "reveil", "température", "temperature", "habitude"
    ],
    "Projets": [
        "mamitales", "visor", "tad", "stremio", "streamvault", "code", "git", "release",
        "bug", "ticket", "linear", "notion", "github", "commit", "build", "flutter", "dart"
    ],
}


class ObsidianMemory:
    def __init__(self, vault_path: Optional[str] = None):
        env_vault = os.getenv("OBSIDIAN_VAULT_PATH")
        default_vault = Path(__file__).resolve().parent.parent / "vault"
        
        self.vault_path = Path(vault_path or env_vault or default_vault)
        if self.vault_path.name.lower() == "memory":
            self.memory_dir = self.vault_path
        else:
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
                    "- **Hyperviseur** : Proxmox VE (192.168.1.200)\n"
                    "- **Firewall & IDS/IPS** : OPNsense + Suricata\n"
                    "- **Domotique** : Home Assistant (lumières, capteurs, media_players)\n"
                    "- **Assistant Vocal** : Amazon Echo Dot 2G ('biscuit') piloté par TAD Core\n",
                    encoding="utf-8"
                )

            notes_file = self.memory_dir / "Notes.md"
            if not notes_file.exists():
                notes_file.write_text(
                    "# 📝 Notes Diverses & Savoirs\n\n",
                    encoding="utf-8"
                )

            logger.info("Obsidian memory initialized at %s", self.memory_dir)
        except Exception as e:
            logger.warning("Could not initialize Obsidian structure at %s: %s", self.vault_path, e)

    def categorize_fact(self, fact: str) -> str:
        """Determines the most appropriate Markdown category note for a given fact."""
        t_lower = fact.lower()
        scores: Dict[str, int] = {}
        for cat, keywords in CATEGORY_RULES.items():
            count = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw) + r'\b', t_lower))
            if count > 0:
                scores[cat] = count

        if scores:
            return max(scores, key=scores.get)
        return "Notes"

    def record_fact(self, category: Optional[str] = None, fact: str = "") -> Dict[str, Any]:
        """
        Records a newly learned fact with timestamp into the target Obsidian note.
        Automatically infers category if not provided or if generic.
        """
        fact_clean = fact.strip()
        if not fact_clean:
            return {"success": False, "error": "Empty fact"}

        if not category or category.lower() in ["famille", "général", "general", "default", "none"]:
            inferred_cat = self.categorize_fact(fact_clean)
            target_category = inferred_cat if inferred_cat != "Notes" else (category or "Famille")
        else:
            target_category = category

        target_file = self.memory_dir / f"{target_category.capitalize()}.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{timestamp}] {fact_clean}"

        try:
            with open(target_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info("Recorded fact in %s: %s", target_file.name, fact_clean)
            return {
                "success": True,
                "category": target_category.capitalize(),
                "file": str(target_file),
                "fact": fact_clean,
                "timestamp": timestamp
            }
        except Exception as e:
            logger.error("Failed to record fact in Obsidian: %s", e)
            return {"success": False, "error": str(e)}

    def search_memory(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Scans all Markdown memory files and ranks bullet entries using token relevance.
        Returns top matching items with category and score.
        """
        tokens = [w for w in re.findall(r'\b\w+\b', query.lower()) if len(w) >= 3 and w not in STOPWORDS_FR]
        if not tokens:
            return []

        results = []
        try:
            for file in sorted(self.memory_dir.glob("*.md")):
                cat_name = file.stem
                content = file.read_text(encoding="utf-8")
                lines = content.splitlines()

                for line in lines:
                    line_clean = line.strip()
                    if not line_clean.startswith("- "):
                        continue

                    # Strip bullet prefix
                    entry_text = line_clean[2:].strip()
                    # Strip leading timestamp [YYYY-MM-DD HH:MM] if present
                    text_without_ts = re.sub(r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*', '', entry_text)

                    entry_lower = text_without_ts.lower()
                    score = 0
                    for token in tokens:
                        if token in entry_lower:
                            score += 1.0
                            # Bonus for exact word boundary match
                            if re.search(r'\b' + re.escape(token) + r'\b', entry_lower):
                                score += 0.5

                    if score > 0:
                        results.append({
                            "category": cat_name,
                            "raw_entry": entry_text,
                            "text": text_without_ts,
                            "score": score
                        })

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.warning("Error searching memory: %s", e)
            return []

    def get_relevant_context(self, query: str, max_items: int = 5) -> str:
        """
        Returns relevant memory bullet points scored against the active query.
        Falls back to baseline summary if no high-confidence matches are found.
        """
        matches = self.search_memory(query, top_k=max_items)
        if matches and matches[0]["score"] >= 1.0:
            lines = [f"[{m['category']}] {m['text']}" for m in matches]
            return "Faits mémorisés pertinents pour cette requête :\n" + "\n".join(lines)
        return self.get_context_summary()

    def recall_memory_spoken(self, query: str) -> str:
        """
        Generates a natural French spoken response to a memory recall request.
        Example queries: 'Régis, que sais-tu sur Ismail ?', 'Régis, rappelle-moi ce que j'ai dit sur le wifi'.
        """
        # Clean query: strip trigger prefixes
        clean_q = re.sub(
            r'^(que\s+sais-tu\s+sur|qu\'est-ce\s+que\s+tu\s+sais\s+sur|rappelle-moi\s+(ce\s+que\s+j\'ai\s+dit\s+sur|sur)?|parle-moi\s+de)\s*',
            '', query.strip(), flags=re.IGNORECASE
        ).strip() or query.strip()

        matches = self.search_memory(clean_q, top_k=3)
        if not matches or matches[0]["score"] < 1.0:
            return f"Je n'ai pas trouvé d'information mémorisée concernant {clean_q} dans mon coffre Obsidian."

        if len(matches) == 1:
            m = matches[0]
            clean_fact = re.sub(r'^\*\*[^*]+\*\*\s*:\s*', '', m['text'])
            return f"D'après mes notes dans {m['category']} : {clean_fact}."

        phrases = [re.sub(r'^\*\*[^*]+\*\*\s*:\s*', '', m['text']) for m in matches[:2]]
        return f"Voici ce que j'ai en mémoire : premièrement, {phrases[0]} ; et aussi, {phrases[1]}."

    def get_context_summary(self) -> str:
        """Returns baseline memory notes for system prompt injection."""
        summary_lines = []
        try:
            for file in sorted(self.memory_dir.glob("*.md")):
                content = file.read_text(encoding="utf-8").strip()
                bullets = [line.strip()[2:] for line in content.splitlines() if line.strip().startswith("- ")]
                if bullets:
                    # Clean timestamps from bullets for prompt readability
                    clean_bullets = [re.sub(r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*', '', b) for b in bullets[:4]]
                    summary_lines.append(f"[{file.stem}] " + " | ".join(clean_bullets))
        except Exception as e:
            logger.warning("Error reading Obsidian memory: %s", e)

        return "\n".join(summary_lines)
