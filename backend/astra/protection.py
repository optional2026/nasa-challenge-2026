"""HTTP protection layer (pure ASGI middleware, so WebSockets pass through untouched).

Always on:
* security headers (no sniffing, no framing, strict referrer, restrictive CSP on pages),
* request-body size limit.

Public demo mode (ASTRA_PUBLIC_DEMO=1, used by tools/start_public_demo.*):
* per-client rate limits (login attempts, write requests, all requests),
* configuration-changing endpoints that would let a visitor alter the shared demo's
  clinical logic are disabled (rule versions).
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict, deque

from . import config

MAX_BODY_BYTES = 512 * 1024
# The signed server-to-server replication endpoint carries batches of up to a few hundred records; it has its own
# limit (checked again in routes_replication) and is authenticated by HMAC, not by a user session.
LARGE_BODY_PATHS = {"/api/v1/replication/batch": 20 * 1024 * 1024}

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
CSP = (b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       b"connect-src 'self' ws: wss:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
       b"form-action 'self'")

# (method, path regex) blocked in public demo mode
PUBLIC_BLOCKED = [
    ("POST", re.compile(r"^/api/v1/rules/[^/]+/versions$")),
]

# limits: (max requests, window seconds)
LIMITS = {
    "login": (20, 600),  # FAILED login attempts only (shared venue IPs must not lock out judges)
    "write": (300, 60),
    "any": (1500, 60),
}


class RateLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    def allow(self, bucket: str, client: str) -> tuple[bool, int]:
        limit, window = LIMITS[bucket]
        now = time.monotonic()
        with self.lock:
            q = self.hits[(bucket, client)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False, int(window - (now - q[0])) + 1
            q.append(now)
            return True, 0

    def blocked(self, bucket: str, client: str) -> tuple[bool, int]:
        limit, window = LIMITS[bucket]
        now = time.monotonic()
        with self.lock:
            q = self.hits[(bucket, client)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return True, int(window - (now - q[0])) + 1
            return False, 0

    def record(self, bucket: str, client: str) -> None:
        with self.lock:
            self.hits[(bucket, client)].append(time.monotonic())

    def reset(self):
        with self.lock:
            self.hits.clear()


LIMITER = RateLimiter()


def client_key(scope) -> str:
    headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    # Behind Cloudflare Tunnel every request comes from 127.0.0.1; Cloudflare supplies the visitor IP.
    for h in ("cf-connecting-ip", "x-forwarded-for"):
        if headers.get(h):
            return headers[h].split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send, status: int, code: str, message: str, extra_headers=()):
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *SECURITY_HEADERS, *extra_headers]})
    await send({"type": "http.response.body", "body": body})


class ProtectionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        method, path = scope["method"], scope["path"]
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        max_body = LARGE_BODY_PATHS.get(path, MAX_BODY_BYTES) if method == "POST" else MAX_BODY_BYTES
        try:
            if int(headers.get("content-length", "0") or 0) > max_body:
                return await _send_json(send, 413, "payload_too_large", f"request body larger than {max_body} bytes")
        except ValueError:
            return await _send_json(send, 400, "bad_request", "invalid Content-Length")

        if config.public_demo():
            for m, rx in PUBLIC_BLOCKED:
                if method == m and rx.match(path):
                    return await _send_json(send, 403, "disabled_in_public_demo",
                                            "this configuration change is disabled on the public demonstration server")
            who = client_key(scope)
            is_login = method == "POST" and path == "/api/v1/auth/login"
            buckets = ["any"]
            if method in ("POST", "PUT", "PATCH", "DELETE") and not is_login:
                buckets.append("write")
            for b in buckets:
                ok, retry = LIMITER.allow(b, who)
                if not ok:
                    return await _send_json(send, 429, "rate_limited", f"too many requests; retry in {retry} s",
                                            [(b"retry-after", str(retry).encode())])
            if is_login:
                blocked, retry = LIMITER.blocked("login", who)
                if blocked:
                    return await _send_json(send, 429, "rate_limited", f"too many failed sign-in attempts; retry in {retry} s",
                                            [(b"retry-after", str(retry).encode())])

        # enforce the size limit also for chunked bodies without Content-Length
        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > max_body:
                    raise ValueError("request body too large")
            return msg

        failed_login = config.public_demo() and method == "POST" and path == "/api/v1/auth/login"

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                if failed_login and msg["status"] == 401:
                    LIMITER.record("login", client_key(scope))
                hdrs = list(msg.get("headers", []))
                names = {k.lower() for k, _ in hdrs}
                hdrs += [h for h in SECURITY_HEADERS if h[0] not in names]
                ctype = dict((k.lower(), v) for k, v in hdrs).get(b"content-type", b"")
                if ctype.startswith(b"text/html"):
                    hdrs.append((b"content-security-policy", CSP))
                if path.startswith("/api/"):
                    hdrs.append((b"cache-control", b"no-store"))
                msg = {**msg, "headers": hdrs}
            await send(msg)

        try:
            await self.app(scope, limited_receive, send_with_headers)
        except ValueError as e:
            if "too large" in str(e):
                return await _send_json(send, 413, "payload_too_large", str(e))
            raise
