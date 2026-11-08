"""
Unit Test for Healthcheck probe (MUS-10).
"""
import unittest
from unittest.mock import patch
from core_server.healthcheck import check_subsystems


class TestHealthcheckProbe(unittest.TestCase):

    def test_healthcheck_returns_true_when_healthy(self):
        """Verifies check_subsystems passes with mocked or local environment."""
        with patch("socket.socket.connect_ex", return_value=0):
            res = check_subsystems()
            self.assertTrue(res)

    def test_healthcheck_handles_unreachable_dot_gracefully(self):
        """Verifies check_subsystems still completes without crashing if Dot is offline."""
        with patch("socket.socket.connect_ex", return_value=111): # Connection refused
            res = check_subsystems()
            # Non-fatal warning logged, function returns True for healthy core
            self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
