"""SQLite event log with JPEG snapshots on disk (stdlib only, safe across threads)."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import struct
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
# Columns added after v21; applied with ALTER TABLE on existing databases.
MIGRATIONS = {
    "clip": "ALTER TABLE events ADD COLUMN clip TEXT",
    "false_alarm": "ALTER TABLE events ADD COLUMN false_alarm INTEGER NOT NULL DEFAULT 0",
    "escalated": "ALTER TABLE events ADD COLUMN escalated INTEGER NOT NULL DEFAULT 0",
}

COLUMNS = ("id", "ts", "source", "track_id", "type", "level", "message", "detail",
           "snapshot", "acknowledged", "ack_ts", "data", "clip", "false_alarm", "escalated")
CLIP_MAGIC = b"ECLP"


def write_clip_frames(path: Path, frames: list[bytes], fps: float) -> None:
    """Length-prefixed JPEG sequence, replayed as MJPEG by the API."""
    with open(path, "wb") as f:
        f.write(CLIP_MAGIC + struct.pack(">f", fps))
        for jpeg in frames:
            f.write(struct.pack(">I", len(jpeg)) + jpeg)


def read_clip_frames(path: Path) -> tuple[float, list[bytes]]:
    data = path.read_bytes()
    if data[:4] != CLIP_MAGIC:
        raise ValueError("not a clip file")
    fps = struct.unpack(">f", data[4:8])[0]
    frames, i = [], 8
    while i + 4 <= len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        frames.append(data[i + 4:i + 4 + n])
        i += 4 + n
    return fps, frames


def encode_mp4(frames: list[bytes], fps: float, path: Path) -> bool:
    import cv2
    import numpy as np

    decoded = (cv2.imdecode(np.frombuffer(j, np.uint8), cv2.IMREAD_COLOR) for j in frames)
    imgs: list[np.ndarray] = [im for im in decoded if im is not None]
    if not imgs:
        return False
    h, w = imgs[0].shape[:2]
    fourcc: Any = cv2.VideoWriter_fourcc  # type: ignore[attr-defined]
    for codec in ("avc1", "mp4v"):  # H.264 plays in browsers/Telegram; mp4v always encodes
        vw = cv2.VideoWriter(str(path), fourcc(*codec), fps, (w, h))
        if not vw.isOpened():
            vw.release()
            continue
        for im in imgs:
            vw.write(im if im.shape[:2] == (h, w) else cv2.resize(im, (w, h)))
        vw.release()
        if path.is_file() and path.stat().st_size > 0:
            return True
    return False


Rows = list[dict[str, Any]]
Frames = list[bytes]


class EventStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.snap_dir = self.data_dir / "snapshots"
        self.snap_dir.mkdir(parents=True, exist_ok=True)
        self.clip_dir = self.data_dir / "clips"
        self.clip_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "echo.db"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)
            have = {r[1] for r in self._db.execute("PRAGMA table_info(events)")}
            for col, sql in MIGRATIONS.items():
                if col not in have:
                    self._db.execute(sql)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["data"] = json.loads(d.get("data") or "{}")
        d["acknowledged"] = bool(d["acknowledged"])
        d["false_alarm"] = bool(d.get("false_alarm"))
        d["escalated"] = bool(d.get("escalated"))
        d["has_image"] = bool(d.pop("snapshot", None))
        d["has_clip"] = bool(d.pop("clip", None))
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

    def acknowledge(self, event_id: int, false_alarm: bool = False) -> bool:
        with self._lock:
            cur = self._db.execute(
                "UPDATE events SET acknowledged = 1, ack_ts = ?, false_alarm = ? WHERE id = ?",
                (time.time(), int(false_alarm), event_id),
            )
            self._db.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ clips
    def save_clip(self, event_id: int, frames: Frames, fps: float) -> Path | None:
        """Store the pre/post-event frames; returns the MP4 path (None if encoding failed)."""
        if not frames:
            return None
        name = f"{event_id:06d}"
        write_clip_frames(self.clip_dir / f"{name}.mjpg", frames, fps)
        mp4 = self.clip_dir / f"{name}.mp4"
        ok = encode_mp4(frames, fps, mp4)
        with self._lock:
            self._db.execute("UPDATE events SET clip = ? WHERE id = ?", (name, event_id))
            self._db.commit()
        return mp4 if ok else None

    def clip_paths(self, event_id: int) -> tuple[Path | None, Path | None]:
        with self._lock:
            row = self._db.execute("SELECT clip FROM events WHERE id = ?",
                                   (event_id,)).fetchone()
        if not row or not row[0]:
            return None, None
        mjpg, mp4 = self.clip_dir / f"{row[0]}.mjpg", self.clip_dir / f"{row[0]}.mp4"
        return (mjpg if mjpg.is_file() else None), (mp4 if mp4.is_file() else None)

    # ------------------------------------------------------------------ maintenance
    def due_escalation(self, older_than: float) -> Rows:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM events WHERE level = 'CRITICAL' AND acknowledged = 0"
                " AND escalated = 0 AND ts <= ? ORDER BY ts", (older_than,)).fetchall()
        return [self._row(r) for r in rows]

    def mark_escalated(self, event_id: int) -> None:
        with self._lock:
            self._db.execute("UPDATE events SET escalated = 1 WHERE id = ?", (event_id,))
            self._db.commit()

    def purge(self, before: float) -> int:
        """Delete events older than ``before`` together with their snapshot and clip files."""
        with self._lock:
            rows = self._db.execute("SELECT snapshot, clip FROM events WHERE ts < ?",
                                    (before,)).fetchall()
            cur = self._db.execute("DELETE FROM events WHERE ts < ?", (before,))
            self._db.commit()
        for snap, clip in rows:
            files = [self.snap_dir / snap] if snap else []
            if clip:
                files += [self.clip_dir / f"{clip}.mjpg", self.clip_dir / f"{clip}.mp4"]
            for f in files:
                f.unlink(missing_ok=True)
        return int(cur.rowcount)

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
            fa_where = (where + " AND" if where else " WHERE") + " false_alarm = 1"
            false_alarms = dict(self._db.execute(
                f"SELECT type, COUNT(*) FROM events{fa_where} GROUP BY type", args).fetchall())
            hours = self._db.execute(
                f"SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER), COUNT(*)"
                f" FROM events{where} GROUP BY 1", args).fetchall()
        by_hour = [0] * 24
        for h, n in hours:
            by_hour[int(h)] = int(n)
        return {"total": int(total), "unacknowledged": int(unack), "by_type": by_type,
                "by_level": by_level, "by_source": by_source, "by_hour": by_hour,
                "false_alarms": false_alarms}

    def to_csv(self, **filters: Any) -> str:
        rows, _ = self.list(limit=1000, **filters)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "time", "source", "track_id", "type", "level", "message", "detail",
                    "acknowledged", "false_alarm"])
        for r in rows:
            w.writerow([r["id"], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["ts"])),
                        r["source"], r["track_id"] if r["track_id"] is not None else "",
                        r["type"], r["level"], r["message"], r["detail"],
                        int(r["acknowledged"]), int(r["false_alarm"])])
        return buf.getvalue()
