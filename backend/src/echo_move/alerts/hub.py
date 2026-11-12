"""Fan-out for confirmed alerts: persist → notify → push to live web clients.

``publish`` may be called from camera threads or executor threads; WebSocket subscribers
live on the asyncio loop, so delivery goes through ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..notify import Notifier
from ..storage import EventStore
from .engine import Alert

log = logging.getLogger(__name__)


class AlertHub:
    def __init__(self, store: EventStore | None = None, notifier: Notifier | None = None):
        self.store = store
        self.notifier = notifier
        self._subs: dict[asyncio.Queue[dict[str, Any]], asyncio.AbstractEventLoop] = {}

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self._subs[q] = asyncio.get_running_loop()
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.pop(q, None)

    def publish(self, alert: Alert, jpeg: bytes | None = None) -> dict[str, Any]:
        try:
            event = self.store.add(alert, jpeg) if self.store else alert.to_dict()
        except Exception:
            log.exception("failed to store event")
            event = alert.to_dict()
        log.warning("ALERT %s [%s] %s track=%s %s", alert.type, alert.source, alert.message,
                    alert.track_id, alert.detail)
        if self.notifier:
            self.notifier.send(event, jpeg)
        self._broadcast(event)
        return event

    def attach_clip(self, event: dict[str, Any], frames: list[bytes], fps: float) -> None:
        """Save the pre/post-event clip of a stored event and send it as a follow-up."""
        if self.store is None or event.get("id") is None:
            return
        try:
            mp4 = self.store.save_clip(int(event["id"]), frames, fps)
        except Exception:
            log.exception("failed to save clip for event %s", event.get("id"))
            return
        if mp4 is not None and self.notifier:
            self.notifier.send_video(event, mp4.read_bytes())
        self._broadcast({"update": "clip", "id": event["id"]})

    def _broadcast(self, message: dict[str, Any]) -> None:
        for q, loop in list(self._subs.items()):
            try:
                loop.call_soon_threadsafe(_offer, q, message)
            except RuntimeError:  # loop closed
                self._subs.pop(q, None)


def _offer(q: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass
