"""
SovereignDot Brain - Central Orchestration Facade.
Decouples and coordinates STT, VoiceID Biometrics, Intent Registry, LLM Router, and Dual-Engine TTS.
"""
import re
import logging
import asyncio
from typing import Optional, AsyncGenerator
from pathlib import Path

from core_server import config
from core_server.stt import WhisperSTTEngine
from core_server.intents import global_intent_registry, IntentContext, IntentRegistry
from core_server.llm import LLMRouterEngine
from core_server.tts import DualEngineTTS, process_audio_for_echo_dot, COMMON_ACK_PHRASES
from core_server.obsidian_memory import ObsidianMemory
from core_server.mcp_client import McpManager
from core_server.resilience import global_circuit_breaker, global_piper_engine, CircuitBreaker, PiperEngine
from core_server.voice_id import global_voice_id, VoiceIDEngine, UserRole, SpeakerProfile

logger = logging.getLogger("brain")

# Re-export for backward compatibility
__all__ = ["Brain", "process_audio_for_echo_dot", "COMMON_ACK_PHRASES"]


class Brain:
    """
    Unified, clean architecture facade for SovereignDot voice assistant.
    Orchestrates Whisper STT, Biometric VoiceID, Modular Voice Intents, Hybrid LLM, and Dual-Engine TTS.
    """

    def __init__(
        self,
        stt_engine: Optional[WhisperSTTEngine] = None,
        tts_engine: Optional[DualEngineTTS] = None,
        llm_engine: Optional[LLMRouterEngine] = None,
        obsidian: Optional[ObsidianMemory] = None,
        voice_id: Optional[VoiceIDEngine] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        piper: Optional[PiperEngine] = None,
        mcp: Optional[McpManager] = None,
    ):
        logger.info("Initializing SovereignDot Brain Facade...")
        # Subsystems & Shared State
        self.obsidian = obsidian or ObsidianMemory()
        self.circuit_breaker = circuit_breaker or global_circuit_breaker
        self.piper = piper or global_piper_engine
        self.voice_id = voice_id or global_voice_id
        self.mcp = mcp or McpManager()
        self.intent_registry: IntentRegistry = global_intent_registry

        # Core Engines
        self.stt = stt_engine or WhisperSTTEngine()
        self.whisper = self.stt.model  # Backward-compatibility alias

        self.tts = tts_engine or DualEngineTTS(circuit_breaker=self.circuit_breaker, piper=self.piper)
        self.cache_dir: Path = self.tts.cache_dir
        self._tts_ram_cache = self.tts._ram_cache  # Backward-compatibility alias

        self.llm = llm_engine or LLMRouterEngine(
            obsidian=self.obsidian,
            mcp=self.mcp,
            circuit_breaker=self.circuit_breaker,
        )
        self.llm_client = self.llm.llm_client
        self.async_llm_client = self.llm.async_llm_client
        self.ollama_url = self.llm.ollama_url
        self.ollama_model = self.llm.ollama_model
        self.router_model = self.llm.router_model
        self.history = self.llm.history

    async def initialize(self):
        """Asynchronous initialization of external services (MCP tools, background Piper loading)."""
        try:
            await self.mcp.initialize()
        except Exception as e:
            logger.warning("Error initializing MCP manager: %s", e)

        if config.PIPER_ENABLED:
            try:
                asyncio.create_task(self.piper.initialize_async())
            except Exception as e:
                logger.warning("Error starting background Piper initialization: %s", e)

    def transcribe(self, pcm_16k_bytes: bytes) -> str:
        """Transcribes 16kHz 16-bit mono PCM into French text using Whisper."""
        return self.stt.transcribe(pcm_16k_bytes)

    async def generate_response_stream(
        self, prompt: str, speaker_audio: Optional[bytes] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming pipeline coordinator:
        1. VoiceID: Speaker biometric identification & RBAC security check (<20ms).
        2. Intent Registry: Decoupled zero-latency skills (Time, Date, Identity, Obsidian, SRE, Network).
        3. Hybrid LLM Router: Local Ollama / OpenRouter streaming.
        """
        if not prompt.strip():
            yield "Je ne vous ai pas bien entendu, pouvez-vous répéter ?"
            return

        # VoiceID Biometric Identification & RBAC Check
        if speaker_audio:
            speaker, conf = self.voice_id.identify_speaker(speaker_audio)
        else:
            admin_name = getattr(config, "FAMILY_ADMIN_NAME", "Admin")
            speaker = SpeakerProfile(name=admin_name, role=UserRole.ADMIN, f0_mean_hz=122.0, spectral_centroid_hz=1450.0)
            conf = 1.0

        # Enforce RBAC security on prompt
        allowed, denial_reason = self.voice_id.check_permission(speaker, prompt)
        if not allowed:
            logger.warning("VoiceID RBAC Blocked prompt: '%s' for speaker '%s'", prompt, speaker.name)
            yield denial_reason
            return

        logger.info("Evaluating prompt: '%s' (Speaker: %s, Role: %s, Conf: %.2f)", prompt, speaker.name, speaker.role.value, conf)
        clean_prompt = re.sub(
            r"^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip() or prompt

        # 1. Dispatch through decoupled Voice Intent Registry
        intent_ctx = IntentContext(
            prompt=prompt,
            clean_prompt=clean_prompt,
            speaker=speaker,
            obsidian=self.obsidian,
            circuit_breaker=self.circuit_breaker,
            mcp=self.mcp,
        )
        intent_stream = await self.intent_registry.handle_prompt(intent_ctx)
        if intent_stream is not None:
            async for reply in intent_stream:
                logger.info("Intent Spoken Response: '%s'", reply)
                yield reply
            return

        # 2. Route remaining queries to Hybrid LLM Router Engine
        async for chunk in self.llm.generate_response_stream(prompt, speaker):
            yield chunk

    async def generate_response(self, prompt: str, speaker_audio: Optional[bytes] = None) -> str:
        """Non-streaming convenience method."""
        chunks = [c async for c in self.generate_response_stream(prompt, speaker_audio=speaker_audio)]
        return " ".join(chunks).strip()

    async def synthesize_speech(self, text: str) -> bytes:
        """Synthesizes text to 48kHz stereo WAV with caching and circuit-breaker fallback."""
        return await self.tts.synthesize_speech(text)
