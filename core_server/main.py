"""
TAD Core - Main Voice Assistant Orchestrator.
Full-duplex continuous voice assistant loop for Amazon Echo Dot 2G.
"""
import sys
import re
import time
import asyncio
import logging
import numpy as np
from core_server import config
from core_server.audio_processor import AudioProcessor
from core_server.brain import Brain
from core_server.dot_bridge import DotBridge, create_audio_bridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("tad_core")


class TadAssistant:
    def __init__(self):
        logger.info("Initializing SovereignDot Assistant (Mode: %s)...", config.AUDIO_INPUT_MODE)
        self.bridge = create_audio_bridge()
        self.processor = AudioProcessor(wake_model_name=config.WAKE_WORD_MODEL)
        self.brain = Brain()
        self.running = False
        self.last_speech_pcm: Optional[bytes] = None

    async def run(self):
        self.running = True
        logger.info("Starting TAD Assistant connecting to Echo Dot at %s...", config.DOT_HOST)

        await self.brain.initialize()
        await self.bridge.connect()
        await self.bridge.set_led("solid_green", brightness=50)

        while self.running:
            try:
                mic_socket = self.bridge.open_mic_stream()
                logger.info("Mic stream connected. Listening for wake word ('%s')...", config.WAKE_WORD_MODEL)
                await self.interaction_loop(mic_socket)
            except Exception as e:
                logger.error("Mic stream error: %s. Reconnecting in 3s...", e)
                await asyncio.sleep(3)

    # ── Wake-word detection loop ─────────────────────────────────────────────

    async def interaction_loop(self, mic_sock):
        loop = asyncio.get_running_loop()
        buffer_mono = bytearray()
        speech_candidate = bytearray()
        silence_frames = 0

        while self.running:
            # Non-blocking recv: run the blocking socket call in a thread executor
            # so asyncio can handle other tasks (event_queue, timers) between reads.
            chunk = await loop.run_in_executor(None, lambda: mic_sock.recv(4320))
            if not chunk:
                logger.warning("Mic stream closed by device.")
                break

            # Check for hardware button ACTION WAKE (non-blocking)
            try:
                while True:
                    evt = self.bridge.event_queue.get_nowait()
                    if evt == "EVT ACTION WAKE":
                        logger.info(">>> HARDWARE BUTTON WAKE triggered!")
                        buffer_mono.clear()
                        speech_candidate.clear()
                        await self.run_conversation_session(mic_sock)
                        buffer_mono.clear()
                        speech_candidate.clear()
                        await self.bridge.set_led("solid_green", brightness=50)
                    elif evt == "EVT DISCONNECTED":
                        logger.warning("Control socket disconnected — reconnecting...")
                        await asyncio.sleep(1)
                        await self.bridge.connect()
            except asyncio.QueueEmpty:
                pass

            samples_16bit = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples_16bit) == 0:
                continue

            buffer_mono.extend(samples_16bit.tobytes())

            while len(buffer_mono) >= 2560:
                chunk_1280 = np.frombuffer(buffer_mono[:2560], dtype=np.int16)
                del buffer_mono[:2560]

                # A. Fast ONNX wake-word model (Alexa fallback)
                if self.processor.process_wake_word(chunk_1280):
                    logger.info(">>> WAKE WORD TRIGGERED (Alexa)!")
                    buffer_mono.clear()
                    speech_candidate.clear()
                    await self.run_conversation_session(mic_sock)
                    buffer_mono.clear()
                    speech_candidate.clear()
                    await self.bridge.set_led("solid_green", brightness=50)
                    break

                # B. Neural VAD + French keyword spotter (Régis)
                has_speech = self.processor.is_speech(chunk_1280)
                if has_speech:
                    speech_candidate.extend(chunk_1280.tobytes())
                    silence_frames = 0
                elif len(speech_candidate) > 0:
                    silence_frames += 1
                    speech_candidate.extend(chunk_1280.tobytes())

                if len(speech_candidate) > 0 and (silence_frames >= 7 or len(speech_candidate) >= 56000):
                    cand_bytes = bytes(speech_candidate)
                    speech_candidate.clear()
                    silence_frames = 0
                    try:
                        self.processor.vad.reset_states()
                    except Exception:
                        pass

                    if len(cand_bytes) >= 16000:
                        self.last_speech_pcm = cand_bytes
                        text = self.brain.transcribe(cand_bytes)
                        text_lower = text.lower()
                        logger.info("Candidate speech: '%s'", text)

                        if any(w in text_lower for w in ["régis", "regis", "régi", "regisse", "alexa"]):
                            logger.info(">>> WAKE WORD DETECTED: '%s'", text)
                            query = re.sub(
                                r'^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*',
                                '', text, flags=re.I
                            ).strip()
                            buffer_mono.clear()
                            await self.run_conversation_session(
                                mic_sock, initial_text=query if len(query) >= 3 else None
                            )
                            buffer_mono.clear()
                            speech_candidate.clear()
                            break

    # ── Voice recording ──────────────────────────────────────────────────────

    async def record_voice_phrase(self, mic_sock, timeout_sec: float) -> str:
        """Records until speech ends or timeout. Returns transcription or ''."""
        loop = asyncio.get_running_loop()
        speech_pcm = bytearray()
        buf_mono = bytearray()
        silence_start = None
        speech_started = False
        start_time = time.time()

        while self.running:
            if not speech_started and (time.time() - start_time >= timeout_sec):
                logger.info("Follow-up timeout (%.1fs) — returning to standby.", timeout_sec)
                return ""
            if time.time() - start_time >= config.MAX_RECORDING_SEC:
                break

            chunk = await loop.run_in_executor(None, lambda: mic_sock.recv(4320))
            if not chunk:
                break

            samples = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples) == 0:
                continue

            buf_mono.extend(samples.tobytes())
            phrase_ended = False

            while len(buf_mono) >= 2560:
                chunk_1280 = np.frombuffer(buf_mono[:2560], dtype=np.int16)
                del buf_mono[:2560]

                rms = self.processor.calculate_rms(chunk_1280)
                has_voice = self.processor.is_speech(chunk_1280) and rms > 15.0

                if has_voice:
                    speech_started = True
                    silence_start = None
                    speech_pcm.extend(chunk_1280.tobytes())
                elif speech_started:
                    speech_pcm.extend(chunk_1280.tobytes())
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= config.VAD_SILENCE_DURATION_SEC:
                        logger.info("Phrase end detected.")
                        phrase_ended = True
                        break

            if phrase_ended:
                break

        if not speech_started or len(speech_pcm) < 16000:
            return ""

        self.last_speech_pcm = bytes(speech_pcm)
        await self.bridge.set_led("solid_cyan", brightness=80)
        return self.brain.transcribe(bytes(speech_pcm)).strip()

    # ── Conversation session ─────────────────────────────────────────────────

    async def run_conversation_session(self, mic_sock, initial_text: str = None):
        """Multi-turn conversation: no wake word needed for follow-up turns."""
        current_text = initial_text

        if not current_text:
            await self.bridge.set_led("solid_cyan", brightness=90)
            wav_ack = await self.brain.synthesize_speech("Oui ?")
            if wav_ack:
                await self.bridge.play_audio(wav_ack)

        while self.running:
            if not current_text:
                await self.bridge.set_led("solid_blue", brightness=85)
                logger.info("Listening for follow-up (timeout=%.1fs)...", config.FOLLOWUP_TIMEOUT_SEC)
                current_text = await self.record_voice_phrase(mic_sock, timeout_sec=config.FOLLOWUP_TIMEOUT_SEC)

            if not current_text:
                logger.info("No follow-up — closing conversation.")
                break

            cleaned_text = re.sub(
                r'^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*',
                '', current_text, flags=re.I
            ).strip() or current_text

            text_lower = cleaned_text.lower()
            logger.info("User: '%s'", cleaned_text)

            # Closing phrases
            if any(cw in text_lower for cw in config.CLOSING_WORDS) and len(cleaned_text.split()) <= 4:
                if "merci" in text_lower:
                    farewell = "Avec plaisir ! N'hésite pas si tu as besoin d'autre chose."
                elif "bonne nuit" in text_lower:
                    farewell = "Bonne nuit à toute la famille !"
                elif "au revoir" in text_lower or "à plus" in text_lower:
                    farewell = "À très bientôt !"
                else:
                    farewell = "C'est noté, je reste disponible."
                await self.bridge.set_led("solid_cyan", brightness=90)
                wav_bytes = await self.brain.synthesize_speech(farewell)
                if wav_bytes:
                    await self.bridge.play_audio(wav_bytes)
                break

            # Stream response chunks directly to speaker with concurrent TTS
            await self.bridge.set_led("solid_cyan", brightness=80)
            await self.stream_response_to_speaker(cleaned_text, speaker_audio=self.last_speech_pcm)

            current_text = None

        await self.bridge.set_led("solid_green", brightness=50)

    async def stream_response_to_speaker(self, prompt: str, speaker_audio: Optional[bytes] = None):
        """
        Streams sentence chunks from Brain LLM and pipelines them directly to TTS and speaker.
        Synthesizes sentence N+1 in the background while sentence N is actively playing.
        Perceived response latency drops from 4-5s to under 1000ms.
        """
        audio_queue: asyncio.Queue = asyncio.Queue(maxsize=3)
        stop_event = asyncio.Event()

        async def synth_producer():
            try:
                async for sentence in self.brain.generate_response_stream(prompt, speaker_audio=speaker_audio):
                    if stop_event.is_set():
                        break
                    s_clean = sentence.strip()
                    if not s_clean:
                        continue
                    logger.info("Sentence ready for TTS: '%s'", s_clean)
                    wav_chunk = await self.brain.synthesize_speech(s_clean)
                    if wav_chunk and not stop_event.is_set():
                        await audio_queue.put(wav_chunk)
            except Exception as e:
                logger.error("Error in TTS streaming producer: %s", e)
            finally:
                await audio_queue.put(None)

        synth_task = asyncio.create_task(synth_producer())

        try:
            first_chunk = True
            while self.running and not stop_event.is_set():
                # Check for barge-in event from hardware buttons
                try:
                    while True:
                        evt = self.bridge.event_queue.get_nowait()
                        if "BARGE_IN" in evt or evt == "EVT ACTION WAKE":
                            logger.info("Barge-in detected during audio playback!")
                            stop_event.set()
                            await self.bridge.stop_audio()
                            break
                except asyncio.QueueEmpty:
                    pass

                if stop_event.is_set():
                    break

                wav = await audio_queue.get()
                if wav is None:
                    break

                if first_chunk:
                    await self.bridge.set_led("solid_cyan", brightness=90)
                    first_chunk = False

                await self.bridge.play_audio(wav)
        finally:
            stop_event.set()
            await synth_task


def main():
    assistant = TadAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        logger.info("TAD Assistant terminated by user.")


if __name__ == "__main__":
    main()
