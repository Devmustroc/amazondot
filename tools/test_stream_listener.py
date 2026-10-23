import socket
import sys

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 8001))
s.listen(1)
print("Listening on 0.0.0.0:8001...")
sys.stdout.flush()

conn, addr = s.accept()
print(f"Connected by {addr}")
sys.stdout.flush()

total_bytes = 0
with open("test_stream_received.pcm", "wb") as f:
    while True:
        data = conn.recv(4096)
        if not data:
            break
        f.write(data)
        total_bytes += len(data)
        if total_bytes >= 64000: # ~2 seconds
            print(f"Received {total_bytes} bytes!")
            break

conn.close()
s.close()
print("Done!")
