"""
Unit and Integration Tests for MUS-9:
VoiceID Biometric Speaker Recognition & Role-Based Access Control (RBAC).
"""
import time
import unittest
import numpy as np
from pathlib import Path
import tempfile
import shutil

from core_server.voice_id import (
    VoiceIDEngine,
    UserRole,
    SpeakerProfile,
    PROTECTED_HOMELAB_ACTIONS,
)
from core_server.brain import Brain
from core_server.mcp_client import McpManager


def generate_synthetic_pcm(frequency_hz: float, duration_sec: float = 1.0, sr: int = 16000) -> bytes:
    """Generates synthetic harmonic audio waveform as 16kHz 16-bit mono PCM."""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    # Fundamental + harmonics
    wave = (
        0.6 * np.sin(2 * np.pi * frequency_hz * t)
        + 0.3 * np.sin(2 * np.pi * 2 * frequency_hz * t)
        + 0.1 * np.sin(2 * np.pi * 3 * frequency_hz * t)
    )
    s16 = np.clip(wave * 30000, -32768, 32767).astype(np.int16)
    return s16.tobytes()


class TestVoiceIDSubsystem(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.engine = VoiceIDEngine(storage_dir=self.temp_dir)
        self.adult_audio = generate_synthetic_pcm(frequency_hz=125.0)  # Adult male pitch
        self.child_audio = generate_synthetic_pcm(frequency_hz=320.0)  # Child pitch

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_feature_extraction_speed_and_pitch(self):
        """Measures feature extraction latency (<50ms) and verifies pitch estimation."""
        t0 = time.perf_counter()
        adult_feats = self.engine.extract_features(self.adult_audio)
        dt = (time.perf_counter() - t0) * 1000

        # Sub-50ms criterion (typically ~2ms)
        self.assertLess(dt, 50.0)
        self.assertAlmostEqual(adult_feats["f0_mean_hz"], 125.0, delta=10.0)
        self.assertFalse(adult_feats["is_child_estimate"])

        # Child audio
        child_feats = self.engine.extract_features(self.child_audio)
        self.assertAlmostEqual(child_feats["f0_mean_hz"], 320.0, delta=15.0)
        self.assertTrue(child_feats["is_child_estimate"])

    def test_encrypted_storage_persistence(self):
        """Verifies Fernet AES encryption and successful decryption of profiles."""
        enc_file = self.temp_dir / "voice_profiles.enc"
        self.assertTrue(enc_file.exists())

        raw_enc = enc_file.read_bytes()
        # Verify file is not plaintext JSON
        self.assertNotIn(b"El Mustapha", raw_enc)
        self.assertNotIn(b"Ismail", raw_enc)

        # Re-instantiate engine pointing to the same encrypted file
        engine2 = VoiceIDEngine(storage_dir=self.temp_dir)
        profiles = engine2.get_profiles_summary()
        names = [p["name"] for p in profiles]
        self.assertIn("El Mustapha", names)
        self.assertIn("Ismail", names)

    def test_enrollment_and_identification(self):
        """Tests custom speaker enrollment and subsequent biometric identification."""
        new_audio = generate_synthetic_pcm(frequency_hz=190.0) # Adult female
        self.engine.enroll_speaker(name="Sarah", role=UserRole.ADULT, pcm_16k_bytes=new_audio)

        speaker, conf = self.engine.identify_speaker(new_audio)
        self.assertEqual(speaker.name, "Sarah")
        self.assertEqual(speaker.role, UserRole.ADULT)
        self.assertGreaterEqual(conf, 0.65)

    def test_rbac_child_protection(self):
        """Ensures child profiles are strictly forbidden from executing homelab admin commands."""
        child_profile = SpeakerProfile(
            name="Ismail",
            role=UserRole.CHILD,
            f0_mean_hz=310.0,
            spectral_centroid_hz=2600.0,
            is_protected_child=True,
        )
        adult_profile = SpeakerProfile(
            name="El Mustapha",
            role=UserRole.ADMIN,
            f0_mean_hz=122.0,
            spectral_centroid_hz=1400.0,
            is_protected_child=False,
        )

        homelab_prompt = "Régis, quel est l'état du serveur Proxmox et des conteneurs docker ?"
        harmless_prompt = "Régis, raconte-moi une histoire de dragon."

        # Child requesting homelab: BLOCKED
        allowed, reason = self.engine.check_permission(child_profile, homelab_prompt)
        self.assertFalse(allowed)
        self.assertIn("réservé aux adultes", reason)
        self.assertIn("Ismail", reason)

        # Child requesting story: ALLOWED
        allowed, _ = self.engine.check_permission(child_profile, harmless_prompt)
        self.assertTrue(allowed)

        # Adult requesting homelab: ALLOWED
        allowed, _ = self.engine.check_permission(adult_profile, homelab_prompt)
        self.assertTrue(allowed)

    async def test_brain_voiceid_integration_and_blocking(self):
        """Verifies end-to-end integration: Brain blocks child homelab requests automatically."""
        brain = Brain()
        # Mock child speaker
        brain.voice_id = self.engine
        self.engine.enroll_speaker("Ismail", UserRole.CHILD, self.child_audio)

        # A. Child asking for Proxmox status
        replies = []
        async for chunk in brain.generate_response_stream(
            "Quel est l'état de Proxmox ?", speaker_audio=self.child_audio
        ):
            replies.append(chunk)

        full_reply = " ".join(replies)
        self.assertIn("réservé aux adultes", full_reply)
        self.assertIn("Ismail", full_reply)

        # B. Voice query 'Qui suis-je'
        id_replies = []
        async for chunk in brain.generate_response_stream(
            "Régis, qui suis-je ?", speaker_audio=self.child_audio
        ):
            id_replies.append(chunk)

        id_full = " ".join(id_replies)
        self.assertIn("Ismail", id_full)
        self.assertIn("child", id_full)

    async def test_mcp_list_voice_profiles(self):
        """Verifies MCP tool 'homelab_list_voice_profiles' lists encrypted profiles."""
        mcp = McpManager()
        res = await mcp.call_tool("homelab_list_voice_profiles", {})
        self.assertIn("Profils vocaux enregistrés", res)
        self.assertIn("El Mustapha", res)


if __name__ == "__main__":
    unittest.main()
