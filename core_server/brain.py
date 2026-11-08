"""
TAD Brain Module.
Integrates Whisper Speech-to-Text, Gemini AI LLM inference, and Edge-TTS synthesis.
"""
import io
import os
import re
import json
import hashlib
import logging
import asyncio
from typing import Optional, AsyncGenerator
from pathlib import Path
import numpy as np
import scipy.signal as sps
import soundfile as sf
import edge_tts
from faster_whisper import WhisperModel
from openai import OpenAI, AsyncOpenAI
from core_server import config
from core_server import homelab_tools
from core_server.intents import global_intent_registry, IntentContext

logger = logging.getLogger("brain")

def process_audio_for_echo_dot(data: np.ndarray, sr: int) -> bytes:
    """
    Applies Echo Dot 2G hardware acoustic processing:
    1. Resample to 48kHz native DAC sample rate.
    2. 2nd-order High-Pass filter at 220Hz (cuts sub-bass that causes 35mm transducer rattling and clipping).
    3. Soft peak limiting to 0.65 (-3.7 dBFS) to keep the internal Class-D amplifier in its linear low-THD range.
    4. Export to 48kHz 16-bit stereo WAV.
    """
    target_sr = 48000
    if sr != target_sr:
        from math import gcd
        g = gcd(target_sr, sr)
        data = sps.resample_poly(data, target_sr // g, sr // g)

    # Highpass filter at 220Hz to eliminate speaker overload and acoustic rattling
    b, a = sps.butter(2, 220.0 / (target_sr / 2.0), btype='highpass')
    data = sps.lfilter(b, a, data, axis=0)

    # Peak normalization to 0.65 to prevent amplifier clipping
    peak = float(np.max(np.abs(data)))
    if peak > 0.001:
        data = (data / peak) * 0.65

    data = np.clip(data, -1.0, 1.0)

    # Ensure stereo (2 channels)
    if len(data.shape) == 1:
        data = np.column_stack([data, data])
    elif data.shape[1] == 1:
        data = np.column_stack([data[:, 0], data[:, 0]])

    out_buf = io.BytesIO()
    sf.write(out_buf, data, target_sr, format="WAV", subtype="PCM_16")
    return out_buf.getvalue()

from core_server.obsidian_memory import ObsidianMemory
from core_server.mcp_client import McpManager
from core_server.resilience import global_circuit_breaker, global_piper_engine, CircuitState
from core_server.voice_id import global_voice_id, UserRole, SpeakerProfile
import requests

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

class Brain:
    def __init__(self):
        logger.info("Initializing Brain (Whisper STT, Hybrid LLM, Obsidian Memory, MCP, TTS Cache)...")
        # 1. Load local Whisper STT
        try:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        
        # 2. Obsidian Memory
        self.obsidian = ObsidianMemory()

        # 3. MCP Manager (tools)
        self.mcp = McpManager()

        # 4. OpenRouter Jev Router & Async Models
        self.llm_client = None
        self.async_llm_client = None
        if config.OPENROUTER_API_KEY:
            try:
                self.llm_client = OpenAI(
                    api_key=config.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                self.async_llm_client = AsyncOpenAI(
                    api_key=config.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                logger.info("OpenRouter client initialized (Router: typesafe/jev-router, Model: %s)", config.OPENROUTER_MODEL)
            except Exception as e:
                logger.warning("Failed to initialize OpenRouter client: %s", e)

        # 5. Local Ollama Settings
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
        self.router_model = os.getenv("OPENROUTER_ROUTER_MODEL", "typesafe/jev-router")

        # 6. Low-Latency TTS Cache (Disk + RAM)
        self.cache_dir = Path(config.BASE_DIR) / "core_server" / "tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._tts_ram_cache: dict[str, bytes] = {}
        self._load_disk_cache()

        # 7. Offline Resilience Circuit Breaker & Piper TTS
        self.circuit_breaker = global_circuit_breaker
        self.piper = global_piper_engine

        # 8. VoiceID & Biometric RBAC Security
        self.voice_id = global_voice_id

        # In-memory conversation history
        self.history = []

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
                    self._tts_ram_cache[phrase] = p.read_bytes()
                    loaded += 1
                except Exception:
                    pass
        if loaded > 0:
            logger.info("Loaded %d common acknowledgment audio phrases into RAM cache.", loaded)

    async def initialize(self):
        """Asynchronous initialization of external services (MCP, Piper, etc.)."""
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
        try:
            raw_s16 = np.frombuffer(pcm_16k_bytes, dtype=np.int16)
            rms = float(np.sqrt(np.mean(raw_s16.astype(np.float32) ** 2))) if len(raw_s16) > 0 else 0.0
            logger.info("Audio to transcribe: %d samples (%.2fs), RMS=%.1f", len(raw_s16), len(raw_s16)/16000.0, rms)
            
            samples = raw_s16.astype(np.float32) / 32768.0
            segments, info = self.whisper.transcribe(
                samples,
                language="fr",
                beam_size=config.WHISPER_BEAM_SIZE,
                best_of=1,
                temperature=0.0,
                without_timestamps=True,
                initial_prompt="Bonjour Régis. Quelle heure est-il ? Quel jour sommes-nous ? Comment vas-tu ? Quelle est la météo ?",
                condition_on_previous_text=False,
                vad_filter=False
            )
            transcription = " ".join([seg.text for seg in segments]).strip()

            # Phonetic post-processing corrections for Whisper tiny on French speech
            t_lower = transcription.lower()
            if any(p in t_lower for p in ["qu'est-ce que leur est-il", "qu'elle heure est-il", "quel heure est-il", "qu'est ce que leur est il", "qu'est ce que l'heure est il"]):
                transcription = "Quelle heure est-il ?"
            elif any(p in t_lower for p in ["quel jour on est", "quel jour nous sommes", "on est quel jour"]):
                transcription = "Quel jour sommes-nous ?"

            logger.info("Transcription: '%s' (language=%s, prob=%.2f)", transcription, info.language, info.language_probability)
            return transcription
        except Exception as e:
            logger.error("Error during transcription: %s", e)
            return ""

    def _query_ollama(self, messages: list) -> Optional[str]:
        """Calls local Ollama instance (Qwen 2.5). Fast and 100% private."""
        try:
            r = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 128}
                },
                timeout=4.0
            )
            if r.status_code == 200:
                reply = r.json().get("message", {}).get("content", "").strip()
                if reply:
                    logger.info("Ollama (%s) replied: %s", self.ollama_model, reply)
                    return reply
        except Exception as e:
            logger.warning("Local Ollama query failed: %s", e)
        return None

    async def generate_response_stream(self, prompt: str, speaker_audio: Optional[bytes] = None) -> AsyncGenerator[str, None]:
        """
        Streaming generator yielding sentence-by-sentence chunks for ultra-low latency voice responses:
        - VoiceID: Speaker identification & RBAC security check (<20ms).
        - Instant Intents: clock, date, identity, obsidian learning (0ms latency).
        - Simple Queries: Fast local Ollama with sentence splitting (<500ms).
        - Reasoning & Tools: OpenRouter / Gemini 3.8 Flash with native token-to-sentence streaming.
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
        p_lower = prompt.lower()
        clean_prompt = re.sub(r'^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*', '', prompt, flags=re.IGNORECASE).strip() or prompt
        clean_p_lower = clean_prompt.lower()
        from datetime import datetime
        now = datetime.now()

        # Dispatch through decoupled Voice Intent Registry (Extensible Skills)
        intent_ctx = IntentContext(
            prompt=prompt,
            clean_prompt=clean_prompt,
            speaker=speaker,
            obsidian=self.obsidian,
            circuit_breaker=self.circuit_breaker,
            mcp=self.mcp,
        )
        intent_generator = await global_intent_registry.handle_prompt(intent_ctx)
        if intent_generator is not None:
            async for reply in intent_generator:
                logger.info("Intent Executed Spoken Response: '%s'", reply)
                yield reply
            return

        # Build dynamic system prompt with live date/time, speaker identity and query-relevant Obsidian knowledge
        now_str = now.strftime("%A %d %B %Y à %H:%M")
        obsidian_context = self.obsidian.get_relevant_context(prompt)
        dynamic_system_prompt = f"{config.SYSTEM_PROMPT}\nDate et heure courantes: {now_str}\nLocuteur identifié: {speaker.name} (Rôle: {speaker.role.value})\n\nContexte et mémoire connus:\n{obsidian_context}"

        messages = [{"role": "system", "content": dynamic_system_prompt}]
        messages.extend(self.history[-6:])
        messages.append({"role": "user", "content": prompt})

        # Router Classifier
        complex_triggers = ["cherche", "recherche", "suricate", "suricata", "proxmox", "opensense", "opnsense",
                            "notion", "firewall", "internet", "pourquoi", "explique", "détaille", "compare",
                            "météo de demain", "homelab", "serveur", "serveurs", "vm", "conteneur", "docker"]
        is_complex = any(k in p_lower for k in complex_triggers) or len(prompt.split()) > 14

        # A. Try Local Ollama first if prompt is simple/routine
        if not is_complex:
            logger.info("Routing simple/routine prompt to Local Ollama (%s)...", self.ollama_model)
            loop = asyncio.get_running_loop()
            ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
            if ollama_reply:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": ollama_reply})
                for s in self._split_into_sentences(ollama_reply):
                    yield s
                return

        # B. Route to OpenRouter / Gemini 3.8 Flash with native streaming (if circuit is closed)
        if self.async_llm_client and self.circuit_breaker.is_cloud_available():
            try:
                logger.info("Routing to OpenRouter JEV / Gemini (%s)...", config.OPENROUTER_MODEL)
                tools = self.mcp.get_openai_tools()

                # If tools are relevant, run tool calling turn first
                if tools and any(k in p_lower for k in ["proxmox", "docker", "suricata", "serveur", "vm", "conteneur", "opnsense", "status"]):
                    response = await self.async_llm_client.chat.completions.create(
                        model=self.router_model,
                        messages=messages,
                        tools=tools,
                        max_tokens=256,
                        temperature=0.7,
                    )
                    message = response.choices[0].message
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tc in message.tool_calls:
                            func_name = tc.function.name
                            try:
                                args = json.loads(tc.function.arguments)
                            except Exception:
                                args = {}
                            logger.info("LLM triggered tool: %s with args: %s", func_name, args)
                            tool_res = await self.mcp.call_tool(func_name, args)
                            messages.append(message)
                            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_res})

                # Stream final formulated response tokens to sentence generator
                stream = await self.async_llm_client.chat.completions.create(
                    model=config.OPENROUTER_MODEL,
                    messages=messages,
                    max_tokens=256,
                    temperature=0.7,
                    stream=True,
                )

                full_reply = ""
                token_buffer = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if not delta:
                        continue
                    full_reply += delta
                    token_buffer += delta

                    match = re.search(r'([.!?]+(\s+|$))', token_buffer)
                    if match:
                        end_pos = match.end()
                        sentence = token_buffer[:end_pos].strip()
                        if not re.search(r'\d\.\d$', sentence) and len(sentence) >= 5:
                            yield sentence
                            token_buffer = token_buffer[end_pos:]

                if token_buffer.strip():
                    yield token_buffer.strip()

                if full_reply.strip():
                    self.circuit_breaker.record_success()
                    self.history.append({"role": "user", "content": prompt})
                    self.history.append({"role": "assistant", "content": full_reply.strip()})
                    return
            except Exception as e:
                self.circuit_breaker.record_failure(e)
                logger.error("OpenRouter streaming call failed, falling back to local Ollama: %s", e)

        # C. Fallback to Local Ollama
        loop = asyncio.get_running_loop()
        ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
        if ollama_reply:
            for s in self._split_into_sentences(ollama_reply):
                yield s
            return

        # D. Ultimate Hardcoded Fallbacks
        if "heure" in p_lower:
            import datetime
            yield f"Il est actuellement {datetime.datetime.now().strftime('%H heures %M')}."
            return
        yield "J'ai bien entendu votre demande, mais je n'ai pas pu joindre mes moteurs de réflexion."

    def _split_into_sentences(self, text: str) -> list[str]:
        """Splits full text into natural sentences for progressive audio playback."""
        raw_chunks = re.split(r'(?<=[.!?])\s+', text.strip())
        return [c.strip() for c in raw_chunks if c.strip()]

    async def generate_response(self, prompt: str, speaker_audio: Optional[bytes] = None) -> str:
        """Non-streaming backward-compatible response wrapper."""
        chunks = []
        async for s in self.generate_response_stream(prompt, speaker_audio=speaker_audio):
            chunks.append(s)
        return " ".join(chunks).strip()

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
        if config.TTS_CACHE_ENABLED and text_clean in self._tts_ram_cache:
            logger.debug("TTS Cache HIT (RAM): '%s'", text_clean)
            return self._tts_ram_cache[text_clean]

        # Tier 2: On-Disk Cache
        cache_file = self._get_cache_path(text_clean)
        if config.TTS_CACHE_ENABLED and cache_file.exists():
            try:
                wav_data = cache_file.read_bytes()
                self._tts_ram_cache[text_clean] = wav_data
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
                    self._tts_ram_cache[text_clean] = wav_data
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
                self._tts_ram_cache[text_clean] = wav_data
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
                        self._tts_ram_cache[text_clean] = wav_data
                        try:
                            cache_file.write_bytes(wav_data)
                        except Exception:
                            pass
                    return wav_data
                except Exception as e_pip:
                    logger.error("Piper fallback synthesis failed: %s", e_pip)
                    return b""
            return b""
