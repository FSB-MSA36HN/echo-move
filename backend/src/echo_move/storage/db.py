"""SQLite event log with JPEG snapshots on disk (stdlib only, safe across threads)."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..alerts.engine import Alert

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    source TEXT NOT NULL,
    track_id INTEGER,
    type TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    snapshot TEXT,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    ack_ts REAL,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
"""

COLUMNS = ("id", "ts", "source", "track_id", "type", "level", "message", "detail",
           "snapshot", "acknowledged", "ack_ts", "data")


class EventStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.snap_dir = self.data_dir / "snapshots"
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "echo.db"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["data"] = json.loads(d.get("data") or "{}")
        d["acknowledged"] = bool(d["acknowledged"])
        d["has_image"] = bool(d.pop("snapshot", None))
        return d

    def add(self, alert: Alert, jpeg: bytes | None = None) -> dict[str, Any]:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO events (ts, source, track_id, type, level, message, detail, data)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (alert.t, alert.source, alert.track_id, alert.type, alert.level,
                 alert.message, alert.detail, json.dumps(alert.data, ensure_ascii=False)),
            )
            event_id = int(cur.lastrowid or 0)
            if jpeg:
                name = f"{event_id:06d}_{alert.type.lower()}.jpg"
                (self.snap_dir / name).write_bytes(jpeg)
                self._db.execute("UPDATE events SET snapshot = ? WHERE id = ?", (name, event_id))
            self._db.commit()
            row = self._db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row(row)

    def _where(self, type: str | None, source: str | None, level: str | None,
               since: float | None, until: float | None,
               acknowledged: bool | None) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        args: list[Any] = []
        for col, val in (("type", type), ("source", source), ("level", level)):
            if val:
                clauses.append(f"{col} = ?")
                args.append(val)
        if since is not None:
            clauses.append("ts >= ?")
            args.append(since)
        if until is not None:
            clauses.append("ts <= ?")
            args.append(until)
        if acknowledged is not None:
            clauses.append("acknowledged = ?")
            args.append(int(acknowledged))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", args

    def list(self, *, type: str | None = None, source: str | None = None,
             level: str | None = None, since: float | None = None, until: float | None = None,
             acknowledged: bool | None = None, limit: int = 50,
             offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        where, args = self._where(type, source, level, since, until, acknowledged)
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM events{where}", args).fetchone()[0]
            rows = self._db.execute(
                f"SELECT * FROM events{where} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
                [*args, max(1, min(limit, 1000)), max(0, offset)],
            ).fetchall()
        return [self._row(r) for r in rows], int(total)

    def get(self, event_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._row(row) if row else None

    def image_path(self, event_id: int) -> Path | None:
        with self._lock:
            row = self._db.execute("SELECT snapshot FROM events WHERE id = ?",
                                   (event_id,)).fetchone()
        if not row or not row[0]:
            return None
        path = self.snap_dir / row[0]
        return path if path.is_file() else None

    def acknowledge(self, event_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE events SET acknowledged = 1, ack_ts = ? WHERE id = ?",
                (time.time(), event_id),
            )
            self._db.commit()
        return cur.rowcount > 0

    def stats(self, since: float | None = None) -> dict[str, Any]:
        where, args = self._where(None, None, None, since, None, None)
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM events{where}", args).fetchone()[0]
            by_type = dict(self._db.execute(
                f"SELECT type, COUNT(*) FROM events{where} GROUP BY type", args).fetchall())
            by_level = dict(self._db.execute(
                f"SELECT level, COUNT(*) FROM events{where} GROUP BY level", args).fetchall())
            by_source = dict(self._db.execute(
                f"SELECT source, COUNT(*) FROM events{where} GROUP BY source", args).fetchall())
            unack_where = (where + " AND" if where else " WHERE") + " acknowledged = 0"
            unack = self._db.execute(f"SELECT COUNT(*) FROM events{unack_where}",
                                     args).fetchone()[0]
            hours = self._db.execute(
                f"SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER), COUNT(*)"
                f" FROM events{where} GROUP BY 1", args).fetchall()
        by_hour = [0] * 24
        for h, n in hours:
            by_hour[int(h)] = int(n)
        return {"total": int(total), "unacknowledged": int(unack), "by_type": by_type,
                "by_level": by_level, "by_source": by_source, "by_hour": by_hour}

    def to_csv(self, **filters: Any) -> str:
        rows, _ = self.list(limit=1000, **filters)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "time", "source", "track_id", "type", "level", "message", "detail",
                    "acknowledged"])
        for r in rows:
            w.writerow([r["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                        r["source"], r["track_id"] if r["track_id"] is not None else "",
                        r["type"], r["level"], r["message"], r["detail"],
                        int(r["acknowledged"])])
        return buf.getvalue()
