# SovereignDot — Assistant Vocal IA 100% Souverain

> **Transformez votre Amazon Echo Dot 2G en enceinte intelligente souveraine, connectée à votre Homelab et respectueuse de votre vie privée.**

Bienvenue sur la documentation officielle de **SovereignDot** (projet TAD — The Sovereign Amazon Dot).  
SovereignDot est une plateforme logicielle et matérielle open-source permettant de libérer votre Amazon Echo Dot de l'écosystème cloud fermé d'Amazon pour en faire un agent vocal autonome propulsé par vos propres modèles d'intelligence artificielle.

---

## ⚡ Pourquoi SovereignDot ?

La plupart des assistants vocaux commerciaux envoient en permanence vos conversations vers des serveurs distants, cessent de fonctionner en cas de panne Internet et ne peuvent pas interagir avec vos serveurs locaux. SovereignDot résout ces trois problèmes majeurs :

- **100% Souverain & Privé** : Vos flux audio restent cantonnés à votre réseau local. Aucun espionnage ni exploitation publicitaire.
- **Ultra-Faible Latence (< 1 000 ms)** : Pipeline streaming réactif de bout en bout (Silero VAD $\to$ Faster-Whisper $\to$ Token-to-Sentence $\to$ Edge-TTS).
- **Résilience Totale & Circuit-Breaker** : En cas de coupure Internet, SovereignDot bascule en moins de 300 ms sur son moteur neuronal local **Piper ONNX**.
- **Biométrie Vocale VoiceID & Contrôle Parental** : Identification de l'orateur en moins de 5 ms par extraction F0/Mel et blocage des commandes d'administration pour les enfants.
- **Supervision Homelab & SRE** : Pilotage vocal de votre cluster Proxmox VE et de vos conteneurs Docker via Model Context Protocol (MCP).
- **Mémoire Long-terme Markdown** : Mémorisation et rappel instantané synchronisés avec votre coffre **Obsidian**.
- **Architecture Extensible `@intent`** : Créez vos propres commandes vocales en 10 lignes de Python sans toucher au cœur du système.

---

## 🏛️ Vue d'Ensemble de l'Architecture

```mermaid
graph TD
    subgraph Hardware["Matériel (Echo Dot 2G ou Émulateur PC)"]
        MIC["Microphone / ALSA"] -->|16kHz PCM| BRIDGE["Bridge Audio TCP:9001"]
        BRIDGE -->|48kHz Stéréo| DAC["DAC / Transducteur 35mm"]
    end

    subgraph Core["SovereignDot Core Server (Conteneur / Proxmox CT)"]
        VAD["Silero VAD / Détection Parole"]
        STT["Faster-Whisper STT (CPU int8)"]
        VOICEID["Biométrie VoiceID & RBAC (<5ms)"]
        REGISTRY["Intent Registry (@intent)"]
        ROUTER["Hybrid LLM Router"]
        TTS["Dual-Engine TTS (Edge-TTS / Piper)"]

        BRIDGE -->|Flux Audio| VAD
        VAD --> STT
        STT --> VOICEID
        VOICEID --> REGISTRY
        REGISTRY -->|Intent Non-Géré| ROUTER
        ROUTER --> TTS
        REGISTRY -->|Réponse Directe| TTS
        TTS -->|WAV Filtré 220Hz| BRIDGE
    end

    subgraph Intelligence["Moteurs d'Intelligence & Mémoire"]
        OLLAMA["Local Ollama (Qwen 2.5)"]
        OPENROUTER["OpenRouter / Gemini 3.8 Flash"]
        OBSIDIAN["Obsidian Vault (Markdown)"]
        MCP["MCP Homelab (Proxmox & Docker)"]

        ROUTER -->|Requête Routine| OLLAMA
        ROUTER -->|Raisonnement / Tools| OPENROUTER
        REGISTRY <--> OBSIDIAN
        REGISTRY <--> MCP
    end
```

---

## 🚀 Navigation Rapide

- [Guide de Démarrage Rapide (60 secondes)](getting-started/quickstart.md) : Démarrez sur votre PC sans Echo Dot physique.
- [Guide de Configuration `.env`](getting-started/configuration.md) : Personnalisez tous les paramètres et clés API.
- [Libération Hardware Echo Dot 2G](hardware/echo-dot-2g.md) : Tutoriel pas à pas pour flash u-boot et rooter l'appareil.
- [Développer des Intentions Vocales](contributing/writing-intents.md) : Apprenez à créer vos propres skills en quelques lignes.

---

> [!NOTE] Projet Frère : Mamitales
> Vous aimez l'IA vocale appliquée à la famille ? Découvrez également [Mamitales](https://mamitales.com), notre plateforme d'histoires personnalisées générées par IA pour les enfants et grands-parents !
