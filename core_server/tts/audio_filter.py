"""
DSP and acoustic filtering for Echo Dot 2G hardware DAC & speaker transducer.
"""
import io
from math import gcd
import numpy as np
import scipy.signal as sps
import soundfile as sf


def process_audio_for_echo_dot(data: np.ndarray, sr: int) -> bytes:
    """
    Applies Echo Dot 2G hardware acoustic processing:
    1. Resample to 48kHz native DAC sample rate.
    2. 2nd-order High-Pass filter at 220Hz (cuts sub-bass that causes 35mm transducer rattling and clipping).
    3. Soft peak limiting to 0.65 (-3.7 dBFS) to keep the internal Class-D amplifier in its linear low-THD range.
    4. Export to 48kHz 16-bit stereo WAV.
    """
    target_sr = 48000
    if sr != target_sr:
        g = gcd(target_sr, sr)
        data = sps.resample_poly(data, target_sr // g, sr // g)

    # Highpass filter at 220Hz to eliminate speaker overload and acoustic rattling
    b, a = sps.butter(2, 220.0 / (target_sr / 2.0), btype="highpass")
    data = sps.lfilter(b, a, data, axis=0)

    # Peak normalization to 0.65 to prevent amplifier clipping
    peak = float(np.max(np.abs(data)))
    if peak > 0.001:
        data = (data / peak) * 0.65

    data = np.clip(data, -1.0, 1.0)

    # Ensure stereo (2 channels)
    if len(data.shape) == 1:
        data = np.column_stack([data, data])
    elif data.shape[1] == 1:
        data = np.column_stack([data[:, 0], data[:, 0]])

    out_buf = io.BytesIO()
    sf.write(out_buf, data, target_sr, format="WAV", subtype="PCM_16")
    return out_buf.getvalue()
