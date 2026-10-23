"""
Audio processing pipeline for TAD Core.
Handles multichannel decoding, beamforming/channel extraction, VAD, and wake-word detection.
"""
import logging
import numpy as np
from openwakeword.model import Model
from core_server import config

logger = logging.getLogger("audio_processor")

import openwakeword

class AudioProcessor:
    def __init__(self, wake_model_name: str = config.WAKE_WORD_MODEL):
        logger.info("Initializing AudioProcessor with wake word model: %s", wake_model_name)
        self.wake_model_name = wake_model_name

        # Resolve model path from openwakeword pretrained resources
        all_models = openwakeword.get_pretrained_model_paths()
        target_path = None
        for p in all_models:
            if wake_model_name in p:
                target_path = p
                break

        if not target_path and all_models:
            target_path = all_models[0]

        logger.info("Loading wake word model from: %s", target_path)
        self.oww_model = Model(wakeword_model_paths=[target_path])
        self.model_key = list(self.oww_model.models.keys())[0]
        self.frame_buffer = bytearray()




    def unpack_raw_to_mono16(self, raw_bytes: bytes) -> np.ndarray:
        """
        Converts Echo Dot 9-channel S24_3LE raw frames to 16kHz mono int16.
        Each frame is 27 bytes (9 channels * 3 bytes).
        Channel 6 (center mic) starts at offset 18.
        The top 16 bits of 24-bit little endian are at offset +1 and +2.
        """
        self.frame_buffer.extend(raw_bytes)
        num_frames = len(self.frame_buffer) // config.FRAME_BYTES_RAW
        if num_frames == 0:
            return np.empty(0, dtype=np.int16)

        consumed_bytes = num_frames * config.FRAME_BYTES_RAW
        frame_chunk = self.frame_buffer[:consumed_bytes]
        del self.frame_buffer[:consumed_bytes]

        # Extract channel 6 high bytes into 16-bit PCM
        # Channel 6 byte 1 is at 18 + 1 = 19, byte 2 is at 18 + 2 = 20
        # Striding every 27 bytes:
        b1 = np.frombuffer(frame_chunk[19::27], dtype=np.uint8)
        b2 = np.frombuffer(frame_chunk[20::27], dtype=np.int8)

        # Recombine into signed 16-bit integer: (b2 << 8) | b1
        mono_int16 = (b2.astype(np.int16) << 8) | b1.astype(np.int16)
        return mono_int16

    def calculate_rms(self, samples: np.ndarray) -> float:
        """Calculates Root Mean Square volume of audio samples."""
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

    def process_wake_word(self, samples_16bit: np.ndarray) -> bool:
        """
        Feeds samples to openWakeWord model.
        Returns True if wake word confidence exceeds threshold.
        """
        if len(samples_16bit) < 1280: # openWakeWord standard chunk is 1280 samples (80ms)
            return False

        # Run prediction
        prediction = self.oww_model.predict(samples_16bit)
        score = prediction.get(self.model_key, 0.0)
        if score >= config.WAKE_WORD_THRESHOLD:
            logger.info("Wake word detected! Model: %s, Score: %.3f", self.model_key, score)
            self.oww_model.reset()
            return True
        return False

