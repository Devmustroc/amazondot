"""
Audio processing pipeline for TAD Core.
Handles multichannel decoding, beamforming/channel extraction, VAD, and wake-word detection.
"""
import logging
import numpy as np
import scipy.signal
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

        # Neural Voice Activity Detector (VAD)
        self.vad = openwakeword.VAD()

        # 4th-order Butterworth high-pass filter at 150Hz to eliminate 50Hz/100Hz ground hum & DC bias
        self.sos = scipy.signal.butter(4, 150, btype='highpass', fs=16000, output='sos')
        self.zi = scipy.signal.sosfilt_zi(self.sos)

    def is_speech(self, samples_16bit: np.ndarray) -> bool:
        """Returns True if human speech is detected by neural VAD."""
        if len(samples_16bit) < 1280:
            return False
        prob = self.vad.predict(samples_16bit)
        return float(prob) > 0.15

    def unpack_raw_to_mono16(self, raw_bytes: bytes) -> np.ndarray:
        """
        Converts Echo Dot 9-channel raw frames to 16kHz mono int16.
        Each frame has 9 channels * 3 bytes = 27 bytes.
        Channel 6 is the omnidirectional center microphone (starts at offset 18).
        Channels 0 to 5 are the outer circular microphones.
        Blends 60% center mic + 40% outer array average to avoid phase cancellation,
        with 1.5x gain boost and 150Hz Butterworth highpass filter.
        """
        self.frame_buffer.extend(raw_bytes)
        num_frames = len(self.frame_buffer) // config.FRAME_BYTES_RAW
        if num_frames == 0:
            return np.empty(0, dtype=np.int16)

        consumed_bytes = num_frames * config.FRAME_BYTES_RAW
        frame_chunk = self.frame_buffer[:consumed_bytes]
        del self.frame_buffer[:consumed_bytes]

        # Extract Center Microphone (Channel 6)
        c_offset = 6 * 3  # 18
        c_b1 = np.frombuffer(frame_chunk[c_offset+1::27], dtype=np.uint8)
        c_b2 = np.frombuffer(frame_chunk[c_offset+2::27], dtype=np.int8)
        center_mic = ((c_b2.astype(np.int16) << 8) | c_b1.astype(np.int16)).astype(np.float32)

        # Outer microphones (channels 0..5)
        outer_acc = np.zeros(num_frames, dtype=np.float32)
        for ch in range(6):
            offset = ch * 3
            b1 = np.frombuffer(frame_chunk[offset+1::27], dtype=np.uint8)
            b2 = np.frombuffer(frame_chunk[offset+2::27], dtype=np.int8)
            outer_acc += ((b2.astype(np.int16) << 8) | b1.astype(np.int16)).astype(np.float32)

        mono_float = (0.60 * center_mic + 0.40 * (outer_acc / 6.0)) * 1.5
        # High-pass filter (150Hz cutoff)
        filtered_float, self.zi = scipy.signal.sosfilt(self.sos, mono_float, zi=self.zi)
        mono_int16 = np.clip(filtered_float, -32768, 32767).astype(np.int16)
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
        if len(samples_16bit) < 1280:
            return False

        # Run prediction
        prediction = self.oww_model.predict(samples_16bit)
        score = prediction.get(self.model_key, 0.0)
        if score >= 0.1:
            logger.debug("Wake word score: %.3f (threshold=%.2f)", score, config.WAKE_WORD_THRESHOLD)

        if score >= config.WAKE_WORD_THRESHOLD:
            logger.info("Wake word detected! Model: %s, Score: %.3f", self.model_key, score)
            self.oww_model.reset()
            return True
        return False


