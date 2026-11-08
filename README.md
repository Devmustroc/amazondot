<div align="center">

# 🎙️ SovereignDot

### Liberate your Amazon Echo Dot into a 100% Sovereign, Ultra-Fast AI Voice Assistant

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-green.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Latency](https://img.shields.io/badge/Voice_Latency-%3C1000ms-success.svg)](#performance)
[![Offline TTS](https://img.shields.io/badge/Offline_TTS-Piper_ONNX-orange.svg)](#offline-resilience)
[![Biometric RBAC](https://img.shields.io/badge/VoiceID-Child_Safe_RBAC-blueviolet.svg)](#voiceid--child-safety)
[![Docs: Material](https://img.shields.io/badge/Docs-MkDocs_Material-blue.svg)](https://mustroc.github.io/amazondot/)

*Zero AWS dependencies. Zero tracking. 100% Local Homelab & Sovereign AI.*

[📖 Documentation](https://mustroc.github.io/amazondot/) • [English](#english) • [Français](#français) • [Quickstart](#-quickstart-in-60-seconds) • [Architecture](#-architecture) • [Echo Dot Jailbreak](#-hardware-liberation-echo-dot-2g)

</div>

---

## ⚡ What is SovereignDot?

Millions of 2nd-generation Amazon Echo Dots sit obsolete in drawers or landfills. **SovereignDot** breathes new life into them by permanently severing their connection to Amazon AWS and turning them into sovereign, ultra-low latency voice assistants powered by local AI and open models.

Works in **two modes**:
1. 📻 **Hardware Mode**: Runs on real, jailbroken Amazon Echo Dot 2G devices over your local WiFi (extracting raw 9-channel microphone arrays and 48kHz audio playback).
2. 💻 **PC Emulator Mode**: Test and run immediately on your Linux/Mac/Windows machine using your standard laptop mic & speakers!

---

## 🚀 Key Features

- **⚡ Sub-Second Latency (< 1000ms)**: Streaming sentence-chunked pipeline with Whisper greedy decoding and pipelined streaming TTS.
- **🛡️ Instant Offline Fallback (< 300ms)**: Built-in asynchronous **Circuit-Breaker**. If your Internet connection drops or the cloud times out, SovereignDot instantly fails over to embedded local **Piper ONNX** without user interruption.
- **🧒 VoiceID & Child Safety (RBAC)**: Sub-5ms biometric speaker identification. Children can ask for stories and general facts, but sensitive homelab commands (Proxmox, Docker containers, firewalls) are strictly locked to adult profiles.
- **🧠 Atomic Memory in Obsidian**: Real-time voice knowledge capture (*"Remember that my son Ismail loves dinosaurs"*) auto-categorized into your local Markdown vault and recalled naturally.
- **🛠️ Homelab SRE & Docker Monitoring via MCP**: Ask your speaker for Proxmox VE node health, CPU/RAM utilization, and Docker container states in natural language.
- **🔒 Encrypted Biometrics**: Local voice profiles and voiceprints are protected with Fernet AES encryption.

---

## 🏛️ Architecture

```mermaid
flowchart LR
    subgraph Hardware["📻 Client Layer"]
        Dot["Echo Dot 2G (Hardware)\ntad_dotd daemon"]
        PC["PC Emulator\n(Laptop Mic / Speaker)"]
    end

    subgraph Core["🧠 SovereignDot Core (Python 3.12 / Docker)"]
        Audio["Audio Processor\n(9-Ch Beamforming + Silero VAD)"]
        STT["STT Engine\n(Faster-Whisper Greedy)"]
        VoiceID["VoiceID Engine\n(Pitch F0 + 16-D Mel Biometrics)"]
        Router["Router / Brain\n(Fast Intents / Ollama / Gemini)"]
        Breaker["Circuit-Breaker\n(Cloud vs Offline Watchdog)"]
        TTS["Dual-Engine TTS\n(Edge-TTS / Piper ONNX Local)"]
        Mem["Obsidian Vault\n(Atomic Markdown Memory)"]
        MCP["Model Context Protocol\n(Proxmox VE & Docker SRE)"]
    end

    Dot -->|TCP 9000 (PCM Raw)| Audio
    PC -->|System Mic| Audio
    Audio --> STT
    Audio --> VoiceID
    STT --> Router
    VoiceID -->|RBAC Guard| Router
    Router <--> Mem
    Router <--> MCP
    Router --> Breaker
    Breaker -->|Online| TTS
    Breaker -->|Offline Fallback| TTS
    TTS -->|TCP 9001 (WAV 48kHz)| Dot
    TTS -->|Local Speaker| PC
```

---

## ⏱️ Quickstart in 60 Seconds

### 1. Clone & Setup Environment

```bash
git clone https://github.com/mustroc/sovereigndot.git
cd sovereigndot
cp .env.example .env
```

### 2. Test in PC Emulator Mode (No Hardware Needed!)

Set in your `.env`:
```env
AUDIO_INPUT_MODE=local
```

Install dependencies and run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m core_server.main
```

### 3. Deploy in Production with Docker (Proxmox / Homelab)

```bash
cd deploy
docker compose up -d
```

Check health status anytime:
```bash
python -m core_server.healthcheck
```

---

## 📻 Hardware Liberation (Echo Dot 2G)

SovereignDot uses a **Clean-Room approach**. No proprietary Amazon firmware files are hosted in this repository.

1. Connect your Echo Dot 2G via micro-USB to your computer.
2. Fetch open-source bootrom exploit tools:
   ```bash
   ./tools/fetch_blobs.sh
   ```
3. Follow our detailed hardware flashing guide in [`docs/hardware/echo-dot-2g.md`](docs/hardware/echo-dot-2g.md).

---

## 🧪 Automated Test Suite

SovereignDot includes an extensive automated unit and integration test suite:

```bash
python -m unittest discover tests
```

- **Pipeline & Latency Tests**: `tests/test_resilience_fallback.py`
- **VoiceID & RBAC Tests**: `tests/test_voice_id.py`
- **Obsidian Memory Tests**: `tests/test_obsidian_memory.py`
- **Healthcheck Probe Tests**: `tests/test_healthcheck.py`

---

## 📄 License

Licensed under the **Apache License, Version 2.0**. See [`LICENSE`](LICENSE) for details.

Copyright © 2026 **Mustroc / El Mustapha**. Built with passion for open-source AI sovereignty.
Proudly supporting the ecosystem of [Mamitales](https://github.com/mustroc).
