# Guide de Configuration (.env)

Toutes les options de SovereignDot sont pilotées par des variables d'environnement centralisées dans [`core_server/config.py`](https://github.com/Devmustroc/amazondot/blob/master/core_server/config.py).  
Copiez `.env.example` vers `.env` et adaptez les valeurs selon vos besoins.

---

## 📋 Tableau Récapitulatif des Variables

| Variable | Valeur par défaut | Description |
| :--- | :--- | :--- |
| `AUDIO_INPUT_MODE` | `echo_dot` | Mode d'entrée audio : `local` (émulateur PC micro/enceintes) ou `echo_dot` (matériel). |
| `DOT_HOST` | `192.168.1.23` | Adresse IP locale de l'Amazon Echo Dot 2G jailbreaké sur votre réseau. |
| `DOT_MIC_PORT` | `9000` | Port TCP du flux brut 9-canaux des microphones de l'Echo Dot. |
| `DOT_PLAY_PORT` | `9001` | Port TCP de lecture stéréo 48kHz et contrôle des LEDs. |
| `WHISPER_MODEL` | `tiny` | Modèle Faster-Whisper pour la reconnaissance vocale (`tiny`, `base`, `small`, `medium`). |
| `WHISPER_BEAM_SIZE` | `1` | Largeur du faisceau pour Whisper (1 = ultra-faible latence < 120ms). |
| `OPENROUTER_API_KEY` | `""` | Clé API pour accéder aux LLM distants via OpenRouter (Gemini 3.8 Flash, Claude, etc.). |
| `OPENROUTER_MODEL` | `google/gemini-3.8-flash` | Modèle de réflexion utilisé pour les requêtes complexes et les tool-calls. |
| `OPENROUTER_ROUTER_MODEL` | `typesafe/jev-router` | Modèle de routage intelligent OpenRouter pour la sélection d'outils. |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | URL de votre instance Ollama locale pour les réponses simples et le fallback offline. |
| `OLLAMA_MODEL` | `qwen2.5:latest` | Modèle Ollama local hébergé sur votre Homelab (ultra-rapide et privé). |
| `TTS_VOICE` | `fr-FR-VivienneMultilingualNeural` | Voix neuronale Microsoft Edge-TTS pour les synthèses vocales en ligne. |
| `TTS_CACHE_ENABLED` | `true` | Active la mise en cache multi-niveaux (RAM + Disque) pour les réponses fréquentes (0ms). |
| `PIPER_ENABLED` | `true` | Active le moteur de synthèse locale hors-ligne Piper ONNX. |
| `PIPER_MODEL_PATH` | `.../fr_FR-siwis-medium.onnx` | Chemin du modèle officiel Piper ONNX en français (téléchargé automatiquement). |
| `CIRCUIT_BREAKER_MAX_FAILURES` | `2` | Nombre d'échecs réseau consécutifs avant de déclencher le basculement hors-ligne. |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SEC` | `15.0` | Durée d'attente (secondes) avant de sonder la réouverture du circuit cloud. |
| `CIRCUIT_BREAKER_TTS_TIMEOUT_SEC` | `1.2` | Timeout strict pour Edge-TTS avant repli instantané sur Piper ONNX. |
| `OBSIDIAN_VAULT_PATH` | `./vault/Memory` | Chemin absolu ou relatif vers le dossier mémoire Markdown de SovereignDot. |
| `FAMILY_ADMIN_NAME` | `El Mustapha` | Nom de l'administrateur système pour les privilèges RBAC élevés. |
| `PROXMOX_HOST` | `192.168.1.200` | Hôte Proxmox VE pour les métriques SRE via MCP. |

---

## 🔒 Sécurité et Clés Privées

- Ne commitez **jamais** votre fichier `.env` sur un dépôt public.
- Les empreintes vocales biométriques générées dans `core_server/data/voice_profiles.enc` sont chiffrées en **AES-GCM 256 bits** à l'aide de votre variable `VOICE_PROFILES_ENCRYPTION_KEY`.
