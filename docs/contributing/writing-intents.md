# Tutoriel : Créer une Intention Vocale (@intent)

Grâce au registre modulaire d'intentions de SovereignDot ([`core_server/intents/`](file:///home/devmust/Work/amazondot/core_server/intents/)), ajouter une nouvelle compétence vocale ne nécessite plus de modifier le cœur du serveur !  
Il vous suffit de créer un nouveau fichier Python dans le dossier `core_server/intents/` et d'utiliser le décorateur `@intent`.

---

## 🏗️ Anatomie d'un Handler d'Intention

Toute compétence vocale hérite de `BaseIntent` et implémente deux méthodes obligatoires :
1. **`can_handle(ctx: IntentContext) -> bool`** : Détermine si l'intention doit intercepter la phrase prononcée par l'utilisateur.
2. **`execute(ctx: IntentContext) -> AsyncGenerator[str, None]`** : Générateur asynchrone qui produit la ou les phrases de réponse parlée.

```python
from typing import AsyncGenerator
from core_server.intents.base import BaseIntent, IntentContext, intent

@intent
class MonSkillIntent(BaseIntent):
    name = "mon_skill"
    priority = 25              # Priorité (plus le nombre est bas, plus la priorité est haute)
    requires_admin = False     # Mettre à True pour exiger les droits administrateur

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return "blague" in p

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        yield "Pourquoi les plongeurs plongent-ils toujours en arrière et jamais en avant ? Parce que sinon ils tombent dans le bateau !"
```

---

## 🔍 Le Contexte d'Exécution `IntentContext`

L'objet `ctx` injecté dans vos méthodes met à votre disposition toutes les informations et services utiles :

```python
@dataclass
class IntentContext:
    prompt: str             # Phrase vocale brute prononcée par l'utilisateur
    clean_prompt: str       # Phrase nettoyée du mot-clé de réveil ("Régis", "Alexa", etc.)
    speaker: SpeakerProfile # Profil biométrique identifié (name, role, f0_mean_hz)
    obsidian: ObsidianMemory# Instance de mémoire Markdown (record_fact, recall_memory_spoken)
    circuit_breaker: Any    # État du disjoncteur réseau (is_cloud_available, get_status)
    mcp: Optional[Any]      # Gestionnaire d'outils MCP pour interagir avec le Homelab
```

---

## 💡 Exemple Complet : Contrôler des Lampes Zigbee / Home Assistant

Voici un exemple concret de skill pour allumer ou éteindre les lumières du salon :

```python
# core_server/intents/home_assistant.py
import re
from typing import AsyncGenerator
import aiohttp
from core_server.intents.base import BaseIntent, IntentContext, intent

@intent
class LightControlIntent(BaseIntent):
    name = "light_control"
    priority = 15
    requires_admin = False

    def can_handle(self, ctx: IntentContext) -> bool:
        p = ctx.clean_prompt.lower()
        return any(k in p for k in ["allume le salon", "éteins le salon", "lumière du salon"])

    async def execute(self, ctx: IntentContext) -> AsyncGenerator[str, None]:
        p = ctx.clean_prompt.lower()
        action = "turn_on" if "allume" in p else "turn_off"
        
        # Appel vers l'API Home Assistant locale
        url = f"http://homeassistant.local:8123/api/services/light/{action}"
        headers = {"Authorization": "Bearer VOTRE_TOKEN_LONG_LIVED"}
        payload = {"entity_id": "light.salon"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=2.0) as resp:
                    if resp.status == 200:
                        verbe = "allumé" if action == "turn_on" else "éteint"
                        yield f"C'est fait, j'ai {verbe} la lumière du salon."
                        return
        except Exception:
            pass

        yield "Désolé, je n'ai pas réussi à joindre Home Assistant."
```

---

## 🔒 Protection RBAC Enfant Automatique

Si votre commande effectue une action sensible (ouverture du portail, redémarrage d'un serveur, consultation d'un mot de passe) :

Définissez simplement :

```python
requires_admin = True
```

Le registre `IntentRegistry` intercepte automatiquement les requêtes émises par un profil `UserRole.CHILD`. Si un enfant prononce la commande, il recevra automatiquement une notification polie de refus sans qu'aucun code sensible ne soit exécuté :

> *« Désolé Ismail, l'accès aux commandes d'administration du serveur est réservé aux adultes. »*

---

## 🧪 Tester son Intention en Test Unitaire

Créez un test unitaire dans `tests/test_mon_skill.py` :

```python
import unittest
from core_server.intents.base import IntentContext
from core_server.intents.registry import IntentRegistry
from core_server.voice_id import SpeakerProfile, UserRole

class TestMonSkill(unittest.IsolatedAsyncioTestCase):
    async def test_execution(self):
        registry = IntentRegistry()
        ctx = IntentContext(
            prompt="Raconte-moi une blague",
            clean_prompt="raconte-moi une blague",
            speaker=SpeakerProfile(name="Test", role=UserRole.ADMIN, f0_mean_hz=120.0, spectral_centroid_hz=1400.0),
            obsidian=None,
            circuit_breaker=None
        )
        gen = await registry.handle_prompt(ctx)
        self.assertIsNotNone(gen)
        responses = [r async for r in gen]
        self.assertIn("plongeurs", responses[0])
```
