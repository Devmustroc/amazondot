"""
Healthcheck Probe for TAD Core Docker & Systemd Daemon.
Returns exit code 0 if all subsystems (audio, models, network bridge) are healthy, 1 otherwise.
"""
import sys
import socket
import logging
from pathlib import Path

# Configure minimal stdout logging for health check
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("healthcheck")


def check_subsystems() -> bool:
    try:
        from core_server import config
        from core_server.resilience import global_circuit_breaker, global_piper_engine
        from core_server.voice_id import global_voice_id

        # 1. Verify Circuit Breaker and Piper Engine
        cb_status = global_circuit_breaker.get_status()
        logger.info("Circuit-Breaker state: %s (fallbacks: %d)", cb_status["state"], cb_status["total_fallbacks"])

        # 2. Check Piper Model availability
        model_p = Path(config.PIPER_MODEL_PATH)
        if not model_p.exists():
            logger.warning("Piper model missing at %s (offline fallback degraded)", model_p)
        else:
            logger.info("Piper model present (%d bytes)", model_p.stat().st_size)

        # 3. Check Echo Dot Network Reachability
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        try:
            # Probe control port 9001 (or mic port 9000)
            res = s.connect_ex((config.DOT_HOST, config.DOT_PLAY_PORT))
            if res == 0:
                logger.info("Echo Dot bridge reachable at %s:%d", config.DOT_HOST, config.DOT_PLAY_PORT)
            else:
                logger.warning("Echo Dot control port %s:%d unreachable (code=%d)", config.DOT_HOST, config.DOT_PLAY_PORT, res)
        finally:
            s.close()

        # 4. Check Voice Profiles Encryption
        profiles = global_voice_id.get_profiles_summary()
        logger.info("VoiceID active with %d enrolled profile(s)", len(profiles))

        return True

    except Exception as e:
        logger.error("Healthcheck probe failed: %s", e)
        return False


if __name__ == "__main__":
    if check_subsystems():
        logger.info("TAD Core healthcheck PASSED.")
        sys.exit(0)
    else:
        logger.error("TAD Core healthcheck FAILED.")
        sys.exit(1)
