"""Outbound alert notifications (Telegram bot, generic JSON webhook).

Runs on a background thread with a bounded queue: a slow or unreachable endpoint can never
stall video processing. Disabled channels (no token / URL) are simply skipped.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

from ..config import Settings

log = logging.getLogger(__name__)

Opener = Callable[[urllib.request.Request, float], Any]


def _default_open(req: urllib.request.Request, timeout: float) -> Any:
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (configured URL)
        return resp.read()


def _multipart(fields: dict[str, str], file_field: str, filename: str,
               payload: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                     f"{v}\r\n".encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()
        + payload + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def format_message(event: dict[str, Any]) -> str:
    when = time.strftime("%H:%M:%S %d/%m/%Y", time.localtime(event.get("ts") or event.get("t")))
    who = f" · người #{event['track_id']}" if event.get("track_id") is not None else ""
    return (f"⚠️ ECHO MOVE [{event.get('level')}] {event.get('message')}\n"
            f"Camera: {event.get('source')}{who}\n"
            f"Chi tiết: {event.get('detail') or '-'}\nThời gian: {when}")


class Notifier:
    def __init__(self, cfg: Settings, opener: Opener | None = None, timeout: float = 10.0):
        self.telegram = bool(cfg.telegram_token and cfg.telegram_chat_id)
        self.webhook = bool(cfg.webhook_url)
        self._cfg = cfg
        self._open = opener or _default_open
        self._timeout = timeout
        self._q: queue.Queue[tuple[dict[str, Any], bytes | None] | None] = queue.Queue(maxsize=100)
        self._thread: threading.Thread | None = None
        self.sent = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return self.telegram or self.webhook

    def channels(self) -> list[str]:
        return [n for n, on in (("telegram", self.telegram), ("webhook", self.webhook)) if on]

    def start(self) -> None:
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="notifier", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._q.put(None)
            self._thread.join(timeout=5)
            self._thread = None

    def send(self, event: dict[str, Any], jpeg: bytes | None = None) -> bool:
        if not self.enabled:
            return False
        try:
            self._q.put_nowait((event, jpeg))
            return True
        except queue.Full:
            log.warning("notification queue full, dropping event %s", event.get("id"))
            return False

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            self.deliver(*item)

    def deliver(self, event: dict[str, Any], jpeg: bytes | None) -> None:
        """Synchronously send one event on every enabled channel (used by the worker)."""
        if self.telegram:
            self._try("telegram", lambda: self._telegram(event, jpeg))
        if self.webhook:
            self._try("webhook", lambda: self._webhook(event))

    def _try(self, name: str, fn: Callable[[], Any]) -> None:
        for attempt in range(3):
            try:
                fn()
                self.sent += 1
                return
            except Exception as exc:  # network errors must never propagate
                log.warning("%s notification failed (try %d): %s", name, attempt + 1, exc)
                time.sleep(0.5 * (attempt + 1))
        self.failed += 1

    def _telegram(self, event: dict[str, Any], jpeg: bytes | None) -> None:
        base = f"https://api.telegram.org/bot{self._cfg.telegram_token}"
        text = format_message(event)
        if jpeg:
            body, ctype = _multipart({"chat_id": self._cfg.telegram_chat_id, "caption": text},
                                     "photo", "alert.jpg", jpeg)
            req = urllib.request.Request(f"{base}/sendPhoto", data=body,
                                         headers={"Content-Type": ctype})
        else:
            data = json.dumps({"chat_id": self._cfg.telegram_chat_id, "text": text}).encode()
            req = urllib.request.Request(f"{base}/sendMessage", data=data,
                                         headers={"Content-Type": "application/json"})
        self._open(req, self._timeout)

    def _webhook(self, event: dict[str, Any]) -> None:
        data = json.dumps({"event": event, "text": format_message(event)},
                          ensure_ascii=False).encode()
        req = urllib.request.Request(self._cfg.webhook_url, data=data,
                                     headers={"Content-Type": "application/json"})
        self._open(req, self._timeout)
