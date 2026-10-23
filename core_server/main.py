"""
TAD Core - Main Voice Assistant Orchestrator.
Full-duplex continuous voice assistant loop for Amazon Echo Dot 2G.
"""
import sys
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
        
        while self.running:
            # Read chunk from TCP socket (27 bytes per 9-channel frame)
            # Read 27 * 160 = 4320 bytes = 10ms of audio
            chunk = mic_sock.recv(4320)
            if not chunk:
                logger.warning("Stream socket closed by device.")
                break

            # 1. Unpack to 16kHz mono S16_LE
            samples_16bit = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples_16bit) == 0:
                continue

            buffer_mono.extend(samples_16bit.tobytes())

            # 2. Check for Wake Word every ~80ms (1280 samples = 2560 bytes)
            if len(buffer_mono) >= 2560:
                window_samples = np.frombuffer(buffer_mono[-2560:], dtype=np.int16)
                if self.processor.process_wake_word(window_samples):
                    logger.info(">>> WAKE WORD TRIGGERED! Transitioning to LISTENING mode.")
                    await self.handle_voice_query(mic_sock)
                    # Reset buffer after query handling
                    buffer_mono.clear()
                    self.bridge.set_led("solid_green", brightness=50)

                # Keep buffer capped
                if len(buffer_mono) > 16000 * 2: # keep last 1 second
                    del buffer_mono[:-2560]

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

        # 4. Generate AI LLM Response
        reply_text = self.brain.generate_response(text)
        logger.info("Assistant reply: '%s'", reply_text)

        # 5. Synthesize TTS Audio
        wav_bytes = await self.brain.synthesize_speech(reply_text)
        if not wav_bytes:
            logger.error("Failed to synthesize TTS audio.")
            return

        # 6. Set LED to Speaking (Turbo pulse) & Play Audio on Echo Dot
        self.bridge.set_led("zzz_turbo-boost", brightness=90)
        self.bridge.play_audio(wav_bytes)

def main():
    assistant = TadAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        logger.info("TAD Assistant terminated by user.")

if __name__ == "__main__":
    main()
