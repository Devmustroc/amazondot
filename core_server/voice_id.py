"""
VoiceID & Role-Based Access Control (RBAC) Subsystem for TAD Core.
Provides speaker identification, biometric voiceprint extraction (<50ms),
and encrypted local storage of family voice profiles with child safety enforcement.
"""
import os
import json
import time
import base64
import logging
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Dict, Tuple, Any

import numpy as np
import scipy.signal
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core_server import config

logger = logging.getLogger("voice_id")


class UserRole(str, Enum):
    ADMIN = "admin"      # Full homelab, Proxmox, Docker, network & memory access
    ADULT = "adult"      # Standard adult profile, can consult servers and smart home
    CHILD = "child"      # Restricted profile: stories, facts, music; NO homelab/admin control
    GUEST = "guest"      # Unknown visitor: basic public facts only


# Actions reserved for ADMIN / ADULT users only
PROTECTED_HOMELAB_ACTIONS = {
    "homelab_get_proxmox_status",
    "homelab_get_cluster_resources",
    "homelab_get_docker_status",
    "homelab_admin",
    "server_monitoring",
    "container_control",
    "opnsense_rules",
    "network_config",
}


@dataclass
class SpeakerProfile:
    name: str
    role: UserRole
    f0_mean_hz: float
    spectral_centroid_hz: float
    voiceprint: List[float] = field(default_factory=list) # 16-D normalized vector
    enrolled_at: str = ""
    is_protected_child: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpeakerProfile":
        role_str = data.get("role", UserRole.GUEST.value)
        try:
            role = UserRole(role_str)
        except ValueError:
            role = UserRole.GUEST
        return cls(
            name=data["name"],
            role=role,
            f0_mean_hz=float(data.get("f0_mean_hz", 150.0)),
            spectral_centroid_hz=float(data.get("spectral_centroid_hz", 1500.0)),
            voiceprint=data.get("voiceprint", []),
            enrolled_at=data.get("enrolled_at", ""),
            is_protected_child=bool(data.get("is_protected_child", role == UserRole.CHILD)),
        )


