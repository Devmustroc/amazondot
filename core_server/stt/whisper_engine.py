"""
STT Subsystem for SovereignDot.
Provides Whisper speech-to-text inference and phonetic corrections for French voice inputs.
"""
import logging
import numpy as np
from faster_whisper import WhisperModel
from core_server import config

logger = logging.getLogger("stt")


class WhisperSTTEngine:
    """Encapsulates Faster-Whisper model loading, inference, and French phonetic corrections."""

    def __init__(self, model_size: str = None, device: str = "cpu", compute_type: str = "int8"):
        model_name = model_size or config.WHISPER_MODEL
        logger.info("Initializing WhisperSTTEngine with model '%s' on %s (%s)...", model_name, device, compute_type)
        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type, local_files_only=True)
        except Exception:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, pcm_16k_bytes: bytes) -> str:
        """
        Transcribes 16kHz 16-bit mono PCM into French text using Whisper.
        Applies phonetic normalization for common French speech ambiguities.
        """
        if not pcm_16k_bytes:
            return ""

        try:
            raw_s16 = np.frombuffer(pcm_16k_bytes, dtype=np.int16)
            if len(raw_s16) == 0:
                return ""

            rms = float(np.sqrt(np.mean(raw_s16.astype(np.float32) ** 2)))
            logger.info("Audio to transcribe: %d samples (%.2fs), RMS=%.1f", len(raw_s16), len(raw_s16) / 16000.0, rms)

            samples = raw_s16.astype(np.float32) / 32768.0
            segments, info = self.model.transcribe(
                samples,
                language="fr",
                beam_size=config.WHISPER_BEAM_SIZE,
                best_of=1,
                temperature=0.0,
                without_timestamps=True,
                initial_prompt="Bonjour Régis. Quelle heure est-il ? Quel jour sommes-nous ? Comment vas-tu ? Quelle est la météo ?",
                condition_on_previous_text=False,
                vad_filter=False,
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
