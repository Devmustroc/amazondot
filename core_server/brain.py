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
from google import genai
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
        
        # Initialize Gemini Client if key available
        self.gemini_client = None
        if config.GEMINI_API_KEY:
            try:
                self.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
                logger.info("Gemini API Client initialized with model %s", config.GEMINI_MODEL)
            except Exception as e:
                logger.warning("Failed to initialize Gemini Client: %s", e)
        else:
            logger.info("No GEMINI_API_KEY set. Local fallback logic will be used.")

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
        """Sends user prompt to Gemini or returns intelligent local response."""
        if not prompt.strip():
            return "Je ne vous ai pas bien entendu, pouvez-vous répéter ?"

        logger.info("Generating response for: '%s'", prompt)

        # 1. Try Gemini Cloud AI
        if self.gemini_client:
            try:
                response = self.gemini_client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=[
                        {"role": "user", "parts": [{"text": f"{config.SYSTEM_PROMPT}\n\nUtilisateur: {prompt}"}]}
                    ]
                )
                if response and response.text:
                    reply = response.text.strip()
                    logger.info("Gemini response: %s", reply)
                    return reply
            except Exception as e:
                logger.error("Gemini API call failed, falling back to local: %s", e)

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
        Synthesizes text to 48kHz 16-bit stereo WAV audio using edge-tts.
        Matches Echo Dot hardware DAC requirements (48kHz 2-channel).
        """
        logger.info("Synthesizing speech: '%s'", text)
        try:
            comm = edge_tts.Communicate(text, config.TTS_VOICE)
            mp3_stream = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_stream.extend(chunk["data"])

            # Read MP3 in memory
            data, sr = sf.read(io.BytesIO(mp3_stream))

            # Resample to 48000 Hz (Echo Dot hardware DAC native rate)
            target_sr = 48000
            if sr != target_sr:
                new_len = int(round(len(data) * target_sr / sr))
                data = sps.resample(data, new_len)

            # Ensure stereo (2 channels)
            if len(data.shape) == 1:
                data = np.column_stack([data, data])
            elif data.shape[1] == 1:
                data = np.column_stack([data[:, 0], data[:, 0]])

            # Export to 16-bit PCM WAV in memory
            out_buf = io.BytesIO()
            sf.write(out_buf, data, target_sr, format="WAV", subtype="PCM_16")
            return out_buf.getvalue()
        except Exception as e:
            logger.error("Error during TTS synthesis: %s", e)
            return b""
