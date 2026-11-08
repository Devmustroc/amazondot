"""
Dual-Engine Speech Synthesis Subsystem for SovereignDot.
Manages Multi-tier Caching (RAM & Disk), Cloud Edge-TTS, and Offline Piper ONNX Fallback.
"""
import io
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict
import soundfile as sf
import edge_tts
from core_server import config
from core_server.tts.audio_filter import process_audio_for_echo_dot
from core_server.resilience import CircuitState, CircuitBreaker, PiperEngine, global_circuit_breaker, global_piper_engine

logger = logging.getLogger("tts")

COMMON_ACK_PHRASES = [
    "Oui ?",
    "Je t'écoute.",
    "C'est noté.",
    "Avec plaisir ! N'hésite pas si tu as besoin d'autre chose.",
    "Bonne nuit à toute la famille !",
    "À très bientôt !",
    "C'est noté, je reste disponible.",
    "Je n'ai pas bien compris.",
]


class DualEngineTTS:
    """Orchestrates multi-tier TTS caching, Cloud Edge-TTS, and Piper ONNX offline fallback."""

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        piper: Optional[PiperEngine] = None,
        cache_dir: Optional[Path] = None,
    ):
        self.circuit_breaker = circuit_breaker or global_circuit_breaker
        self.piper = piper or global_piper_engine

        self.cache_dir = cache_dir or (Path(config.BASE_DIR) / "core_server" / "tts_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._ram_cache: Dict[str, bytes] = {}
        self._load_disk_cache()

    def _get_cache_path(self, text: str) -> Path:
        key = hashlib.md5(f"{config.TTS_VOICE}:{text.strip()}".encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.wav"

    def _load_disk_cache(self):
        """Pre-loads existing cached WAVs from disk into RAM for instant 0ms access."""
        loaded = 0
        for phrase in COMMON_ACK_PHRASES:
            p = self._get_cache_path(phrase)
            if p.exists():
                try:
                    self._ram_cache[phrase] = p.read_bytes()
                    loaded += 1
                except Exception:
                    pass
        if loaded > 0:
            logger.info("Loaded %d common acknowledgment audio phrases into RAM cache.", loaded)

    async def synthesize_speech(self, text: str) -> bytes:
        """
        Synthesizes text to crystal-clear 48kHz 16-bit stereo WAV with multi-tier caching and Circuit-Breaker fallback:
        1. In-RAM cache (0.00ms).
        2. On-disk cache (<1ms).
        3. Cloud Edge-TTS (with strict timeout).
        4. Offline Piper ONNX instant fallback (<300ms) on network failure or circuit breaker OPEN.
        """
        text_clean = text.strip()
        if not text_clean:
            return b""

        # Tier 1: In-RAM Cache (Instant 0ms)
        if config.TTS_CACHE_ENABLED and text_clean in self._ram_cache:
            logger.debug("TTS Cache HIT (RAM): '%s'", text_clean)
            return self._ram_cache[text_clean]

        # Tier 2: On-Disk Cache
        cache_file = self._get_cache_path(text_clean)
        if config.TTS_CACHE_ENABLED and cache_file.exists():
            try:
                wav_data = cache_file.read_bytes()
                self._ram_cache[text_clean] = wav_data
                logger.debug("TTS Cache HIT (Disk): '%s'", text_clean)
                return wav_data
            except Exception as e:
                logger.warning("Error reading TTS disk cache: %s", e)

        # Tier 3: If Circuit Breaker is OPEN, directly bypass cloud and use offline Piper ONNX
        if self.circuit_breaker.state == CircuitState.OPEN and config.PIPER_ENABLED:
            logger.info("Circuit Breaker is OPEN. Synthesizing directly via offline Piper ONNX: '%s'", text_clean)
            try:
                wav_data = await self.piper.synthesize_async(text_clean)
                if wav_data and config.TTS_CACHE_ENABLED:
                    self._ram_cache[text_clean] = wav_data
                    try:
                        cache_file.write_bytes(wav_data)
                    except Exception:
                        pass
                return wav_data
            except Exception as e:
                logger.error("Offline Piper ONNX synthesis failed: %s", e)
                return b""

        # Tier 4: Attempt Cloud Edge-TTS with strict timeout and fallback
        async def _call_edge_tts() -> bytes:
            comm = edge_tts.Communicate(text_clean, config.TTS_VOICE)
            mp3_stream = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_stream.extend(chunk["data"])
            if not mp3_stream:
                raise RuntimeError("Empty audio stream from Edge-TTS")
            data, sr = sf.read(io.BytesIO(mp3_stream))
            return process_audio_for_echo_dot(data, sr)

        try:
            logger.info("Synthesizing speech via Edge-TTS (%s): '%s'", config.TTS_VOICE, text_clean)
            wav_data = await asyncio.wait_for(_call_edge_tts(), timeout=config.CIRCUIT_BREAKER_TTS_TIMEOUT_SEC)
            self.circuit_breaker.record_success()

            if config.TTS_CACHE_ENABLED:
                self._ram_cache[text_clean] = wav_data
                try:
                    cache_file.write_bytes(wav_data)
                except Exception:
                    pass
            return wav_data

        except Exception as e:
            self.circuit_breaker.record_failure(e)
            logger.warning("Edge-TTS timed out or failed (%s). Triggering instant Piper ONNX fallback (<300ms)...", e)
            if config.PIPER_ENABLED:
                try:
                    wav_data = await self.piper.synthesize_async(text_clean)
                    if wav_data and config.TTS_CACHE_ENABLED:
                        self._ram_cache[text_clean] = wav_data
                        try:
                            cache_file.write_bytes(wav_data)
                        except Exception:
                            pass
                    return wav_data
                except Exception as e_pip:
                    logger.error("Piper fallback synthesis failed: %s", e_pip)
                    return b""
            return b""
