import subprocess
import time
import os

print("Starting tinycap capture on Echo Dot...")
proc = subprocess.Popen(
    ["adb", "shell", "su -c 'exec tinycap /data/local/tmp/test.wav -D 0 -d 24 -r 16000 -b 24 -c 9 -p 512 -n 5'"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

time.sleep(2.5)
print("Sending SIGINT to gracefully close WAV...")
proc.send_signal(subprocess.signal.SIGINT)
try:
    stdout, stderr = proc.communicate(timeout=3)
    print("STDOUT:", stdout.decode("utf-8", errors="ignore"))
    print("STDERR:", stderr.decode("utf-8", errors="ignore"))
except subprocess.TimeoutExpired:
    proc.kill()

# Pull file
subprocess.run(["adb", "pull", "/data/local/tmp/test.wav", "tools/mic_test.wav"])
if os.path.exists("tools/mic_test.wav"):
    size = os.path.getsize("tools/mic_test.wav")
    print(f"tools/mic_test.wav pulled! Size: {size} bytes")
else:
    print("Failed to pull mic_test.wav")
