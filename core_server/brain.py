"""
TAD Brain Module.
Integrates Whisper Speech-to-Text, Gemini AI LLM inference, and Edge-TTS synthesis.
"""
import io
import logging
import asyncio
import numpy as np
import scipy.signal as sps
import soundfile as sf
import edge_tts
from faster_whisper import WhisperModel
from openai import OpenAI
from core_server import config

logger = logging.getLogger("brain")

class Brain:
    def __init__(self):
        logger.info("Initializing Brain (Whisper STT, Gemini Client, Edge-TTS)...")
        # Load local Whisper STT (offline)
        try:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8", local_files_only=True)
        except Exception:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        
        # Initialize OpenRouter client
        self.llm_client = None
        if config.OPENROUTER_API_KEY:
            try:
                self.llm_client = OpenAI(
                    api_key=config.OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                logger.info("OpenRouter client initialized with model %s", config.OPENROUTER_MODEL)
            except Exception as e:
                logger.warning("Failed to initialize OpenRouter client: %s", e)
        else:
            logger.info("No OPENROUTER_API_KEY set. Local fallback logic will be used.")

        # In-memory conversation history
        self.history = []

    def transcribe(self, pcm_16k_bytes: bytes) -> str:
        """Transcribes 16kHz 16-bit mono PCM into French text using Whisper."""
        try:
            raw_s16 = np.frombuffer(pcm_16k_bytes, dtype=np.int16)
            rms = float(np.sqrt(np.mean(raw_s16.astype(np.float32) ** 2))) if len(raw_s16) > 0 else 0.0
            logger.info("Audio to transcribe: %d samples (%.2fs), RMS=%.1f, range=[%d, %d]",
                        len(raw_s16), len(raw_s16)/16000.0, rms, raw_s16.min() if len(raw_s16) else 0, raw_s16.max() if len(raw_s16) else 0)
            
            try:
                sf.write("tools/debug_transcribe.wav", raw_s16, 16000)
            except Exception:
                pass

            samples = raw_s16.astype(np.float32) / 32768.0
            segments, info = self.whisper.transcribe(
                samples,
                language="fr",
                beam_size=5,
                initial_prompt="Régis",
                condition_on_previous_text=False,
                vad_filter=False
            )
            transcription = " ".join([seg.text for seg in segments]).strip()
            logger.info("Transcription: '%s' (language=%s, prob=%.2f)", transcription, info.language, info.language_probability)
            return transcription
        except Exception as e:
            logger.error("Error during transcription: %s", e)
            return ""

    def generate_response(self, prompt: str) -> str:
        """Sends user prompt to Gemini 3.8 Flash via OpenRouter or returns intelligent local response."""
        if not prompt.strip():
            return "Je ne vous ai pas bien entendu, pouvez-vous répéter ?"

        logger.info("Generating response with Gemini for: '%s'", prompt)

        # 1. Try OpenRouter LLM (Gemini 3.8 Flash)
        if self.llm_client:
            try:
                messages = [{"role": "system", "content": config.SYSTEM_PROMPT}]
                # Add up to 6 recent turns of history
                messages.extend(self.history[-6:])
                messages.append({"role": "user", "content": prompt})

                response = self.llm_client.chat.completions.create(
                    model=config.OPENROUTER_MODEL,
                    messages=messages,
                    max_tokens=256,
                    temperature=0.7,
                )
                reply = response.choices[0].message.content.strip()
                logger.info("Gemini (%s) response: %s", config.OPENROUTER_MODEL, reply)

                # Update history
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": reply})
                if len(self.history) > 10:
                    self.history = self.history[-10:]

                return reply
            except Exception as e:
                logger.error("OpenRouter LLM API call failed, falling back to local: %s", e)

        # 2. Local Fallback Responses
        p_lower = prompt.lower()
        if "bonjour" in p_lower or "salut" in p_lower:
            return "Bonjour ! Je suis Régis. Comment puis-je vous aider aujourd'hui ?"
        elif "qui es-tu" in p_lower or "qui t'appelle" in p_lower or "nom" in p_lower:
            return "Je m'appelle Régis, votre assistant vocal personnel."
        elif "heure" in p_lower:
            import datetime
            now = datetime.datetime.now().strftime("%H heures %M")
            return f"Il est actuellement {now}."
        elif "météo" in p_lower:
            return "La météo est clémente avec quelques nuages et une température agréable."
        else:
            return f"J'ai bien compris : {prompt}. Que souhaitez-vous que je fasse ?"

    async def synthesize_speech(self, text: str) -> bytes:
        """
        Synthesizes text to 48kHz 16-bit stereo WAV via Edge-TTS.
        Matches Echo Dot hardware DAC requirements (48kHz 2-channel 16-bit PCM).
        """
        if not text.strip():
            return b""

        logger.info("Synthesizing speech via Edge-TTS: '%s'", text)
        try:
            comm = edge_tts.Communicate(text, config.TTS_VOICE)
            mp3_stream = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_stream.extend(chunk["data"])

            data, sr = sf.read(io.BytesIO(mp3_stream))

            target_sr = 48000
            if sr != target_sr:
                from math import gcd
                g = gcd(target_sr, sr)
                data = sps.resample_poly(data, target_sr // g, sr // g)
            data = np.clip(data, -1.0, 1.0)

            if len(data.shape) == 1:
                data = np.column_stack([data, data])
            elif data.shape[1] == 1:
                data = np.column_stack([data[:, 0], data[:, 0]])

            out_buf = io.BytesIO()
            sf.write(out_buf, data, target_sr, format="WAV", subtype="PCM_16")
            return out_buf.getvalue()
        except Exception as e:
            logger.error("Edge-TTS synthesis failed: %s", e)
            return b""
