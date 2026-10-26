"""
TAD Core Configuration.
Manages network endpoints, audio format settings, models, and API keys.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Echo Dot Network Configuration
DOT_HOST = os.getenv("DOT_HOST", "192.168.1.23")
DOT_MIC_PORT = int(os.getenv("DOT_MIC_PORT", "9000"))
DOT_PLAY_PORT = int(os.getenv("DOT_PLAY_PORT", "9001"))
DOT_CTRL_PORT = int(os.getenv("DOT_CTRL_PORT", "9002"))

# Audio Hardware Specification (Reverse-Engineered Echo Dot 2G)
SAMPLE_RATE = 16000
CHANNELS_RAW = 9
BYTES_PER_SAMPLE_RAW = 3     # S24_3LE (24-bit packed)
FRAME_BYTES_RAW = CHANNELS_RAW * BYTES_PER_SAMPLE_RAW  # 27 bytes per frame
CENTER_MIC_OFFSET = 18       # Channel 6 in S24_3LE starts at byte 18

# Processing & VAD
VAD_SILENCE_THRESHOLD = float(os.getenv("VAD_SILENCE_THRESHOLD", "12.0")) # RMS
VAD_SILENCE_DURATION_SEC = float(os.getenv("VAD_SILENCE_DURATION_SEC", "1.2"))
MAX_RECORDING_SEC = int(os.getenv("MAX_RECORDING_SEC", "10"))

# Assistant Identity & Wake Word
ASSISTANT_NAME = "Régis"
WAKE_WORDS = ["régis", "regis", "regisse", "alexa"]
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "alexa") # openWakeWord model for fast fallback
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.2"))

# Speech-to-Text & Text-to-Speech
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
TTS_VOICE = os.getenv("TTS_VOICE", "fr-FR-DeniseNeural")

# LLM & Brain (OpenRouter)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.8-flash")
OPENROUTER_TTS_MODEL = os.getenv("OPENROUTER_TTS_MODEL", "google/gemini-3.8-flash-lite-tts")
OPENROUTER_TTS_VOICE = os.getenv("OPENROUTER_TTS_VOICE", "Puck")

# System Prompt for TAD
SYSTEM_PROMPT = """Tu t'appelles Régis. Tu es l'assistant vocal intelligent, chaleureux et concis pour la famille de El Mustapha.
Réponds toujours en français de façon naturelle, précise et brève (1 à 3 phrases maximum), car tes réponses sont prononcées à voix haute."""
# Continuous Conversation (Follow-up Mode)
FOLLOWUP_TIMEOUT_SEC = float(os.getenv("FOLLOWUP_TIMEOUT_SEC", "10.0"))
CLOSING_WORDS = ["merci", "c'est bon", "stop", "au revoir", "bonne journée", "bonne nuit", "à plus", "rien", "c'est tout", "non c'est bon"]
