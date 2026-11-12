import json

from echo_move.alerts import Alert, AlertEngine, AlertHub
from echo_move.config import Settings
from echo_move.notify import Notifier, format_message
from echo_move.storage import EventStore

KPS = [[0.5, 0.5, 0.9]] * 17


def person(tech, tid=1, hip_y=0.5, bbox=(0.4, 0.2, 0.6, 0.8)):
    kps = [list(k) for k in KPS]
    kps[11] = [0.48, hip_y, 0.9]
    kps[12] = [0.52, hip_y, 0.9]
    return {"id": tid, "keypoints": kps, "bbox": list(bbox),
            "safety": {"technique": tech, "detail": "x", "spine_deg": 80.0}}


def run(engine, frames, dt=0.1, t0=0.0):
    out, t = [], t0
    for persons, quality in frames:
        out += engine.update(persons, quality, t)
        t += dt
    return out, t


def cfg(**kw):
    base = {"fall_confirm_s": 1.5, "posture_confirm_s": 3.0, "quality_confirm_s": 5.0,
            "alert_cooldown_s": 30.0}
    return Settings(**{**base, **kw})


def test_fall_confirmed_only_after_persisting():
    eng = AlertEngine(cfg(), "cam")
    short, t = run(eng, [([person("FALL")], None)] * 10)  # 0.9 s
    assert short == []
    eng = AlertEngine(cfg(), "cam")
    alerts, _ = run(eng, [([person("FALL")], None)] * 20)  # 1.9 s
    assert [a.type for a in alerts] == ["FALL"]
    assert alerts[0].level == "CRITICAL" and alerts[0].track_id == 1
    assert alerts[0].data["spine_deg"] == 80.0


def test_brief_dropout_does_not_reset_episode():
    eng = AlertEngine(cfg(), "cam")
    frames = ([([person("FALL")], None)] * 8 + [([person("NONE")], None)] * 2
              + [([person("FALL")], None)] * 8)
    alerts, _ = run(eng, frames)
    assert [a.type for a in alerts] == ["FALL"]


def test_long_recovery_resets_episode():
    eng = AlertEngine(cfg(), "cam")
    frames = ([([person("FALL")], None)] * 12 + [([person("NONE")], None)] * 10
              + [([person("FALL")], None)] * 12)
    alerts, _ = run(eng, frames)
    assert alerts == []


def test_cooldown_suppresses_repeats_then_allows():
    eng = AlertEngine(cfg(alert_cooldown_s=10), "cam")
    fall, ok = ([person("FALL")], None), ([person("NONE")], None)
    a1, t = run(eng, [fall] * 20 + [ok] * 10 + [fall] * 20)  # second episode within 10 s
    assert len(a1) == 1
    a2, _ = run(eng, [ok] * 10 + [fall] * 20, t0=t + 10)
    assert len(a2) == 1


def test_rapid_hip_drop_halves_fall_confirmation():
    eng = AlertEngine(cfg(), "cam")
    frames = [([person("NONE", hip_y=0.45)], None)] * 3
    frames += [([person("FALL", hip_y=0.85)], None)] * 9  # dropped 0.4 of a 0.6-tall body
    alerts, _ = run(eng, frames)
    assert [a.type for a in alerts] == ["FALL"]
    assert alerts[0].detail == "Ngã đột ngột" and alerts[0].data["rapid_drop"] is True


def test_mandown_after_lying_still_then_recovered():
    eng = AlertEngine(cfg(mandown_s=3.0), "cam")
    alerts, t = run(eng, [([person("FALL")], None)] * 50)  # 4.9 s lying, not moving
    assert [a.type for a in alerts] == ["FALL", "MANDOWN"]
    down = alerts[1]
    assert down.level == "CRITICAL" and down.data["motionless"] is True
    assert down.detail.startswith("Nằm bất động")
    up, _ = run(eng, [([person("NONE")], None)] * 25, t0=t)
    assert [a.type for a in up] == ["RECOVERED"] and up[0].level == "INFO"


def test_mandown_reports_movement_and_needs_persistence():
    eng = AlertEngine(cfg(mandown_s=3.0), "cam")
    frames = [([person("FALL", hip_y=0.8 + 0.05 * (i % 2))], None) for i in range(50)]
    alerts, _ = run(eng, frames)
    down = next(a for a in alerts if a.type == "MANDOWN")
    assert down.data["motionless"] is False and "còn cử động" in down.detail
    eng = AlertEngine(cfg(mandown_s=3.0), "cam")
    short, _ = run(eng, [([person("FALL")], None)] * 30 + [([person("NONE")], None)] * 30)
    assert [a.type for a in short] == ["FALL", "RECOVERED"]


