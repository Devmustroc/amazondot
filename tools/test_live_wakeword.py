import socket
import time
import numpy as np
import openwakeword
from openwakeword.model import Model

print("Loading openWakeWord model...")
models = openwakeword.get_pretrained_model_paths()
alexa_path = [m for m in models if "alexa" in m][0]
m = Model(wakeword_model_paths=[alexa_path])
model_key = list(m.models.keys())[0]
print(f"Model loaded: {model_key}")

s = socket.socket()
s.settimeout(5.0)
s.connect(("192.168.1.23", 9000))
print("Connected to Echo Dot mic stream! Listening... (speak 'Alexa' now!)")

raw_buf = bytearray()
audio_accum = bytearray()
start = time.time()
last_print = time.time()
max_score = 0.0


while time.time() - start < 15:
    chunk = s.recv(4320)
    if not chunk:
        break

    raw_buf.extend(chunk)
    # 27 bytes per frame
    num_frames = len(raw_buf) // 27
    if num_frames == 0:
        continue

    consumed = num_frames * 27
    frames = raw_buf[:consumed]
    del raw_buf[:consumed]

    # Beamform 7 mics: sample in b0 (offset) and b1 (offset+1)
    acc = np.zeros(num_frames, dtype=np.float32)
    for ch in range(7):
        off = ch * 3
        b0 = np.frombuffer(frames[off::27], dtype=np.uint8)
        b1 = np.frombuffer(frames[off+1::27], dtype=np.int8)
        acc += ((b1.astype(np.int16) << 8) | b0.astype(np.int16)).astype(np.float32)

    mono = (acc / 7.0).astype(np.int16)
    audio_accum.extend(mono.tobytes())

    # Feed 1280-sample blocks to openWakeWord
    while len(audio_accum) >= 2560:
        block = np.frombuffer(audio_accum[:2560], dtype=np.int16)
        del audio_accum[:2560]
        res = m.predict(block)
        score = res.get(model_key, 0.0)
        if score > max_score:
            max_score = score
        if score >= 0.05:
            print(f">>> DETECTED SCORE: {score:.3f} <<<")

    if time.time() - last_print >= 0.5:
        rms = np.sqrt(np.mean(mono.astype(np.float32)**2)) if len(mono) > 0 else 0

        print(f"Audio level RMS: {rms:6.1f} | Peak Alexa Score: {max_score:.4f}")
        last_print = time.time()

s.close()
print("Test completed!")
