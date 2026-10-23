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
from core_server.dot_bridge import DotBridge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("tad_core")

class TadAssistant:
    def __init__(self):
        logger.info("Initializing TAD Assistant...")
        self.bridge = DotBridge(host=config.DOT_HOST)
        self.processor = AudioProcessor(wake_model_name=config.WAKE_WORD_MODEL)
        self.brain = Brain()
        self.running = False

    async def run(self):
        self.running = True
        logger.info("Starting TAD Assistant loop connecting to Echo Dot at %s...", config.DOT_HOST)
        
        # Ensure LED is green on startup
        self.bridge.set_led("solid_green", brightness=50)

        while self.running:
            try:
                mic_socket = self.bridge.open_mic_stream()
                logger.info("Microphone stream connected. Listening for wake word ('%s')...", config.WAKE_WORD_MODEL)
                await self.interaction_loop(mic_socket)
            except Exception as e:
                logger.error("Error in mic connection or stream: %s. Reconnecting in 3s...", e)
                await asyncio.sleep(3)

    async def interaction_loop(self, mic_sock):
        buffer_mono = bytearray()
        speech_candidate = bytearray()
        silence_frames = 0
        
        while self.running:
            # Read chunk from TCP socket (27 bytes per 9-channel frame)
            # Read 27 * 160 = 4320 bytes = 10ms of audio
            chunk = mic_sock.recv(4320)
            if not chunk:
                logger.warning("Stream socket closed by device.")
                break

            # 1. Unpack to 16kHz mono S16_LE (with 150Hz highpass filter)
            samples_16bit = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples_16bit) == 0:
                continue

            buffer_mono.extend(samples_16bit.tobytes())

            # 2. Check for Wake Word on successive 1280-sample chunks (80ms)
            while len(buffer_mono) >= 2560:
                chunk_1280 = np.frombuffer(buffer_mono[:2560], dtype=np.int16)
                del buffer_mono[:2560]

                # A. Fast ONNX model check (Alexa fallback)
                if self.processor.process_wake_word(chunk_1280):
                    logger.info(">>> WAKE WORD TRIGGERED (Alexa)! Transitioning to LISTENING mode.")
                    await self.handle_voice_query(mic_sock)
                    buffer_mono.clear()
                    speech_candidate.clear()
                    self.bridge.set_led("solid_green", brightness=50)
                    break

                # B. Neural VAD + French Keyword Spotter (Régis)
                has_speech = self.processor.is_speech(chunk_1280)
                if has_speech:
                    speech_candidate.extend(chunk_1280.tobytes())
                    silence_frames = 0
                elif len(speech_candidate) > 0:
                    silence_frames += 1
                    speech_candidate.extend(chunk_1280.tobytes())

                # If speech finished (approx 1s silence detected) or maximum duration reached (~3.5s)
                if len(speech_candidate) > 0 and (silence_frames >= 12 or len(speech_candidate) >= 56000):
                    cand_bytes = bytes(speech_candidate)
                    speech_candidate.clear()
                    silence_frames = 0
                    try:
                        self.processor.vad.reset_states()
                    except Exception:
                        pass

                    # Only transcribe if candidate is at least 500ms (16000 bytes)
                    if len(cand_bytes) >= 16000:
                        text = self.brain.transcribe(cand_bytes)
                        text_lower = text.lower()
                        logger.info("Candidate speech heard: '%s'", text)
                        
                        wake_terms = ["régis", "regis", "régi", "regisse", "alexa"]
                        matched = any(w in text_lower for w in wake_terms)

                        if matched:
                            logger.info(">>> WAKE WORD DETECTED: '%s'! Full phrase: '%s'", config.ASSISTANT_NAME, text)
                            query = re.sub(r'^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*', '', text, flags=re.I).strip()
                            if len(query) >= 3:
                                # Direct command in same sentence (e.g. "Régis, quelle heure est-il ?")
                                await self.process_and_reply(query)
                            else:
                                # Wake word alone ("Régis") -> enter listening mode
                                await self.handle_voice_query(mic_sock)

                            buffer_mono.clear()
                            self.bridge.set_led("solid_green", brightness=50)
                            break

    async def process_and_reply(self, text: str):
        """Processes transcribed user prompt directly and speaks reply."""
        self.bridge.set_led("solid_cyan", brightness=80)
        logger.info("Processing direct prompt: '%s'", text)
        reply_text = self.brain.generate_response(text)
        logger.info("Assistant reply: '%s'", reply_text)
        wav_bytes = await self.brain.synthesize_speech(reply_text)
        if wav_bytes:
            self.bridge.set_led("zzz_turbo-boost", brightness=90)
            self.bridge.play_audio(wav_bytes)

    async def handle_voice_query(self, mic_sock):
        """Records voice query until silence is detected, processes it, and replies."""
        # 1. Set LED to Listening (Blue)
        self.bridge.set_led("solid_blue", brightness=90)

        logger.info("Listening for speech...")
        speech_pcm = bytearray()
        silence_start = None
        speech_started = False
        start_time = time.time()

        while time.time() - start_time < config.MAX_RECORDING_SEC:
            chunk = mic_sock.recv(4320)
            if not chunk:
                break

            samples = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples) == 0:
                continue

            speech_pcm.extend(samples.tobytes())
            rms = self.processor.calculate_rms(samples)

            # Simple energy VAD
            if rms > config.VAD_SILENCE_THRESHOLD:
                speech_started = True
                silence_start = None
            else:
                if speech_started:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= config.VAD_SILENCE_DURATION_SEC:
                        logger.info("End of speech detected (silence duration reached).")
                        break

            await asyncio.sleep(0)

        if len(speech_pcm) == 0:
            logger.warning("No audio recorded.")
            return

        # 2. Set LED to Thinking (Cyan)
        self.bridge.set_led("solid_cyan", brightness=80)
        logger.info("Transcribing %d bytes of speech...", len(speech_pcm))

        # 3. Transcribe via Whisper
        text = self.brain.transcribe(bytes(speech_pcm))
        logger.info("User prompt: '%s'", text)

        if not text.strip():
            logger.info("No speech detected in transcription.")
            return

        # 4. Generate AI LLM Response & Synthesize Audio
        await self.process_and_reply(text)

def main():
    assistant = TadAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        logger.info("TAD Assistant terminated by user.")

if __name__ == "__main__":
    main()
