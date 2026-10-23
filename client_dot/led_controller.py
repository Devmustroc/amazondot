"""
LED Controller for Echo Dot 2nd Gen (biscuit).
Wraps FireOS native 'ledctrl' utility discovered through REA reverse engineering.
"""
import subprocess
import logging

logger = logging.getLogger("led_controller")

class LedController:
    PATTERNS = {
        "listening": "solid_blue",
        "thinking": "solid_cyan",
        "speaking": "zzz_turbo-boost",
        "error": "solid_red",
        "warning": "solid_orange",
        "success": "solid_green",
        "muted": "mics-off_on",
        "off": "off",
    }

    def __init__(self, ledctrl_bin: str = "ledctrl"):
        self.ledctrl_bin = ledctrl_bin

    def set_pattern(self, pattern_name: str, brightness: int = 100):
        target = self.PATTERNS.get(pattern_name, pattern_name)
        try:
            # Clear previous pattern
            subprocess.run([self.ledctrl_bin, "-c"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Set new pattern
            subprocess.run([self.ledctrl_bin, "-s", target, "-b", str(brightness)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("LED set to %s (pattern=%s)", pattern_name, target)
        except Exception as e:
            logger.error("Failed to set LED pattern: %s", e)

    def clear(self):
        try:
            subprocess.run([self.ledctrl_bin, "-c"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error("Failed to clear LEDs: %s", e)
