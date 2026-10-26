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

    def _get_adb_target(self) -> str:
        """Determines best active ADB device (Wi-Fi or USB)."""
        wifi_target = f"{self.host}:5555"
        try:
            res = subprocess.run(["adb", "devices"], capture_output=True, text=True, check=False)
            lines = [l.strip() for l in res.stdout.splitlines() if "\tdevice" in l]
            devices = [l.split("\t")[0] for l in lines]
            if wifi_target in devices:
                return wifi_target
            if devices:
                return devices[0]
        except Exception:
            pass
        return wifi_target

    def set_led(self, pattern: str, brightness: int = 80):
        """Sets the LED ring animation pattern via ADB or control port."""
        logger.info("Setting Dot LED to: %s (brightness=%d)", pattern, brightness)
        target = self._get_adb_target()
        try:
            subprocess.run(
                ["adb", "-s", target, "shell", f"su -c 'ledctrl -c && ledctrl -s {pattern} -b {brightness}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3
            )
        except Exception as e:
            logger.error("Failed to set LED via adb: %s", e)

    def play_audio(self, wav_bytes: bytes):
        """Pushes WAV audio to the Dot and plays it through the internal speaker."""
        if not wav_bytes:
            return

        logger.info("Playing %d bytes of audio through Echo Dot speaker...", len(wav_bytes))
        target = self._get_adb_target()
        try:
            # Unmute amplifier and configure acoustic profile
            subprocess.run(
                ["adb", "-s", target, "shell", "su -c 'tinymix Speaker_Amp_Switch On; tinymix Audio_Amp_R_Switch On; tinymix \"Right Channel Only\" On; tinymix \"HP Driver Gain Volume\" 6 6'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=3
            )

            local_wav = "tools/tad_speech.wav"
            with open(local_wav, "wb") as f:
                f.write(wav_bytes)

            remote_wav = "/data/local/tmp/tad_speech.wav"
            subprocess.run(
                ["adb", "-s", target, "push", local_wav, remote_wav],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=5
            )
            # Ensure tad_player.jar is present
            subprocess.run(
                ["adb", "-s", target, "push", "tools/tad_player.jar", "/data/local/tmp/tad_player.jar"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5
            )
            # Use TadPlayer DEX which plays via Android MediaPlayer (AudioFlinger / FastMixer)
            play_cmd = f"CLASSPATH=/data/local/tmp/tad_player.jar app_process / com.tad.Player {remote_wav}"
            subprocess.run(
                ["adb", "-s", target, "shell", play_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=15
            )
            logger.info("Playback completed successfully on Dot speaker.")
        except Exception as e:
            logger.error("Failed to play audio on Dot: %s", e)
        finally:
            # Mute speaker amplifier when idle to completely eliminate background hiss/hum
            try:
                subprocess.run(
                    ["adb", "-s", target, "shell", "su -c 'tinymix Speaker_Amp_Switch Off; tinymix Audio_Amp_R_Switch Off'"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=3
                )
            except Exception:
                pass

    def open_mic_stream(self) -> socket.socket:
        """Establishes TCP connection to the microphone stream on the Echo Dot."""
        logger.info("Connecting to Echo Dot mic stream at %s:%d...", self.host, self.mic_port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((self.host, self.mic_port))
        s.settimeout(None) # set to blocking
        logger.info("Connected to Echo Dot mic stream successfully.")
        return s
