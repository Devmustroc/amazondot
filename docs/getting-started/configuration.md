# Guide de Configuration (.env)

Toutes les options de SovereignDot sont pilotées par des variables d'environnement centralisées dans [`core_server/config.py`](file:///home/devmust/Work/amazondot/core_server/config.py).  
Copiez `.env.example` vers `.env` et adaptez les valeurs selon vos besoins.

---

## 📋 Tableau Récapitulatif des Variables

| Variable | Valeur par défaut | Description |
| :--- | :--- | :--- |
| `LOCAL_AUDIO_MODE` | `false` | Active le mode émulateur PC (micro & haut-parleurs locaux sans Echo Dot physique). |
| `ECHO_DOT_IP` | `192.168.1.23` | Adresse IP locale de l'Amazon Echo Dot 2G jailbreaké sur votre réseau. |
| `ECHO_DOT_PORT` | `9001` | Port TCP de streaming audio brut (16kHz entrée / 48kHz sortie). |
| `WHISPER_MODEL` | `tiny` | Modèle Faster-Whisper pour la reconnaissance vocale (`tiny`, `base`, `small`, `medium`). |
| `WHISPER_BEAM_SIZE` | `1` | Largeur du faisceau pour Whisper (1 = ultra-faible latence < 120ms). |
| `OPENROUTER_API_KEY` | `""` | Clé API pour accéder aux LLM distants via OpenRouter (Gemini 3.8 Flash, Claude, etc.). |
| `OPENROUTER_MODEL` | `google/gemini-3.8-flash` | Modèle de réflexion utilisé pour les requêtes complexes et les tool-calls. |
| `OPENROUTER_ROUTER_MODEL` | `typesafe/jev-router` | Modèle de routage intelligent OpenRouter pour la sélection d'outils. |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | URL de votre instance Ollama locale pour les réponses simples et le fallback offline. |
| `OLLAMA_MODEL` | `qwen2.5:latest` | Modèle Ollama local hébergé sur votre Homelab (ultra-rapide et privé). |
| `TTS_VOICE` | `fr-FR-HenriNeural` | Voix neuronale Microsoft Edge-TTS pour les synthèses vocales en ligne. |
| `TTS_CACHE_ENABLED` | `true` | Active la mise en cache multi-niveaux (RAM + Disque) pour les réponses fréquentes (0ms). |
| `PIPER_ENABLED` | `true` | Active le moteur de synthèse locale hors-ligne Piper ONNX. |
| `PIPER_MODEL_NAME` | `fr_FR-upmc-medium` | Nom du modèle officiel Piper ONNX en français (téléchargé automatiquement). |
| `CIRCUIT_BREAKER_MAX_FAILURES` | `2` | Nombre d'échecs réseau consécutifs avant de déclencher le basculement hors-ligne. |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SEC` | `30.0` | Durée d'attente (secondes) avant de sonder la réouverture du circuit cloud. |
| `CIRCUIT_BREAKER_TTS_TIMEOUT_SEC` | `1.5` | Timeout strict pour Edge-TTS avant repli instantané sur Piper ONNX. |
| `OBSIDIAN_VAULT_PATH` | `./vault/Memory` | Chemin absolu ou relatif vers le dossier mémoire Markdown de SovereignDot. |
| `FAMILY_ADMIN_NAME` | `El Mustapha` | Nom de l'administrateur système pour les privilèges RBAC élevés. |
| `VOICE_PROFILES_ENCRYPTION_KEY` | *Générée auto* | Clé de chiffrement AES-256 pour sécuriser les empreintes vocales sur le disque. |
| `PROXMOX_HOST` | `192.168.1.10` | Hôte Proxmox VE pour les métriques SRE via MCP. |
| `PROXMOX_TOKEN_ID` | `""` | Token API Proxmox VE (format: `user@pam!tokenid`). |
| `PROXMOX_TOKEN_SECRET` | `""` | Secret du token API Proxmox VE. |

---

## 🔒 Sécurité et Clés Privées

- Ne commitez **jamais** votre fichier `.env` sur un dépôt public.
- Les empreintes vocales biométriques générées dans `core_server/data/voice_profiles.enc` sont chiffrées en **AES-GCM 256 bits** à l'aide de votre variable `VOICE_PROFILES_ENCRYPTION_KEY`.
