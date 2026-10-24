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
        
        # Initialize async brain services (MCP, etc.)
        await self.brain.initialize()

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
                    buffer_mono.clear()
                    speech_candidate.clear()
                    await self.run_conversation_session(mic_sock)
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
                            buffer_mono.clear()
                            
                            # Start multi-turn continuous conversation
                            initial_text = query if len(query) >= 3 else None
                            await self.run_conversation_session(mic_sock, initial_text=initial_text)
                            
                            buffer_mono.clear()
                            speech_candidate.clear()
                            break

    async def record_voice_phrase(self, mic_sock, timeout_sec: float) -> str:
        """
        Listens to microphone stream:
        - Times out if no speech detected within timeout_sec.
        - Once speech starts, records until silence of VAD_SILENCE_DURATION_SEC.
        - Transcribes and returns the user speech string (or empty if timeout/silence).
        """
        speech_pcm = bytearray()
        silence_start = None
        speech_started = False
        start_time = time.time()

        while self.running:
            # Check for initial inactivity timeout before speech starts
            if not speech_started and (time.time() - start_time >= timeout_sec):
                logger.info("Follow-up silence timeout (%.1fs) reached without speech.", timeout_sec)
                return ""

            if time.time() - start_time >= config.MAX_RECORDING_SEC:
                break

            chunk = mic_sock.recv(4320)
            if not chunk:
                break

            samples = self.processor.unpack_raw_to_mono16(chunk)
            if len(samples) == 0:
                continue

            speech_pcm.extend(samples.tobytes())
            rms = self.processor.calculate_rms(samples)

            if rms > config.VAD_SILENCE_THRESHOLD:
                speech_started = True
                silence_start = None
            else:
                if speech_started:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= config.VAD_SILENCE_DURATION_SEC:
                        logger.info("End of phrase detected.")
                        break

            await asyncio.sleep(0)

        if not speech_started or len(speech_pcm) < 8000:
            return ""

        self.bridge.set_led("solid_cyan", brightness=80)
        text = self.brain.transcribe(bytes(speech_pcm))
        return text.strip()

    async def run_conversation_session(self, mic_sock, initial_text: str = None):
        """
        Runs an active multi-turn conversation session.
        Keeps listening for follow-up questions without requiring the wake word 'Régis'
        until a silence timeout is reached or user closes the conversation.
        """
        current_text = initial_text

        while self.running:
            # If we don't have a prompt (follow-up turn), listen for one
            if not current_text:
                self.bridge.set_led("solid_blue", brightness=85)
                logger.info(">> Continuous conversation active. Listening for follow-up (timeout=%.1fs)...",
                            config.FOLLOWUP_TIMEOUT_SEC)
                current_text = await self.record_voice_phrase(mic_sock, timeout_sec=config.FOLLOWUP_TIMEOUT_SEC)

            if not current_text:
                logger.info("No follow-up speech heard. Closing continuous conversation.")
                break

            # Strip optional leading 'Régis' if user still said it by habit
            cleaned_text = re.sub(r'^(dis\s+|salut\s+|hey\s+)?(r[ée]gis|r[ée]gi|regisse|alexa)[,\s\.]*', '', current_text, flags=re.I).strip()
            if not cleaned_text:
                cleaned_text = current_text

            text_lower = cleaned_text.lower()
            logger.info("User prompt in conversation: '%s'", cleaned_text)

            # Check if user wants to close conversation
            closing_detected = any(cw in text_lower for cw in config.CLOSING_WORDS)
            if closing_detected and len(cleaned_text.split()) <= 4:
                logger.info("User closing phrase detected ('%s'). Closing conversation.", cleaned_text)
                if "merci" in text_lower:
                    farewell = "Avec plaisir ! N'hésite pas si tu as besoin d'autre chose."
                elif "bonne nuit" in text_lower:
                    farewell = "Bonne nuit à toute la famille !"
                elif "au revoir" in text_lower or "à plus" in text_lower:
                    farewell = "À très bientôt !"
                else:
                    farewell = "C'est noté, je reste disponible."
                
                self.bridge.set_led("solid_cyan", brightness=90)
                wav_bytes = await self.brain.synthesize_speech(farewell)
                if wav_bytes:
                    self.bridge.play_audio(wav_bytes)
                break

            # Process AI Response
            self.bridge.set_led("solid_cyan", brightness=80)
            reply_text = self.brain.generate_response(cleaned_text)
            logger.info("Assistant reply: '%s'", reply_text)

            wav_bytes = await self.brain.synthesize_speech(reply_text)
            if wav_bytes:
                self.bridge.set_led("solid_cyan", brightness=90)
                self.bridge.play_audio(wav_bytes)

            # Reset current_text to None so next iteration listens for follow-up!
            current_text = None

        # Reset to idle green once conversation ends
        self.bridge.set_led("solid_green", brightness=50)

def main():
    assistant = TadAssistant()
    try:
        asyncio.run(assistant.run())
    except KeyboardInterrupt:
        logger.info("TAD Assistant terminated by user.")

if __name__ == "__main__":
    main()
