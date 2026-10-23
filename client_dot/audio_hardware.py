"""
Audio hardware interface for Amazon Echo Dot 2nd Gen (MediaTek MT8163).
Verified reverse-engineering parameters:
- Capture Device: Card 0, Device 1 (MultiMedia1_Capture, S16_LE, 16000Hz, mono/stereo)
- Playback Device: Card 0, Device 0 (tinyctlplay / tinyplay, 16000Hz, 16-bit)
- LED Controller: /system/bin/ledctrl
"""
import subprocess
import logging

logger = logging.getLogger("audio_hardware")

class AudioHardware:
    CARD = 0
    CAPTURE_DEVICE = 1     # MultiMedia1_Capture
    PLAYBACK_DEVICE = 0    # MultiMedia1_Playback
    SAMPLE_RATE = 16000
    BITS = 16
    CHANNELS = 1

    @staticmethod
    def record_chunk(output_wav: str, duration_sec: int = 3):
        """Records an audio chunk using tinycap on device 1."""
        cmd = [
            "tinycap", output_wav,
            "-D", str(AudioHardware.CARD),
            "-d", str(AudioHardware.CAPTURE_DEVICE),
            "-r", str(AudioHardware.SAMPLE_RATE),
            "-b", str(AudioHardware.BITS),
            "-c", str(AudioHardware.CHANNELS),
            "-t", str(duration_sec)
        ]
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def play_wav(input_wav: str):
        """Plays a WAV file through the internal speaker."""
        cmd = [
            "tinyctlplay", input_wav,
            "-D", str(AudioHardware.CARD),
            "-d", str(AudioHardware.PLAYBACK_DEVICE),
            "-a", "100",
            "-m", "100"
        ]
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
