"""In-process real-time event bus feeding WebSocket clients.

Services publish from any thread; delivery is scheduled on the server event
loop. Each event carries an audience so that private behavioral-health
events only reach authorized connections.
"""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from . import db
from .security import Principal, can_see_private_exists, can_view_astronaut, can_view_private


@dataclass
class Subscriber:
    principal: Principal
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


@dataclass
class EventBus:
    subscribers: list[Subscriber] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    history: list[dict] = field(default_factory=list)  # recent events (diagnostics/tests)

    def subscribe(self, principal: Principal, loop: asyncio.AbstractEventLoop) -> Subscriber:
        sub = Subscriber(principal, asyncio.Queue(maxsize=1000), loop)
        with self.lock:
            self.subscribers.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self.lock:
            if sub in self.subscribers:
                self.subscribers.remove(sub)

    @staticmethod
    def allowed(p: Principal, astronaut_id: str | None, private: bool) -> tuple[bool, bool]:
        """Returns (deliver, redact)."""
        if private:
            if can_view_private(p, astronaut_id):
                return True, False
            if can_see_private_exists(p, astronaut_id):
                return True, True
            return False, False
        return can_view_astronaut(p, astronaut_id), False

    def publish(self, event_type: str, payload: dict[str, Any], *, astronaut_id: str | None = None,
                private: bool = False) -> None:
        event = {"type": event_type, "at": db.now_iso(), "astronaut_id": astronaut_id,
                 "private": private, "payload": payload}
        with self.lock:
            self.history.append(event)
            del self.history[:-500]
            subs = list(self.subscribers)
        for sub in subs:
            deliver, redact = self.allowed(sub.principal, astronaut_id, private)
            if not deliver:
                continue
            msg = event if not redact else {**event, "payload": {"redacted": True, "id": payload.get("id"),
                                                                   "severity": payload.get("severity")}}
            try:
                sub.loop.call_soon_threadsafe(_put_nowait, sub.queue, msg)
            except RuntimeError:
                pass  # loop closed


def _put_nowait(q: asyncio.Queue, msg: dict) -> None:
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        pass


BUS = EventBus()
