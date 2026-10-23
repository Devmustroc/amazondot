import math
import struct
import wave

SAMPLE_RATE = 16000
DURATION_SEC = 1.5
FREQ = 440.0

with wave.open("tools/test_tone.wav", "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2) # 16 bits
    wav_file.setframerate(SAMPLE_RATE)
    
    num_samples = int(SAMPLE_RATE * DURATION_SEC)
    for i in range(num_samples):
        # 440Hz tone with smooth fade in/out
        envelope = math.sin(math.pi * i / num_samples)
        sample = int(32767.0 * 0.5 * envelope * math.sin(2.0 * math.pi * FREQ * i / SAMPLE_RATE))
        wav_file.writeframes(struct.pack("<h", sample))

print("tools/test_tone.wav generated")
