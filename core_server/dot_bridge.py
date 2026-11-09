"""
Dot Bridge Module for SovereignDot.
Provides abstract audio hardware bridge:
- DotBridge: TCP socket communication with tad_dotd on Amazon Echo Dot 2G (ports 9000-9002).
- LocalAudioBridge: Local PC mic & speaker emulation using system audio (aplay/pw-play/afplay/sounddevice).
"""
import os
import sys
import shutil
import asyncio
import socket
import logging
import subprocess
from pathlib import Path
from typing import Optional

from core_server import config

logger = logging.getLogger("dot_bridge")


class DotBridge:
    """Hardware bridge communicating with Amazon Echo Dot 2G over local network."""
    def __init__(self, host: str = config.DOT_HOST):
        self.host = host
        self.mic_port = config.DOT_MIC_PORT    # 9000 — raw mic stream
        self.ctrl_port = config.DOT_PLAY_PORT  # 9001 — control + playback

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._cmd_lock = asyncio.Lock()
        self._response_event = asyncio.Event()
        self._response_line = ""
        self._play_done = asyncio.Event()
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def connect(self):
        """Opens persistent async TCP connection to tad_dotd control port."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.ctrl_port), timeout=5.0
            )
            self._play_done.clear()
            self._reader_task = asyncio.create_task(
                self._read_loop(), name="ctrl_reader"
            )
            logger.info("Connected to tad_dotd control port %d", self.ctrl_port)
        except Exception as e:
            logger.warning("Could not connect to control port %d: %s", self.ctrl_port, e)
            self._reader = self._writer = None

    async def _ensure_connected(self):
        if self._writer is None or self._writer.is_closing():
            logger.info("Control socket not connected, reconnecting...")
            await self.connect()

    async def _read_loop(self):
        """Reads lines from control socket and routes them to the right consumer."""
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                decoded = line.decode(errors="replace").strip()
                logger.debug("CTRL ← %s", decoded)

                if decoded.startswith("EVT "):
                    if decoded == "EVT PLAY_DONE":
                        self._play_done.set()
                    await self.event_queue.put(decoded)
                else:
                    self._response_line = decoded
                    self._response_event.set()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Control reader ended: %s", e)
        finally:
            self._writer = None
            self._reader = None
            await self.event_queue.put("EVT DISCONNECTED")

    async def _send_cmd(self, data: bytes) -> str:
        """Sends raw bytes and waits for the daemon's response line."""
        await self._ensure_connected()
        if self._writer is None:
            return "ERR NOT_CONNECTED"
        async with self._cmd_lock:
            self._response_event.clear()
            self._response_line = ""
            try:
                self._writer.write(data)
                await self._writer.drain()
                await asyncio.wait_for(self._response_event.wait(), timeout=5.0)
                return self._response_line
            except asyncio.TimeoutError:
                logger.warning("Command response timeout")
                return "ERR TIMEOUT"
            except Exception as e:
                logger.warning("Command send failed: %s", e)
                self._writer = None
                return "ERR SEND_FAILED"

    async def set_led(self, pattern: str, brightness: int = 80):
        """Sets the LED ring animation via tad_dotd TCP protocol."""
        logger.info("LED %s brightness=%d", pattern, brightness)
        await self._send_cmd(f"LED {pattern} {brightness}\n".encode())

    async def stop_audio(self):
        """Stops ongoing playback immediately and mutes amplifier."""
        resp = await self._send_cmd(b"STOP\n")
        self._play_done.set()
        logger.info("STOP playback requested → %s", resp)

    async def play_audio(self, wav_bytes: bytes):
        """Streams WAV bytes to tad_dotd and waits for EVT PLAY_DONE."""
        if not wav_bytes:
            return
        self._play_done.clear()
        header = f"PLAY {len(wav_bytes)}\n".encode()
        resp = await self._send_cmd(header + wav_bytes)
        logger.info("PLAY %d bytes → %s", len(wav_bytes), resp)
        if resp.startswith("OK PLAY_STARTED"):
            try:
                await asyncio.wait_for(self._play_done.wait(), timeout=30.0)
                logger.info("Playback finished (EVT PLAY_DONE)")
            except asyncio.TimeoutError:
                logger.warning("PLAY_DONE not received within 30s")

    def open_mic_stream(self) -> socket.socket:
        """Opens a blocking TCP socket to the raw 9-channel mic stream (port 9000)."""
        logger.info("Connecting to mic stream at %s:%d...", self.host, self.mic_port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((self.host, self.mic_port))
        s.settimeout(None)
        logger.info("Mic stream connected.")
        return s


class LocalAudioBridge:
    """
    Local PC Emulator Bridge for SovereignDot.
    Allows testing the entire voice assistant on any Linux/Mac/Windows machine
    without needing an Amazon Echo Dot hardware unit.
    """
    def __init__(self):
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._current_player: Optional[subprocess.Popen] = None
        self._server_sock: Optional[socket.socket] = None
        self._player_bin = self._find_player()
        self._recorder_bin = self._find_recorder()
        logger.info(
            "LocalAudioBridge initialized (Player: %s, Recorder: %s)",
            self._player_bin or "None/Dummy",
            self._recorder_bin or "None",
        )

    def _find_player(self) -> Optional[str]:
        for bin_name in ["pw-play", "paplay", "aplay", "afplay"]:
            found = shutil.which(bin_name)
            if found:
                return found
        return None

    def _find_recorder(self) -> Optional[str]:
        for bin_name in ["arecord", "parec", "ffmpeg"]:
            found = shutil.which(bin_name)
            if found:
                return found
        return None

    async def connect(self):
        logger.info("LocalAudioBridge connected to local host audio system.")

    async def set_led(self, pattern: str, brightness: int = 80):
        # Emulate LED ring in terminal with ANSI colors
        color_code = "\033[92m" if "green" in pattern else "\033[96m" if "cyan" in pattern else "\033[94m"
        logger.info("%s[💡 LED Ring Simulation: %s (Brightness: %d%%)]\033[0m", color_code, pattern, brightness)

    async def stop_audio(self):
        if self._current_player and self._current_player.poll() is None:
            try:
                self._current_player.terminate()
                logger.info("Local audio playback terminated.")
            except Exception as e:
                logger.warning("Error stopping local playback: %s", e)
        self._current_player = None

    async def play_audio(self, wav_bytes: bytes):
        if not wav_bytes:
            return

        await self.stop_audio()

        if self._player_bin:
            try:
                logger.info("Playing %d bytes audio via local %s...", len(wav_bytes), self._player_bin)
                loop = asyncio.get_running_loop()

                def _play():
                    proc = subprocess.Popen(
                        [self._player_bin, "-"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._current_player = proc
                    proc.communicate(input=wav_bytes)

                await loop.run_in_executor(None, _play)
                logger.info("Local audio playback completed.")
            except Exception as e:
                logger.error("Local audio playback failed: %s", e)
        else:
            logger.info("[Dummy Playback] %d bytes WAV generated (No system player found).", len(wav_bytes))

    def open_mic_stream(self) -> socket.socket:
        """
        Emulates mic stream using an in-memory loopback socket kept alive.
        """
        logger.info("Opening local mic stream emulator...")
        self._server_sock, client_sock = socket.socketpair()
        return client_sock

    async def record_local_mic(self, duration_sec: float = 4.0) -> bytes:
        """Records 16kHz 16-bit mono PCM from the local PC microphone."""
        if not self._recorder_bin:
            logger.warning("No local audio recorder binary (arecord/parec/ffmpeg) found on system.")
            return b""

        bin_name = Path(self._recorder_bin).name
        if bin_name == "arecord":
            cmd = [self._recorder_bin, "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-d", str(int(duration_sec))]
        elif bin_name == "parec":
            cmd = ["timeout", str(duration_sec), self._recorder_bin, "--format=s16le", "--rate=16000", "--channels=1", "--raw"]
        else:
            cmd = [self._recorder_bin, "-loglevel", "quiet", "-f", "alsa", "-i", "default", "-t", str(duration_sec), "-f", "s16le", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-"]

        logger.info("🎙️ Recording from local PC microphone for %.1fs...", duration_sec)
        loop = asyncio.get_running_loop()

        def _rec() -> bytes:
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=duration_sec + 2.0)
                return res.stdout
            except Exception as e:
                logger.error("Local microphone recording error: %s", e)
                return b""

        return await loop.run_in_executor(None, _rec)


def create_audio_bridge() -> DotBridge | LocalAudioBridge:
    """Factory creating the appropriate audio bridge according to AUDIO_INPUT_MODE configuration."""
    mode = getattr(config, "AUDIO_INPUT_MODE", "echo_dot").lower()
    if mode == "local":
        logger.info("Using LocalAudioBridge (PC Mode).")
        return LocalAudioBridge()
    logger.info("Using DotBridge for Amazon Echo Dot 2G (Host: %s).", config.DOT_HOST)
    return DotBridge(host=config.DOT_HOST)
