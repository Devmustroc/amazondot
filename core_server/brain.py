"""
TAD Brain Module.
Integrates Whisper Speech-to-Text, Gemini AI LLM inference, and Edge-TTS synthesis.
"""
import io
import os
import json
import logging
import asyncio
import numpy as np
import scipy.signal as sps
import soundfile as sf
import edge_tts
from typing import Optional
from faster_whisper import WhisperModel
from openai import OpenAI
from core_server import config

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
import requests

class Brain:
    def __init__(self):
        logger.info("Initializing Brain (Whisper STT, Hybrid LLM, Obsidian Memory, MCP)...")
        # 1. Load local Whisper STT
        try:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        
        # 2. Obsidian Memory
        self.obsidian = ObsidianMemory()

        # 3. MCP Manager (tools)
        self.mcp = McpManager()

        # 4. OpenRouter Jev Router & Models
        self.llm_client = None
        if config.OPENROUTER_API_KEY:
            try:
                self.llm_client = OpenAI(
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

        # In-memory conversation history
        self.history = []

    async def initialize(self):
        """Asynchronous initialization of external services (MCP, etc.)."""
        try:
            await self.mcp.initialize()
        except Exception as e:
            logger.warning("Error initializing MCP manager: %s", e)

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
                beam_size=5,
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
                timeout=6.0
            )
            if r.status_code == 200:
                reply = r.json().get("message", {}).get("content", "").strip()
                if reply:
                    logger.info("Ollama (%s) replied: %s", self.ollama_model, reply)
                    return reply
        except Exception as e:
            logger.warning("Local Ollama query failed: %s", e)
        return None

    async def generate_response(self, prompt: str) -> str:
        """
        Processes user prompt via Hybrid Decision Engine:
        - Instant Intents: clock time, date, identity (0ms latency, zero hallucination).
        - Memory Learning: detects and saves new family facts to Obsidian.
        - Fast Local: simple, polite, or quick queries answered by Ollama (<700ms).
        - Reasoning & Tools: complex queries routed via OpenRouter JEV Router to Gemini 3.8 Flash + MCP.
        """
        if not prompt.strip():
            return "Je ne vous ai pas bien entendu, pouvez-vous répéter ?"

        logger.info("Evaluating prompt: '%s'", prompt)
        p_lower = prompt.lower()
        from datetime import datetime
        now = datetime.now()

        # 1. Instant Intent: Heure actuelle
        if any(k in p_lower for k in ["heure est-il", "l'heure", "il est quelle heure", "donne-moi l'heure", "donne l'heure"]):
            h = now.hour
            m = now.minute
            m_str = "pile" if m == 0 else f"{m:02d}" if m < 10 else str(m)
            h_str = f"{h} heure{'s' if h > 1 else ''}"
            reply = f"Il est actuellement {h_str} {m_str}."
            logger.info("Instant Time Intent triggered: '%s'", reply)
            return reply

        # 2. Instant Intent: Date et Jour actuel
        if any(k in p_lower for k in ["quel jour", "la date", "date d'aujourd'hui", "on est quel jour"]):
            jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
            mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
            reply = f"Nous sommes le {jours[now.weekday()]} {now.day} {mois[now.month - 1]} {now.year}."
            logger.info("Instant Date Intent triggered: '%s'", reply)
            return reply

        # 3. Instant Intent: Identité
        if any(k in p_lower for k in ["qui es-tu", "comment tu t'appelles", "présente-toi", "t'es qui"]):
            return "Je m'appelle Régis, je suis l'assistant vocal IA familial pour la maison de El Mustapha."

        # 4. Fact Learning in Obsidian Vault
        import re
        learn_match = re.search(r'(retiens que|souviens-toi que|note que|enregistre que)\s+(.*)', p_lower)
        if learn_match:
            fact_text = learn_match.group(2).strip()
            self.obsidian.record_fact("Famille", fact_text)
            reply = f"C'est bien noté dans ma mémoire, j'ai enregistré que {fact_text}."
            return reply

        # Build dynamic system prompt with live date/time and Obsidian knowledge
        now_str = now.strftime("%A %d %B %Y à %H:%M")
        obsidian_context = self.obsidian.get_context_summary()
        dynamic_system_prompt = f"{config.SYSTEM_PROMPT}\nDate et heure courantes: {now_str}\n\nContexte familial et Homelab connu:\n{obsidian_context}"

        messages = [{"role": "system", "content": dynamic_system_prompt}]
        messages.extend(self.history[-6:])
        messages.append({"role": "user", "content": prompt})

        # 2. Fast Router Classifier: Decide whether to route locally or to JEV
        complex_triggers = ["cherche", "recherche", "suricate", "suricata", "proxmox", "opensense", "opnsense",
                            "notion", "firewall", "internet", "pourquoi", "explique", "détaille", "compare", "météo de demain"]
        is_complex = any(k in p_lower for k in complex_triggers) or len(prompt.split()) > 14

        # A. Try Local Ollama first if prompt is simple/routine
        if not is_complex:
            logger.info("Routing simple/routine prompt to Local Ollama (%s)...", self.ollama_model)
            loop = asyncio.get_running_loop()
            ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
            if ollama_reply:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": ollama_reply})
                return ollama_reply

        # B. Route to OpenRouter JEV Router for reasoning, tool use or complex questions
        if self.llm_client:
            try:
                logger.info("Routing to OpenRouter JEV Router (%s)...", self.router_model)
                tools = self.mcp.get_openai_tools()
                kwargs = {
                    "model": self.router_model,
                    "messages": messages,
                    "max_tokens": 256,
                    "temperature": 0.7,
                }
                if tools:
                    kwargs["tools"] = tools

                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None, lambda: self.llm_client.chat.completions.create(**kwargs)
                )
                message = response.choices[0].message

                # Handle tool calls if returned
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
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_res
                        })

                    # Second turn after tool output
                    second_resp = await loop.run_in_executor(
                        None,
                        lambda: self.llm_client.chat.completions.create(
                            model=config.OPENROUTER_MODEL,
                            messages=messages,
                            max_tokens=256,
                        ),
                    )
                    reply = second_resp.choices[0].message.content.strip()
                else:
                    reply = message.content.strip()

                logger.info("JEV/OpenRouter response: %s", reply)
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": reply})
                return reply
            except Exception as e:
                logger.error("OpenRouter JEV call failed, trying local fallback: %s", e)

        # C. Fallback to Local Ollama if not already tried
        loop = asyncio.get_running_loop()
        ollama_reply = await loop.run_in_executor(None, self._query_ollama, messages)
        if ollama_reply:
            return ollama_reply

        # D. Ultimate Hardcoded Fallbacks
        if "heure" in p_lower:
            import datetime
            return f"Il est actuellement {datetime.datetime.now().strftime('%H heures %M')}."
        return "J'ai bien entendu votre demande, mais je n'ai pas pu joindre mes moteurs de réflexion."

    async def synthesize_speech(self, text: str) -> bytes:
        """
        Synthesizes text to crystal-clear 48kHz 16-bit stereo WAV.
        Uses OpenRouter google/gemini-3.8-flash-lite-tts first, with Edge-TTS as fallback.
        Includes acoustic filtering and peak limiting to prevent physical speaker rattling/saturation.
        """
        if not text.strip():
            return b""

        logger.info("Synthesizing speech: '%s'", text)

        # 1. Try OpenRouter Gemini TTS (google/gemini-3.8-flash-lite-tts)
        if config.OPENROUTER_API_KEY:
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": config.OPENROUTER_TTS_MODEL,
                    "input": text,
                    "voice": config.OPENROUTER_TTS_VOICE,
                    "response_format": "pcm",
                }
                logger.info("Requesting Gemini TTS from OpenRouter (%s, voice=%s)...",
                            config.OPENROUTER_TTS_MODEL, config.OPENROUTER_TTS_VOICE)

                loop = asyncio.get_running_loop()
                r = await loop.run_in_executor(
                    None,
                    lambda: requests.post(
                        "https://openrouter.ai/api/v1/audio/speech",
                        headers=headers,
                        json=payload,
                        timeout=12
                    )
                )

                if r.status_code == 200 and len(r.content) > 0:
                    raw_pcm = r.content
                    logger.info("Gemini TTS returned %d bytes PCM (24kHz mono)", len(raw_pcm))
                    # Gemini returns 24kHz 16-bit mono PCM, convert to float in [-1.0, 1.0]
                    s16_mono = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                    wav_data = process_audio_for_echo_dot(s16_mono, 24000)
                    logger.info("Acoustically processed Gemini TTS audio (%d bytes)", len(wav_data))
                    return wav_data
                else:
                    logger.warning("OpenRouter TTS returned HTTP %d: %s. Using Edge-TTS fallback.",
                                   r.status_code, r.text[:200])
            except Exception as e:
                logger.warning("OpenRouter TTS failed (%s). Falling back to Edge-TTS.", e)

        # 2. Fallback: Edge-TTS
        try:
            logger.info("Synthesizing speech via Edge-TTS fallback (%s)...", config.TTS_VOICE)
            comm = edge_tts.Communicate(text, config.TTS_VOICE)
            mp3_stream = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_stream.extend(chunk["data"])

            data, sr = sf.read(io.BytesIO(mp3_stream))
            wav_data = process_audio_for_echo_dot(data, sr)
            return wav_data
        except Exception as e:
            logger.error("Edge-TTS synthesis failed: %s", e)
            return b""
