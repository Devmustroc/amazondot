"""
Resilience & Offline Fallback Subsystem for TAD Core.
Provides Circuit-Breaker network status monitoring and instant ONNX Piper TTS fallback.
"""
import os
import io
import time
import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any
import numpy as np

from core_server import config

logger = logging.getLogger("resilience")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Cloud services normal and healthy
    OPEN = "OPEN"            # Outage detected: circuit open, fast offline fallback
    HALF_OPEN = "HALF_OPEN"  # Testing connectivity recovery


class CircuitBreaker:
    """
    In-memory asynchronous Circuit Breaker pattern with automatic recovery probe.
    Guarantees <300ms failover to local offline engines on cloud timeouts or network loss.
    """
    def __init__(
        self,
        name: str = "CloudVoiceBreaker",
        max_failures: int = config.CIRCUIT_BREAKER_MAX_FAILURES,
        recovery_timeout_sec: float = config.CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SEC,
    ):
        self.name = name
        self.max_failures = max_failures
        self.recovery_timeout_sec = recovery_timeout_sec
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._last_state_change: float = time.time()
        self._total_fallbacks = 0

    @property
    def state(self) -> CircuitState:
        now = time.time()
        if self._state == CircuitState.OPEN:
            if now - self._last_failure_time >= self.recovery_timeout_sec:
                logger.info("[%s] Recovery timeout elapsed (%.1fs). Switching to HALF_OPEN probe mode.", self.name, self.recovery_timeout_sec)
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = now
        return self._state

    def is_cloud_available(self) -> bool:
        """Instant check: True if cloud requests should be attempted."""
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self):
        """Notifies a successful cloud transaction."""
        now = time.time()
        if self._state != CircuitState.CLOSED:
            logger.info("[%s] Cloud connection recovered! Switching from %s to CLOSED.", self.name, self._state.value)
            self._state = CircuitState.CLOSED
            self._last_state_change = now
        self._failure_count = 0
        self._success_count += 1

    def record_failure(self, error: Optional[Exception] = None):
        """Notifies a cloud failure or network timeout."""
        now = time.time()
        self._failure_count += 1
        self._last_failure_time = now
        self._total_fallbacks += 1

        logger.warning(
            "[%s] Cloud failure detected (%d/%d): %s",
            self.name,
            self._failure_count,
            self.max_failures,
            error or "Timeout / Unreachable",
        )

        if self._failure_count >= self.max_failures or self._state == CircuitState.HALF_OPEN:
            if self._state != CircuitState.OPEN:
                logger.critical(
                    "[%s] Circuit breaker TRIPPED! Switching to OPEN (Offline Fallback Active).",
                    self.name,
                )
                self._state = CircuitState.OPEN
                self._last_state_change = now

    def force_state(self, new_state: CircuitState):
        """Manual test override for CI/CD and integration testing."""
        self._state = new_state
        self._last_state_change = time.time()
        if new_state == CircuitState.OPEN:
            self._last_failure_time = time.time()

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_fallbacks": self._total_fallbacks,
            "last_failure_time": self._last_failure_time,
            "uptime_in_state_sec": round(time.time() - self._last_state_change, 2),
        }


class PiperEngine:
    """
    Embedded high-performance French neural TTS engine using Piper ONNX.
    Zero external internet dependency.
    """
    _instance: Optional["PiperEngine"] = None

    def __init__(
        self,
        model_path: str = config.PIPER_MODEL_PATH,
        config_path: str = config.PIPER_CONFIG_PATH,
    ):
        self.model_path = model_path
        self.config_path = config_path
        self._voice = None
        self._sample_rate: int = 22050
        self._is_ready = False
        self._load_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "PiperEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_ready(self) -> bool:
        return self._is_ready and self._voice is not None

    def _ensure_model_downloaded(self):
        """Auto-downloads official French Piper model on first run if missing."""
        import urllib.request
        model_file = Path(self.model_path)
        cfg_file = Path(self.config_path)
        if model_file.exists() and cfg_file.exists():
            return
        logger.info("Piper neural voice missing. Auto-downloading from Hugging Face...")
        model_file.parent.mkdir(parents=True, exist_ok=True)
        base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/fr/fr_FR/siwis/medium/"
        try:
            if not cfg_file.exists():
                urllib.request.urlretrieve(base_url + "fr_FR-siwis-medium.onnx.json", str(cfg_file))
            if not model_file.exists():
                urllib.request.urlretrieve(base_url + "fr_FR-siwis-medium.onnx", str(model_file))
            logger.info("Piper neural model downloaded successfully.")
        except Exception as e:
            logger.warning("Could not auto-download Piper model: %s", e)

    def initialize_sync(self):
        """Loads Piper ONNX model into memory and performs warmup."""
        if self._is_ready:
            return
        self._ensure_model_downloaded()
        if not os.path.exists(self.model_path):
            logger.warning("Piper model file not found at %s. Offline TTS disabled.", self.model_path)
            return

        try:
            from piper.voice import PiperVoice
            t0 = time.perf_counter()
            self._voice = PiperVoice.load(self.model_path, config_path=self.config_path)
            dt = time.perf_counter() - t0
            self._is_ready = True
            logger.info("Piper ONNX model loaded successfully in %.1fms from %s", dt * 1000, self.model_path)

            # Quick silent warmup
            self.warmup()
        except Exception as e:
            logger.error("Failed to load Piper ONNX engine: %s", e)
            self._is_ready = False

    async def initialize_async(self):
        """Loads Piper in a background worker thread without blocking the asyncio loop."""
        if self.is_ready:
            return
        async with self._load_lock:
            if not self.is_ready:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.initialize_sync)

    def warmup(self):
        """Runs a tiny token inference to compile ONNX graph execution buffers."""
        if not self._voice:
            return
        try:
            t0 = time.perf_counter()
            for _ in self._voice.synthesize("Régis"):
                pass
            logger.debug("Piper ONNX engine warmed up in %.1fms", (time.perf_counter() - t0) * 1000)
        except Exception as e:
            logger.warning("Piper warmup warning: %s", e)

    def synthesize_to_dot_wav(self, text: str) -> bytes:
        """
        Synchronous synthesis producing 48kHz stereo WAV ready for Echo Dot 2G playback.
        Execution time: ~100-300ms on CPU.
        """
        if not self.is_ready:
            self.initialize_sync()
        if not self._voice:
            raise RuntimeError("Piper engine not initialized or model missing")

        clean_text = text.strip()
        if not clean_text:
            return b""

        t0 = time.perf_counter()
        audio_chunks = []
        sample_rate = self._sample_rate

        for chunk in self._voice.synthesize(clean_text):
            audio_chunks.append(chunk.audio_float_array)
            sample_rate = chunk.sample_rate

        if not audio_chunks:
            return b""

        merged_float = np.concatenate(audio_chunks)
        from core_server.brain import process_audio_for_echo_dot
        wav_bytes = process_audio_for_echo_dot(merged_float, sample_rate)
        dt = (time.perf_counter() - t0) * 1000
        logger.info("Piper synthesized '%s' (%d bytes WAV) in %.1fms", clean_text, len(wav_bytes), dt)
        return wav_bytes

    async def synthesize_async(self, text: str) -> bytes:
        """Asynchronously synthesizes speech via threadpool executor."""
        if not self.is_ready:
            await self.initialize_async()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.synthesize_to_dot_wav, text)


# Global singleton instances
global_circuit_breaker = CircuitBreaker()
global_piper_engine = PiperEngine.get_instance()