def test_no_recovered_without_reported_fall():
    eng = AlertEngine(cfg(), "cam")
    alerts, _ = run(eng, [([person("NONE")], None)] * 40)
    assert alerts == []


def test_posture_and_camera_alerts():
    eng = AlertEngine(cfg(), "cam")
    alerts, _ = run(eng, [([person("IMPROPER")], {"overall": 20.0})] * 55)
    assert sorted(a.type for a in alerts) == ["CAMERA", "POSTURE"]
    cam = next(a for a in alerts if a.type == "CAMERA")
    assert cam.track_id is None and cam.detail.startswith("IQA 20")


def test_tracks_are_independent():
    eng = AlertEngine(cfg(), "cam")
    alerts, _ = run(eng, [([person("FALL", 1), person("FALL", 2)], None)] * 20)
    assert sorted(a.track_id for a in alerts) == [1, 2]


def test_store_roundtrip(tmp_path):
    store = EventStore(tmp_path)
    a = store.add(Alert("FALL", "CRITICAL", "kho", "Ngã", "detail", 3, 1000.0,
                        {"spine_deg": 81}), b"\xff\xd8jpeg")
    store.add(Alert("POSTURE", "WARNING", "cong", "Cúi", "", 4, 2000.0))
    assert a["id"] == 1 and a["has_image"] and a["data"] == {"spine_deg": 81}
    items, total = store.list()
    assert total == 2 and items[0]["type"] == "POSTURE"  # newest first
    assert store.list(type="FALL")[1] == 1
    assert store.list(since=1500)[1] == 1
    assert store.image_path(1).read_bytes() == b"\xff\xd8jpeg"
    assert store.image_path(2) is None
    assert store.acknowledge(1) and not store.acknowledge(99)
    assert store.get(1)["acknowledged"] is True
    s = store.stats()
    assert s["total"] == 2 and s["unacknowledged"] == 1
    assert s["by_type"] == {"FALL": 1, "POSTURE": 1} and sum(s["by_hour"]) == 2
    csv = store.to_csv()
    assert csv.splitlines()[0].startswith("id,time,source") and "kho" in csv
    store.close()


def test_hub_works_without_store_or_notifier():
    event = AlertHub().publish(Alert("FALL", "CRITICAL", "x", "m"))
    assert event["type"] == "FALL" and "id" not in event


class FakeOpener:
    def __init__(self, fail=0):
        self.requests, self.fail = [], fail

    def __call__(self, req, timeout):
        if self.fail:
            self.fail -= 1
            raise OSError("network down")
        self.requests.append(req)
        return b"{}"


def test_notifier_disabled_without_config():
    n = Notifier(Settings(telegram_token="", telegram_chat_id="", webhook_url=""))
    assert not n.enabled and n.channels() == [] and n.send({"type": "FALL"}) is False


def test_notifier_telegram_photo_and_webhook():
    opener = FakeOpener()
    n = Notifier(Settings(telegram_token="T", telegram_chat_id="42",
                          webhook_url="http://hook.local/x"), opener=opener)
    event = {"id": 1, "type": "FALL", "level": "CRITICAL", "message": "Ngã",
             "source": "kho", "track_id": 2, "detail": "d", "ts": 1000.0}
    n.deliver(event, b"\xff\xd8jpeg")
    urls = [r.full_url for r in opener.requests]
    assert urls == ["https://api.telegram.org/botT/sendPhoto", "http://hook.local/x"]
    assert b'name="chat_id"\r\n\r\n42' in opener.requests[0].data
    assert b"\xff\xd8jpeg" in opener.requests[0].data
    hook = json.loads(opener.requests[1].data)
    assert hook["event"]["id"] == 1 and "người #2" in hook["text"]
    assert n.sent == 2 and n.failed == 0


def test_notifier_retries_then_counts_failure(monkeypatch):
    monkeypatch.setattr("echo_move.notify.time.sleep", lambda s: None)
    opener = FakeOpener(fail=2)
    n = Notifier(Settings(webhook_url="http://hook.local/x"), opener=opener)
    n.deliver({"type": "FALL", "ts": 0}, None)
    assert n.sent == 1 and len(opener.requests) == 1
    n = Notifier(Settings(webhook_url="http://hook.local/x"), opener=FakeOpener(fail=5))
    n.deliver({"type": "FALL", "ts": 0}, None)
    assert n.failed == 1


