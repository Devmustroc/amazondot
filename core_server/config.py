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
VAD_SILENCE_DURATION_SEC = float(os.getenv("VAD_SILENCE_DURATION_SEC", "0.6")) # Fast 600ms silence detection
MAX_RECORDING_SEC = int(os.getenv("MAX_RECORDING_SEC", "10"))

# Assistant Identity & Family RBAC Configuration
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Régis")
FAMILY_ADMIN_NAME = os.getenv("FAMILY_ADMIN_NAME", "El Mustapha")
FAMILY_CHILD_NAME = os.getenv("FAMILY_CHILD_NAME", "Ismail")
AUDIO_INPUT_MODE = os.getenv("AUDIO_INPUT_MODE", "echo_dot") # "echo_dot" or "local"
WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "régis,regis,regisse,alexa").split(",")]
WAKE_WORD_MODEL = os.getenv("WAKE_WORD_MODEL", "alexa") # openWakeWord model for fast fallback
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.2"))

# Speech-to-Text & Text-to-Speech
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1")) # 1 = fast greedy decoding
TTS_VOICE = os.getenv("TTS_VOICE", "fr-FR-VivienneMultilingualNeural")
TTS_CACHE_ENABLED = os.getenv("TTS_CACHE_ENABLED", "true").lower() == "true"

# Offline Resilience & Fallback (Piper ONNX)
PIPER_ENABLED = os.getenv("PIPER_ENABLED", "true").lower() == "true"
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", str(BASE_DIR / "core_server" / "models" / "piper" / "fr_FR-siwis-medium.onnx"))
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", str(BASE_DIR / "core_server" / "models" / "piper" / "fr_FR-siwis-medium.onnx.json"))
CIRCUIT_BREAKER_MAX_FAILURES = int(os.getenv("CIRCUIT_BREAKER_MAX_FAILURES", "2"))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SEC = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SEC", "15.0"))
CIRCUIT_BREAKER_TTS_TIMEOUT_SEC = float(os.getenv("CIRCUIT_BREAKER_TTS_TIMEOUT_SEC", "1.2"))

# Homelab & Proxmox SRE Configuration
PROXMOX_HOST = os.getenv("PROXMOX_HOST", "192.168.1.200")
PROXMOX_SSH_USER = os.getenv("PROXMOX_SSH_USER", "root")
PROXMOX_SSH_KEY = os.getenv("PROXMOX_SSH_KEY", str(Path.home() / ".ssh" / "id_ed25519"))

# LLM & Brain (OpenRouter)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3.8-flash")
OPENROUTER_TTS_MODEL = os.getenv("OPENROUTER_TTS_MODEL", "google/gemini-3.8-flash-lite-tts")
OPENROUTER_TTS_VOICE = os.getenv("OPENROUTER_TTS_VOICE", "Puck")

# System Prompt for SovereignDot
DEFAULT_SYSTEM_PROMPT = f"""Tu t'appelles {ASSISTANT_NAME}. Tu es l'assistant vocal intelligent, souverain, chaleureux et concis pour la maison.
Réponds toujours en français métropolitain standard (de France), sans aucun accent régional ni expression québécoise, de façon calme, douce, précise et brève (1 à 2 phrases maximum), car tes réponses sont prononcées à voix haute."""
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
# Continuous Conversation (Follow-up Mode)
FOLLOWUP_TIMEOUT_SEC = float(os.getenv("FOLLOWUP_TIMEOUT_SEC", "10.0"))
CLOSING_WORDS = ["merci", "c'est bon", "stop", "au revoir", "bonne journée", "bonne nuit", "à plus", "rien", "c'est tout", "non c'est bon"]
