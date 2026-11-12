"""Periodic housekeeping: data retention and escalation of unhandled CRITICAL events."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from .alerts import AlertHub
from .config import Settings
from .notify import Notifier
from .storage import EventStore

log = logging.getLogger(__name__)


@dataclass
class Maintenance:
    cfg: Settings
    store: EventStore | None
    notifier: Notifier | None
    hub: AlertHub | None = None
    purge_every_s: float = 3600.0
    _last_purge: float = 0.0

    def run_once(self, now: float | None = None) -> dict[str, int]:
        now = time.time() if now is None else now
        done = {"purged": 0, "escalated": 0}
        if self.store is None:
            return done
        if self.cfg.retention_days > 0 and now - self._last_purge >= self.purge_every_s:
            self._last_purge = now
            done["purged"] = self.store.purge(now - self.cfg.retention_days * 86400)
            if done["purged"]:
                log.info("retention: deleted %d events older than %.0f days", done["purged"],
                         self.cfg.retention_days)
        if self.cfg.escalate_min > 0:
            for ev in self.store.due_escalation(now - self.cfg.escalate_min * 60):
                if self.notifier:
                    self.notifier.send({**ev, "escalation": True})
                self.store.mark_escalated(ev["id"])
                done["escalated"] += 1
                log.warning("escalated unacknowledged event %s (%s)", ev["id"], ev["type"])
            if done["escalated"] and self.hub:
                self.hub._broadcast({"update": "escalated", "count": done["escalated"]})
        return done

    async def loop(self, period_s: float = 60.0) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                await loop.run_in_executor(None, self.run_once)
            except Exception:
                log.exception("maintenance failed")
            await asyncio.sleep(period_s)
