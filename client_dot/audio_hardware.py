"""
Audio hardware interface for Amazon Echo Dot 2nd Gen (MediaTek MT8163).
Reverse-engineered parameters:
- Capture Device: Card 0, Device 24 (amzn_mt_spi / TLV320AIC3101, 9ch, 24-bit S24_3LE, 16000Hz)
- Playback Device: Card 0, Device 0 (tinyctlplay, 16000Hz, 16-bit)
- LED Controller: /system/bin/ledctrl
"""
import subprocess
import logging

logger = logging.getLogger("audio_hardware")

class AudioHardware:
    CARD = 0
    CAPTURE_DEVICE = 24    # TLV320AIC3101 SPI 9-channel Mic Array
    PLAYBACK_DEVICE = 0    # MultiMedia1_Playback
    SAMPLE_RATE = 16000
    BITS = 24
    CHANNELS = 9
    PERIOD_SIZE = 1024
    PERIOD_COUNT = 2

    @staticmethod
    def record_chunk(output_wav: str, duration_sec: int = 3):
        """Records an audio chunk using tinycap on hardware device 24."""
        cmd = [
            "tinycap", output_wav,
            "-D", str(AudioHardware.CARD),
            "-d", str(AudioHardware.CAPTURE_DEVICE),
            "-r", str(AudioHardware.SAMPLE_RATE),
            "-b", str(AudioHardware.BITS),
            "-c", str(AudioHardware.CHANNELS),
            "-p", str(AudioHardware.PERIOD_SIZE),
            "-n", str(AudioHardware.PERIOD_COUNT),
            "-f",
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

