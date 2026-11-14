"""Self-test a public ASTRA URL: health endpoint, sign-in and WebSocket.

    python tools/check_public_url.py https://xxxx.trycloudflare.com --password <demo password>

Standard library only, so it runs with any Python 3.10+.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


def http_json(url: str, body: dict | None = None, timeout: float = 15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": "astra-public-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def _recv_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf += chunk
    return buf


def ws_connect(base_url: str, path: str, timeout: float = 15) -> tuple[int, str]:
    """Open a WebSocket to base_url+path. Returns (HTTP status, first text frame or '')."""
    u = urlparse(base_url)
    secure = u.scheme == "https"
    port = u.port or (443 if secure else 80)
    raw = socket.create_connection((u.hostname, port), timeout=timeout)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=u.hostname) if secure else raw
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        host = u.hostname if u.port is None else f"{u.hostname}:{u.port}"
        sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                      f"User-Agent: astra-public-check\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.recv(1)
            if not chunk:
                break
            head += chunk
        status = int(head.split(b" ", 2)[1]) if head.startswith(b"HTTP/") else 0
        if status != 101:
            return status, ""
        b1, b2 = _recv_exact(sock, 2)
        length = b2 & 0x7F
        if length == 126:
            length = int.from_bytes(_recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(_recv_exact(sock, 8), "big")
        payload = _recv_exact(sock, length)
        return status, payload.decode("utf-8", "replace") if (b1 & 0x0F) == 1 else ""
    finally:
        sock.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--password", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--wait", type=int, default=90, help="seconds to wait for the tunnel DNS to come up")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    deadline = time.time() + a.wait
    status = 0
    while time.time() < deadline:
        try:
            status, body = http_json(base + "/api/v1/health")
            if status == 200:
                break
        except Exception:
            pass
        time.sleep(3)
    print(f"  health       : {'OK' if status == 200 else f'FAILED ({status})'}")
    if status != 200:
        return 1

    status, body = http_json(base + "/api/v1/auth/login", {"username": a.user, "password": a.password})
    ok_login = status == 200 and body and body.get("token")
    print(f"  sign-in      : {'OK' if ok_login else f'FAILED ({status})'}")
    if not ok_login:
        return 1

    try:
        ws_status, msg = ws_connect(base, "/ws?token=" + body["token"])
    except Exception as e:  # noqa: BLE001
        ws_status, msg = 0, str(e)
    ok_ws = ws_status == 101 and '"hello"' in msg
    print(f"  websocket    : {'OK' if ok_ws else f'FAILED ({ws_status}) {msg}'}")
    return 0 if ok_ws else 1


if __name__ == "__main__":
    sys.exit(main())
