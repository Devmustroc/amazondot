"""
Dot Bridge Module.
Handles socket communication with the Echo Dot 2G hardware daemon (Microphones, Speaker, LEDs).
"""
import socket
import logging
import subprocess
import time
from core_server import config

logger = logging.getLogger("dot_bridge")

class DotBridge:
    def __init__(self, host: str = config.DOT_HOST):
        self.host = host
        self.mic_port = config.DOT_MIC_PORT
        self.play_port = config.DOT_PLAY_PORT
        self.ctrl_port = config.DOT_CTRL_PORT

    def set_led(self, pattern: str, brightness: int = 80):
        """Sets the LED ring animation pattern via ADB or control port."""
        logger.info("Setting Dot LED to: %s (brightness=%d)", pattern, brightness)
        try:
            # We can invoke ledctrl directly via adb shell for immediate guaranteed response
            subprocess.run(
                ["adb", "-s", f"{self.host}:5555", "shell", f"su -c 'ledctrl -c && ledctrl -s {pattern} -b {brightness}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception as e:
            logger.error("Failed to set LED via adb: %s", e)

    def play_audio(self, wav_bytes: bytes):
        """Pushes WAV audio to the Dot and plays it through the internal speaker."""
        if not wav_bytes:
            return

        logger.info("Playing %d bytes of audio through Echo Dot speaker...", len(wav_bytes))
        try:
            local_wav = "/tmp/tad_speech.wav"
            with open(local_wav, "wb") as f:
                f.write(wav_bytes)

            remote_wav = "/data/local/tmp/tad_speech.wav"
            subprocess.run(
                ["adb", "-s", f"{self.host}:5555", "push", local_wav, remote_wav],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            cmd = f"su -c 'tinyplay {remote_wav} -D 0 -d 0 2>/dev/null || tinyplay {remote_wav} -D 0 -d 23'"
            subprocess.run(
                ["adb", "-s", f"{self.host}:5555", "shell", cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True
            )
            logger.info("Playback completed successfully.")
        except Exception as e:
            logger.error("Failed to play audio on Dot: %s", e)

    def open_mic_stream(self) -> socket.socket:
        """Establishes TCP connection to the microphone stream on the Echo Dot."""
        logger.info("Connecting to Echo Dot mic stream at %s:%d...", self.host, self.mic_port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((self.host, self.mic_port))
        s.settimeout(None) # set to blocking
        logger.info("Connected to Echo Dot mic stream successfully.")
        return s
