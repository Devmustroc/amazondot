"""
Audio hardware interface for Amazon Echo Dot 2nd Gen (MediaTek MT8163 / CX20810 7-mic array).
Extracted from Echo Dot reverse-engineering:
- Hardware card: 0
- Mic array capture device: 24 (tinycap -D 0 -d 24 -r 16000 -b 24 -c 9)
- Playback device: card 0, device 0 (tinyplay)
- Conflicting Amazon daemon to stop: 'mixer'
"""
import subprocess
import logging

logger = logging.getLogger("audio_hardware")

class AudioHardware:
    CARD = 0
    CAPTURE_DEVICE = 24
    PLAYBACK_DEVICE = 0
    SAMPLE_RATE = 16000
    BITS = 24
    CHANNELS = 9

    @staticmethod
    def kill_amazon_mixer():
        """Kills proprietary Amazon mixer process holding the audio devices."""
        try:
            subprocess.run(["killall", "mixer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Amazon audio mixer process killed.")
        except Exception as e:
            logger.warning("Error killing mixer process: %s", e)

    @staticmethod
    def start_capture_process(output_path: str = "-"):
        """
        Launches tinycap to stream audio.
        If output_path is '-', streams to stdout pipe.
        """
        AudioHardware.kill_amazon_mixer()
        cmd = [
            "tinycap", output_path,
            "-D", str(AudioHardware.CARD),
            "-d", str(AudioHardware.CAPTURE_DEVICE),
            "-r", str(AudioHardware.SAMPLE_RATE),
            "-b", str(AudioHardware.BITS),
            "-c", str(AudioHardware.CHANNELS),
            "-p", "512",
            "-n", "5"
        ]
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