def test_notifier_video_zalo_and_escalation_chat():
    opener = FakeOpener()
    n = Notifier(Settings(telegram_token="T", telegram_chat_id="42", escalate_chat_id="99",
                          zalo_token="Z", zalo_user_id="u1", webhook_url=""), opener=opener)
    assert n.channels() == ["telegram", "zalo"]
    event = {"id": 7, "type": "FALL", "level": "CRITICAL", "message": "Ngã", "source": "kho",
             "ts": 0, "escalation": True}
    n.deliver(event, None)
    tg, zalo = opener.requests
    assert json.loads(tg.data)["chat_id"] == "99" and "LEO THANG" in json.loads(tg.data)["text"]
    assert zalo.full_url.startswith("https://openapi.zalo.me/")
    assert zalo.get_header("Access_token") == "Z"
    assert json.loads(zalo.data)["recipient"]["user_id"] == "u1"
    n._telegram_video({"id": 7, "message": "Ngã", "source": "kho"}, b"mp4data")
    vid = opener.requests[-1]
    assert vid.full_url.endswith("/sendVideo") and b"video/mp4" in vid.data
    assert b'name="chat_id"\r\n\r\n42' in vid.data
    assert Notifier(Settings(telegram_token="", telegram_chat_id="", webhook_url="x")
                    ).send_video({}, b"") is False


def test_store_migrates_clips_false_alarm_and_purge(tmp_path):
    import sqlite3

    db = sqlite3.connect(tmp_path / "echo.db")  # a v21 database without the new columns
    db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,"
               " source TEXT NOT NULL, track_id INTEGER, type TEXT NOT NULL, level TEXT NOT NULL,"
               " message TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', snapshot TEXT,"
               " acknowledged INTEGER NOT NULL DEFAULT 0, ack_ts REAL,"
               " data TEXT NOT NULL DEFAULT '{}')")
    db.execute("INSERT INTO events (ts, source, type, level, message) VALUES"
               " (100, 'old', 'FALL', 'CRITICAL', 'x')")
    db.commit()
    db.close()
    store = EventStore(tmp_path)
    assert store.get(1)["has_clip"] is False and store.get(1)["false_alarm"] is False
    new = store.add(Alert("FALL", "CRITICAL", "kho", "Ngã", "", 1, 5000.0), b"\xff\xd8x")
    import cv2
    import numpy as np

    jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))[1].tobytes()
    assert store.save_clip(new["id"], [jpeg] * 5, 10.0) is not None
    assert store.get(new["id"])["has_clip"] and all(store.clip_paths(new["id"]))
    assert store.acknowledge(new["id"], false_alarm=True)
    assert store.stats()["false_alarms"] == {"FALL": 1}
    assert [e["id"] for e in store.due_escalation(10_000)] == [1]
    store.mark_escalated(1)
    assert store.due_escalation(10_000) == []
    assert store.purge(6000) == 2 and store.list()[1] == 0
    assert not any(store.clip_dir.iterdir()) and not any(store.snap_dir.iterdir())
    store.close()


def test_maintenance_escalates_and_purges(tmp_path):
    from echo_move.maintenance import Maintenance

    class Recorder:
        def __init__(self):
            self.sent = []

        def send(self, event, jpeg=None):
            self.sent.append(event)

    store = EventStore(tmp_path)
    old = store.add(Alert("FALL", "CRITICAL", "kho", "Ngã", "", 1, 1000.0))
    store.add(Alert("POSTURE", "WARNING", "kho", "Cúi", "", 1, 1000.0))
    fresh = store.add(Alert("FALL", "CRITICAL", "kho", "Ngã", "", 2, 1250.0))
    notifier = Recorder()
    off = Maintenance(Settings(escalate_min=0, retention_days=0), store, notifier)
    assert off.run_once(2000.0) == {"purged": 0, "escalated": 0}
    m = Maintenance(Settings(escalate_min=5, retention_days=1), store, notifier)
    assert m.run_once(1310.0) == {"purged": 0, "escalated": 1}
    assert notifier.sent[0]["id"] == old["id"] and notifier.sent[0]["escalation"]
    assert m.run_once(1320.0)["escalated"] == 0  # only once per event
    store.acknowledge(fresh["id"])
    assert m.run_once(2000.0)["escalated"] == 0  # acknowledged events are never escalated
    assert m.run_once(1100.0 + 86400)["purged"] == 2
    assert [e["id"] for e in store.list()[0]] == [fresh["id"]]
    assert m.run_once(1100.0 + 86400 + 600)["purged"] == 0  # purge runs at most hourly
    store.close()


def test_format_message_mentions_camera_and_level():
    msg = format_message({"level": "CRITICAL", "message": "Ngã", "source": "kho", "ts": 0})
    assert "CRITICAL" in msg and "kho" in msg
