"""
Unit and Integration Tests for MUS-8:
Resilience, Circuit-Breaker, and Offline Piper ONNX TTS Fallback.
"""
import time
import asyncio
import unittest
from unittest.mock import patch, AsyncMock
import soundfile as sf
import io

from core_server.resilience import CircuitBreaker, CircuitState, PiperEngine
from core_server.brain import Brain
from core_server.mcp_client import McpManager
from core_server import config


class TestResilienceFallback(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.breaker = CircuitBreaker(
            name="TestBreaker",
            max_failures=2,
            recovery_timeout_sec=0.2, # short timeout for testing
        )
        self.piper = PiperEngine.get_instance()

    def test_circuit_breaker_transitions(self):
        """Tests CLOSED -> OPEN -> HALF_OPEN -> CLOSED state lifecycle."""
        # Initial state is CLOSED
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)
        self.assertTrue(self.breaker.is_cloud_available())

        # First failure: still CLOSED (max_failures=2)
        self.breaker.record_failure(RuntimeError("Cloud error 1"))
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)
        self.assertTrue(self.breaker.is_cloud_available())

        # Second failure: switches to OPEN
        self.breaker.record_failure(RuntimeError("Cloud error 2"))
        self.assertEqual(self.breaker.state, CircuitState.OPEN)
        self.assertFalse(self.breaker.is_cloud_available())

        # Wait for recovery timeout (0.2s)
        time.sleep(0.25)
        self.assertEqual(self.breaker.state, CircuitState.HALF_OPEN)
        self.assertTrue(self.breaker.is_cloud_available())

        # Successful request closes the circuit
        self.breaker.record_success()
        self.assertEqual(self.breaker.state, CircuitState.CLOSED)
        self.assertTrue(self.breaker.is_cloud_available())

    def test_piper_engine_synthesis(self):
        """Verifies Piper ONNX produces valid 48kHz stereo WAV audio."""
        self.piper.initialize_sync()
        self.assertTrue(self.piper.is_ready)

        t0 = time.perf_counter()
        wav_bytes = self.piper.synthesize_to_dot_wav("Test de synthèse vocale hors ligne Régis.")
        duration = time.perf_counter() - t0

        self.assertGreater(len(wav_bytes), 1000)
        # Latency should be well under 1000ms for warm inference
        self.assertLess(duration, 1.0)

        # Validate WAV structure (48kHz, 2 channels, PCM_16)
        data, sr = sf.read(io.BytesIO(wav_bytes))
        self.assertEqual(sr, 48000)
        self.assertEqual(len(data.shape), 2)
        self.assertEqual(data.shape[1], 2)

    async def test_brain_tts_fallback_on_cloud_failure(self):
        """Verifies that when Edge-TTS fails/times out, Brain falls back to Piper seamlessly."""
        brain = Brain()
        # Reset breaker
        brain.circuit_breaker.force_state(CircuitState.CLOSED)
        unique_phrase = f"Alerte panne réseau {time.time()} test de repli automatique."

        # Mock edge_tts.Communicate to simulate network timeout / failure
        with patch("edge_tts.Communicate", side_effect=RuntimeError("Connection refused by Microsoft")):
            t0 = time.perf_counter()
            wav = await brain.synthesize_speech(unique_phrase)
            dt = time.perf_counter() - t0

            # Fallback should deliver valid audio without raising an exception
            self.assertGreater(len(wav), 1000)
            self.assertLess(dt, 1.5)

            # Failure should be recorded in circuit breaker
            status = brain.circuit_breaker.get_status()
            self.assertGreaterEqual(status["failure_count"], 1)

    async def test_brain_bypass_when_circuit_open(self):
        """Verifies that when Circuit Breaker is OPEN, cloud TTS is bypassed entirely."""
        brain = Brain()
        brain.circuit_breaker.force_state(CircuitState.OPEN)
        unique_phrase = f"Synthèse directe en circuit ouvert {time.time()}."

        with patch("edge_tts.Communicate") as mock_comm:
            wav = await brain.synthesize_speech(unique_phrase)
            # Edge-TTS should NOT be called at all
            mock_comm.assert_not_called()
            self.assertGreater(len(wav), 1000)

    async def test_network_resilience_voice_intent(self):
        """Verifies voice query for network status returns circuit-breaker metrics."""
        brain = Brain()
        brain.circuit_breaker.force_state(CircuitState.CLOSED)

        responses = []
        async for s in brain.generate_response_stream("Régis, quel est l'état du réseau ?"):
            responses.append(s)

        full_reply = " ".join(responses)
        self.assertIn("circuit réseau est CLOSED", full_reply)
        self.assertIn("connecté au cloud", full_reply)

    async def test_mcp_resilience_tool(self):
        """Verifies native MCP tool 'homelab_get_resilience_status' returns breaker stats."""
        mcp = McpManager()
        res = await mcp.call_tool("homelab_get_resilience_status", {})
        self.assertIn("État du Circuit-Breaker:", res)
        self.assertIn("failure_count", res)


if __name__ == "__main__":
    unittest.main()
