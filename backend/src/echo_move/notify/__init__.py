"""Outbound alert notifications (Telegram bot, Zalo OA, generic JSON webhook).

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
from dataclasses import dataclass
from functools import partial
from typing import Any

from ..config import Settings

log = logging.getLogger(__name__)

Opener = Callable[[urllib.request.Request, float], Any]
ZALO_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"


def _default_open(req: urllib.request.Request, timeout: float) -> Any:
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (configured URL)
        return resp.read()


def _multipart(fields: dict[str, str], file_field: str, filename: str,
               payload: bytes, content_type: str = "image/jpeg") -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                     f"{v}\r\n".encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
        + payload + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def format_message(event: dict[str, Any]) -> str:
    when = time.strftime("%H:%M:%S %d/%m/%Y", time.localtime(event.get("ts") or event.get("t")))
    who = f" · người #{event['track_id']}" if event.get("track_id") is not None else ""
    head = "⏫ LEO THANG — CHƯA AI XỬ LÝ\n" if event.get("escalation") else ""
    return (f"{head}⚠️ ECHO MOVE [{event.get('level')}] {event.get('message')}\n"
            f"Camera: {event.get('source')}{who}\n"
            f"Chi tiết: {event.get('detail') or '-'}\nThời gian: {when}")


@dataclass
class _Item:
    event: dict[str, Any]
    jpeg: bytes | None = None
    video: bytes | None = None


class Notifier:
    def __init__(self, cfg: Settings, opener: Opener | None = None, timeout: float = 10.0):
        self.telegram = bool(cfg.telegram_token and cfg.telegram_chat_id)
        self.zalo = bool(cfg.zalo_token and cfg.zalo_user_id)
        self.webhook = bool(cfg.webhook_url)
        self._cfg = cfg
        self._open = opener or _default_open
        self._timeout = timeout
        self._q: queue.Queue[_Item | None] = queue.Queue(maxsize=100)
        self._thread: threading.Thread | None = None
        self.sent = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return self.telegram or self.zalo or self.webhook

    def channels(self) -> list[str]:
        return [n for n, on in (("telegram", self.telegram), ("zalo", self.zalo),
                                ("webhook", self.webhook)) if on]

    def start(self) -> None:
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="notifier", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._q.put(None)
            self._thread.join(timeout=5)
            self._thread = None

    def _enqueue(self, item: _Item) -> bool:
        if not self.enabled:
            return False
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            log.warning("notification queue full, dropping event %s", item.event.get("id"))
            return False

    def send(self, event: dict[str, Any], jpeg: bytes | None = None) -> bool:
        return self._enqueue(_Item(event, jpeg))

    def send_video(self, event: dict[str, Any], mp4: bytes) -> bool:
        """Follow-up clip for an event already notified (Telegram only)."""
        if not self.telegram:
            return False
        return self._enqueue(_Item(event, video=mp4))

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            if item.video is not None:
                self._try("telegram", partial(self._telegram_video, item.event, item.video))
            else:
                self.deliver(item.event, item.jpeg)

    def deliver(self, event: dict[str, Any], jpeg: bytes | None) -> None:
        """Synchronously send one event on every enabled channel (used by the worker)."""
        if self.telegram:
            self._try("telegram", lambda: self._telegram(event, jpeg))
        if self.zalo:
            self._try("zalo", lambda: self._zalo(event))
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

    def _chat(self, event: dict[str, Any]) -> str:
        if event.get("escalation") and self._cfg.escalate_chat_id:
            return self._cfg.escalate_chat_id
        return self._cfg.telegram_chat_id

    def _telegram(self, event: dict[str, Any], jpeg: bytes | None) -> None:
        base = f"https://api.telegram.org/bot{self._cfg.telegram_token}"
        text = format_message(event)
        chat = self._chat(event)
        if jpeg:
            body, ctype = _multipart({"chat_id": chat, "caption": text}, "photo", "alert.jpg", jpeg)
            req = urllib.request.Request(f"{base}/sendPhoto", data=body,
                                         headers={"Content-Type": ctype})
        else:
            data = json.dumps({"chat_id": chat, "text": text}).encode()
            req = urllib.request.Request(f"{base}/sendMessage", data=data,
                                         headers={"Content-Type": "application/json"})
        self._open(req, self._timeout)

    def _telegram_video(self, event: dict[str, Any], mp4: bytes) -> None:
        base = f"https://api.telegram.org/bot{self._cfg.telegram_token}"
        caption = (f"🎬 Clip sự kiện #{event.get('id')} — {event.get('message')}"
                   f" ({event.get('source')})")
        body, ctype = _multipart({"chat_id": self._chat(event), "caption": caption,
                                  "supports_streaming": "true"},
                                 "video", f"event_{event.get('id')}.mp4", mp4, "video/mp4")
        req = urllib.request.Request(f"{base}/sendVideo", data=body,
                                     headers={"Content-Type": ctype})
        self._open(req, max(self._timeout, 30.0))

    def _zalo(self, event: dict[str, Any]) -> None:
        data = json.dumps({"recipient": {"user_id": self._cfg.zalo_user_id},
                           "message": {"text": format_message(event)[:2000]}},
                          ensure_ascii=False).encode()
        req = urllib.request.Request(ZALO_URL, data=data, headers={
            "Content-Type": "application/json", "access_token": self._cfg.zalo_token})
        resp = self._open(req, self._timeout)
        try:
            body = json.loads(resp) if resp else {}
        except (TypeError, ValueError):
            body = {}
        if isinstance(body, dict) and body.get("error", 0) not in (0, None):
            raise RuntimeError(f"Zalo error {body.get('error')}: {body.get('message')}")

    def _webhook(self, event: dict[str, Any]) -> None:
        data = json.dumps({"event": event, "text": format_message(event)},
                          ensure_ascii=False).encode()
        req = urllib.request.Request(self._cfg.webhook_url, data=data,
                                     headers={"Content-Type": "application/json"})
        self._open(req, self._timeout)
