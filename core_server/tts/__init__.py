"""
SovereignDot TTS Subsystem.
"""
from core_server.tts.audio_filter import process_audio_for_echo_dot
from core_server.tts.dual_tts_engine import DualEngineTTS, COMMON_ACK_PHRASES

__all__ = ["process_audio_for_echo_dot", "DualEngineTTS", "COMMON_ACK_PHRASES"]
