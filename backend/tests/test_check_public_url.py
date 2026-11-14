"""The public-URL checker's WebSocket client against a minimal local WebSocket server."""
import base64
import hashlib
import importlib.util
import json
import socket
import threading
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_public_url", Path(__file__).resolve().parents[2] / "tools" / "check_public_url.py")
cpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpu)
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def serve_once(sock, accept_token):
    conn, _ = sock.accept()
    data = b""
    while b"\r\n\r\n" not in data:
        data += conn.recv(4096)
    head = data.decode()
    path = head.split(" ")[1]
    key = [l.split(": ")[1] for l in head.split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
    if f"token={accept_token}" not in path:
        conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        conn.close()
        return
    acc = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {acc}\r\n\r\n".encode())
    payload = json.dumps({"type": "hello", "payload": {"x": "y" * 200}}).encode()
    conn.sendall(bytes([0x81, 126]) + len(payload).to_bytes(2, "big") + payload)
    conn.close()


def test_ws_client_reads_first_frame_and_detects_refusal():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(2)
    port = sock.getsockname()[1]
    t = threading.Thread(target=lambda: [serve_once(sock, "good"), serve_once(sock, "good")], daemon=True)
    t.start()
    status, msg = cpu.ws_connect(f"http://127.0.0.1:{port}", "/ws?token=good")
    assert status == 101 and '"hello"' in msg
    status2, _ = cpu.ws_connect(f"http://127.0.0.1:{port}", "/ws?token=bad")
    assert status2 == 403
