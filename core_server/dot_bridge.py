"""
Dot Bridge Module.
Handles TCP socket communication with the tad_dotd daemon on Echo Dot 2G.
Uses the native control protocol on port 9001 (PLAY, LED, STOP) instead of ADB.
"""
import asyncio
import socket
import logging
from core_server import config

logger = logging.getLogger("dot_bridge")


class DotBridge:
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

    # ── Connection management ────────────────────────────────────────────────

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
                    # Response to a sent command (OK … / ERR …)
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

    # ── Command helpers ──────────────────────────────────────────────────────

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

    # ── Public API ───────────────────────────────────────────────────────────

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

    async def stop_audio(self):
        """Immediately stops current playback."""
        await self._send_cmd(b"STOP\n")
        self._play_done.set()  # Unblock any pending play_audio

    def open_mic_stream(self) -> socket.socket:
        """Opens a blocking TCP socket to the raw 9-channel mic stream (port 9000)."""
        logger.info("Connecting to mic stream at %s:%d...", self.host, self.mic_port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((self.host, self.mic_port))
        s.settimeout(None)
        logger.info("Mic stream connected.")
        return s