class VoiceIDEngine:
    """
    Sub-50ms acoustic biometric voice recognition engine.
    Extracts fundamental frequency (F0) and Mel-filterbank spectral embeddings.
    Protects homelab administration against unauthorized non-adult users.
    """
    _instance: Optional["VoiceIDEngine"] = None

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (Path(config.BASE_DIR) / "core_server" / "data")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "voice_profiles.enc"
        self._profiles: Dict[str, SpeakerProfile] = {}
        self._fernet = self._init_crypto()
        self.load_profiles()

    @classmethod
    def get_instance(cls) -> "VoiceIDEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_crypto(self) -> Fernet:
        """Derives a reproducible symmetric encryption key for the local vault."""
        secret = os.getenv("VOICE_ID_SECRET", "tad-sovereign-family-voice-key-mustroc-2026")
        salt = b"tad_voice_salt_9400"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
        return Fernet(derived_key)

    def extract_features(self, pcm_16k_bytes: bytes) -> Dict[str, Any]:
        """
        Extracts acoustic features from 16kHz mono audio in < 5ms:
        1. F0 Pitch via Normalized Autocorrelation.
        2. Spectral Centroid.
        3. 16-D Mel Filterbank Embedding.
        """
        if len(pcm_16k_bytes) < 3200: # Need at least 0.2s of audio
            return {
                "f0_mean_hz": 150.0,
                "spectral_centroid_hz": 1500.0,
                "voiceprint": [0.0] * 16,
                "is_child_estimate": False,
            }

        samples = np.frombuffer(pcm_16k_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        sr = 16000

        # A. F0 Estimation via Autocorrelation (Speech window: 70Hz - 500Hz)
        # Take central 0.5s segment for cleanest voice pitch
        mid = len(samples) // 2
        seg_len = min(len(samples), 8000)
        start_idx = max(0, mid - seg_len // 2)
        segment = samples[start_idx:start_idx + seg_len]

        corr = scipy.signal.correlate(segment, segment, mode='full')
        corr = corr[len(corr) // 2:]
        min_lag = int(sr / 500) # 32 samples (~500Hz)
        max_lag = int(sr / 70)  # 228 samples (~70Hz)

        peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
        f0 = float(sr / peak_lag) if peak_lag > 0 else 150.0

        # B. 16-D Spectral Filterbank Embedding
        win_len = 512
        hop = 256
        n_frames = max(1, (len(samples) - win_len) // hop + 1)
        frames = np.lib.stride_tricks.as_strided(
            samples, shape=(n_frames, win_len),
            strides=(samples.strides[0] * hop, samples.strides[0])
        ) * np.hanning(win_len)

        mag_spec = np.abs(np.fft.rfft(frames, n=win_len))
        avg_spec = np.mean(mag_spec, axis=0) # shape (257,)

        # Compute Spectral Centroid
        freqs = np.linspace(0, sr / 2, len(avg_spec))
        spec_sum = np.sum(avg_spec)
        centroid = float(np.sum(freqs * avg_spec) / (spec_sum + 1e-8))

        # 16-D Filterbank
        mel_bins = np.linspace(0, len(avg_spec) - 1, 18).astype(int)
        fbank = np.zeros(16, dtype=np.float32)
        for i in range(16):
            fbank[i] = np.mean(avg_spec[mel_bins[i]:mel_bins[i + 2]])
        # L2-normalize
        norm = np.linalg.norm(fbank)
        if norm > 1e-8:
            fbank = fbank / norm

        # Children pitch threshold: typically > 240Hz with elevated spectral centroid
        is_child = bool(f0 > 245.0 or (f0 > 220.0 and centroid > 2200.0))

        return {
            "f0_mean_hz": round(f0, 1),
            "spectral_centroid_hz": round(centroid, 1),
            "voiceprint": [float(x) for x in fbank],
            "is_child_estimate": is_child,
        }

    def enroll_speaker(
        self,
        name: str,
        role: UserRole,
        pcm_16k_bytes: bytes,
        is_protected_child: Optional[bool] = None,
    ) -> SpeakerProfile:
        """Enrolls or updates a speaker profile from recorded audio."""
        feats = self.extract_features(pcm_16k_bytes)
        child_flag = is_protected_child if is_protected_child is not None else (role == UserRole.CHILD)
        profile = SpeakerProfile(
            name=name,
            role=role,
            f0_mean_hz=feats["f0_mean_hz"],
            spectral_centroid_hz=feats["spectral_centroid_hz"],
            voiceprint=feats["voiceprint"],
            enrolled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            is_protected_child=child_flag,
        )
        self._profiles[name.lower()] = profile
        self.save_profiles()
        logger.info("Enrolled speaker '%s' (Role: %s, F0: %.1fHz)", name, role.value, profile.f0_mean_hz)
        return profile

    def identify_speaker(self, pcm_16k_bytes: bytes) -> Tuple[SpeakerProfile, float]:
        """
        Identifies speaker in < 20ms using cosine similarity and pitch matching.
        Returns: (SpeakerProfile, confidence [0.0 - 1.0])
        """
        t0 = time.perf_counter()
        feats = self.extract_features(pcm_16k_bytes)
        f0 = feats["f0_mean_hz"]
        vp = np.array(feats["voiceprint"], dtype=np.float32)

        best_profile: Optional[SpeakerProfile] = None
        best_score = -1.0

        for p in self._profiles.values():
            if not p.voiceprint:
                continue
            ref_vp = np.array(p.voiceprint, dtype=np.float32)
            # Cosine similarity
            dot = float(np.dot(vp, ref_vp))
            # F0 pitch penalty if discrepancy > 60Hz
            f0_diff = abs(f0 - p.f0_mean_hz)
            pitch_penalty = max(0.0, (f0_diff - 40.0) / 200.0) * 0.3
            score = max(0.0, dot - pitch_penalty)

            if score > best_score:
                best_score = score
                best_profile = p

        dt = (time.perf_counter() - t0) * 1000

        # Confidence threshold: 0.65
        if best_profile and best_score >= 0.65:
            logger.info("Identified speaker: '%s' (Confidence: %.2f, F0: %.1fHz) in %.2fms", best_profile.name, best_score, f0, dt)
            return best_profile, round(best_score, 2)

        # Fallback to acoustic classification: Child vs Adult
        if feats["is_child_estimate"]:
            generic = SpeakerProfile(
                name="Enfant",
                role=UserRole.CHILD,
                f0_mean_hz=f0,
                spectral_centroid_hz=feats["spectral_centroid_hz"],
                is_protected_child=True,
            )
            conf = 0.85
        else:
            generic = SpeakerProfile(
                name="Adulte",
                role=UserRole.ADULT,
                f0_mean_hz=f0,
                spectral_centroid_hz=feats["spectral_centroid_hz"],
                is_protected_child=False,
            )
            conf = 0.80

        logger.info("Speaker not matched to enrolled DB. Classified acoustically as '%s' (F0: %.1fHz) in %.2fms", generic.name, f0, dt)
        return generic, conf

    def check_permission(self, speaker: SpeakerProfile, action_or_prompt: str) -> Tuple[bool, str]:
        """
        Enforces Role-Based Access Control (RBAC).
        Returns: (is_allowed, denial_reason_or_empty)
        """
        prompt_lower = action_or_prompt.lower()
        is_homelab_request = any(
            k in prompt_lower
            for k in [
                "proxmox", "serveur", "docker", "conteneur", "machine virtuelle",
                "vm", "cluster", "opnsense", "redémarre", "reboot", "stop", "root"
            ]
        )

        if is_homelab_request and (speaker.is_protected_child or speaker.role == UserRole.CHILD):
            reason = f"Désolé {speaker.name}, l'accès aux commandes d'administration du serveur est réservé aux adultes."
            logger.warning("RBAC Security Alert: Blocked action '%s' for child speaker '%s'", action_or_prompt, speaker.name)
            return False, reason

        return True, ""

    def save_profiles(self):
        """Serializes and encrypts speaker profiles to disk."""
        try:
            data = {k: v.to_dict() for k, v in self._profiles.items()}
            raw_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            enc_bytes = self._fernet.encrypt(raw_bytes)
            self.storage_path.write_bytes(enc_bytes)
            logger.debug("Saved %d encrypted voice profiles to %s", len(self._profiles), self.storage_path)
        except Exception as e:
            logger.error("Failed to save encrypted voice profiles: %s", e)

    def load_profiles(self):
        """Decrypts and loads speaker profiles from disk. Seeds defaults if not present."""
        if not self.storage_path.exists():
            self._seed_default_family_profiles()
            return

        try:
            enc_bytes = self.storage_path.read_bytes()
            raw_bytes = self._fernet.decrypt(enc_bytes)
            data = json.loads(raw_bytes.decode("utf-8"))
            self._profiles = {k: SpeakerProfile.from_dict(v) for k, v in data.items()}
            logger.info("Loaded %d encrypted voice profile(s) from %s", len(self._profiles), self.storage_path)
        except Exception as e:
            logger.warning("Could not decrypt %s (%s). Re-seeding defaults.", self.storage_path, e)
            self._seed_default_family_profiles()

    def _seed_default_family_profiles(self):
        """Seeds baseline profiles for El Mustapha (Admin) and Ismail (Child)."""
        # Baseline adult profile (F0 ~120Hz)
        mustapha = SpeakerProfile(
            name="El Mustapha",
            role=UserRole.ADMIN,
            f0_mean_hz=122.0,
            spectral_centroid_hz=1450.0,
            voiceprint=[0.25] * 16,
            enrolled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            is_protected_child=False,
        )
        # Baseline child profile (F0 ~310Hz)
        ismail = SpeakerProfile(
            name="Ismail",
            role=UserRole.CHILD,
            f0_mean_hz=315.0,
            spectral_centroid_hz=2800.0,
            voiceprint=[0.25] * 16,
            enrolled_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            is_protected_child=True,
        )
        self._profiles = {
            "el mustapha": mustapha,
            "ismail": ismail,
        }
        self.save_profiles()
        logger.info("Seeded default family voice profiles: El Mustapha (Admin), Ismail (Child).")

    def get_profiles_summary(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._profiles.values()]


# Global singleton instance
global_voice_id = VoiceIDEngine.get_instance()
