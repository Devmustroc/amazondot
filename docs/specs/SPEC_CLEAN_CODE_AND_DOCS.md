# Spec: SovereignDot Clean Architecture & MkDocs Documentation Platform

## Problem Statement

SovereignDot currently delivers all core functionality (streaming voice pipeline <1000ms, offline Piper fallback <300ms, voice ID RBAC <5ms, Obsidian memory, Proxmox/Docker SRE). However:
1. `core_server/brain.py` has grown into a 560-line monolithic module combining transcription, hardcoded regex intent matching, streaming LLM inference, local Ollama orchestration, and multi-tier TTS synthesis. This makes extending the system with new voice skills difficult for open-source contributors.
2. The project lacks a unified, searchable public documentation website for users and contributors to easily set up PC mode, understand the architecture, jailbreak their Echo Dot 2G, or write custom voice plugins.

## Solution

1. **Domain-Driven Clean Refactoring**:
   - Refactor `core_server/brain.py` into decoupled domain modules:
     - `core_server/intents/` with an extensible `@intent` registry pattern where each voice skill is a standalone handler.
     - `core_server/stt/` handling Whisper speech-to-text and phonetic corrections.
     - `core_server/llm/` managing OpenRouter streaming, prompt assembly, and local Ollama routing.
     - `core_server/tts/` managing the dual-engine TTS (Edge-TTS + Piper ONNX) and multi-tier caching.
   - Maintain strict backward compatibility for all existing callers (`Brain`, `TadAssistant`) ensuring all 21 unit tests pass.

2. **MkDocs Material Documentation Platform**:
   - Build a production-grade, responsive documentation website using **MkDocs Material** under `docs/`.
   - Implement dark/light theme, instant offline search, Mermaid diagrams, code copy buttons, and clear navigation across 4 pillars:
     1. **Getting Started**: Quickstart in 60 seconds (PC emulator & Docker).
     2. **Architecture**: Audio pipeline, Circuit-Breaker, VoiceID RBAC, Obsidian memory.
     3. **Hardware Jailbreak**: Step-by-step Clean-Room guide for Echo Dot 2G.
     4. **Plugin Development**: How to write a custom `@intent` in 10 lines of Python.
   - Add automated GitHub Actions deployment workflow for GitHub Pages (`.github/workflows/docs.yml`).

## User Stories

1. As an open-source contributor, I want a clean `@intent` decorator pattern so that I can create a new voice command in a single isolated file without editing the central brain monolith.
2. As a home automator, I want modular voice intent handlers so that I can add custom smart home or weather integrations with dedicated triggers.
3. As a developer testing SovereignDot on a laptop, I want clear online documentation so that I can launch the PC emulator in under 60 seconds without searching through commit logs.
4. As an Echo Dot owner, I want a clean-room, visual hardware jailbreak guide with troubleshooting tips so that I can liberate my device safely without risking bricking.
5. As an SRE engineer, I want the Proxmox and Docker monitoring features thoroughly documented with example voice queries so that I can supervise my homelab hands-free.
6. As a privacy-conscious parent, I want clear architectural documentation on the VoiceID RBAC child-safety system so that I understand how voiceprints are encrypted with Fernet AES.
7. As a self-hoster, I want complete Docker Compose and Systemd production guides so that SovereignDot runs 24/7 with auto-restart and zero memory leaks.
8. As a maintainer, I want automated GitHub Actions for building and deploying the documentation site so that every commit to master updates the live website.
9. As a core developer, I want existing unit tests to continue passing without modification so that refactoring introduces zero behavioral regressions.
10. As a visitor browsing the repository, I want a clean code structure with standard type annotations and docstrings so that navigating the codebase is intuitive and readable.

## Implementation Decisions

### 1. Intent Registry Pattern (`core_server/intents/`)
- A centralized `IntentRegistry` singleton that collects handlers decorated with `@intent(name, triggers, priority, protected_role)`.
- Handlers implement an evaluation interface `match(prompt: str, context: dict) -> bool` and an asynchronous execution interface `execute(prompt: str, context: dict) -> AsyncGenerator[str, None]`.
- Built-in intents migrated cleanly:
  - `time_intent.py` (Heure actuelle)
  - `date_intent.py` (Date et jour)
  - `identity_intent.py` (Identité de l'assistant)
  - `memory_intent.py` (Apprentissage et rappel Obsidian)
  - `homelab_intent.py` (Proxmox VE & Docker SRE)
  - `resilience_intent.py` (Statut du réseau et circuit-breaker)
  - `voiceid_intent.py` (Qui suis-je)

### 2. Specialized Audio & Model Packages
- `core_server/stt/`: Encapsulates `faster-whisper` transcription, beam size configuration, and phonetic post-processing.
- `core_server/tts/`: Encapsulates `AudioProcessor`, Edge-TTS communication, Piper ONNX synthesis, and multi-tier RAM/disk caching.
- `core_server/llm/`: Encapsulates prompt template rendering, token streaming generator, and Ollama/OpenRouter fallback orchestration.

### 3. Facade `Brain` Class
- The existing `Brain` class in `core_server/brain.py` becomes a thin, high-level facade coordinating `STT`, `IntentRegistry`, `LLM`, and `TTS`.
- Keeps the exact existing public method signatures: `transcribe()`, `generate_response_stream()`, `generate_response()`, and `synthesize_speech()`.
- Guarantees zero breaking changes for `TadAssistant` and the 21 existing unit tests.

### 4. MkDocs Material Platform
- Configured via `mkdocs.yml` at the project root with the `material` theme.
- Navigation structure:
  - Home / Overview (`index.md`)
  - Getting Started (`getting-started/quickstart.md`, `getting-started/configuration.md`)
  - Architecture & Deep Dives (`architecture/pipeline.md`, `architecture/voiceid-rbac.md`, `architecture/circuit-breaker.md`, `architecture/obsidian-memory.md`)
  - Hardware Liberation (`hardware/echo-dot-2g.md`, `hardware/pinout.md`)
  - Contributing & Plugins (`contributing/writing-intents.md`, `contributing/guidelines.md`)
- GitHub Actions workflow `.github/workflows/docs.yml` using `mkdocs gh-deploy --force`.

## Testing Decisions

- **Zero-Regression Rule**: All 21 existing unit tests (`test_resilience_fallback.py`, `test_voice_id.py`, `test_obsidian_memory.py`, `test_healthcheck.py`) must pass before and after the refactoring.
- **New Unit Tests**:
  - `tests/test_intent_registry.py`: Tests dynamic intent registration, priority sorting, parameter matching, and child RBAC enforcement.
- **Doc Build Verification**:
  - Run `mkdocs build --strict` to verify all links, images, and Mermaid syntax compile without warnings or broken links.

## Out of Scope

- Adding new hardware support beyond Echo Dot 2G (Echo Dot 3G, Google Home are reserved for v2.0).
- Replacing faster-whisper with alternative STT engines.
- Cloud hosting of the documentation outside GitHub Pages.

## Further Notes

- The refactored code will be clean, fully typed with Python 3.12 syntax, and formatted according to PEP 8 / Ruff standards.
