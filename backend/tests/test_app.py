import base64
import json

import pytest
from fastapi.testclient import TestClient

from echo_move.app import create_app
from echo_move.config import Settings
from echo_move.matlab_bridge import MatlabBridge
from echo_move.pipeline import StreamPipeline
from echo_move.pose.detector import PoseDetector
from echo_move.scenarios import DemoGenerator

JPEG = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_DEMO_MODE", "1")
    monkeypatch.setenv("ECHO_MATLAB_DIR", str(tmp_path))
    monkeypatch.setenv("ECHO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ECHO_CAMERAS", "")
    monkeypatch.setenv("ECHO_TELEGRAM_TOKEN", "")
    monkeypatch.setenv("ECHO_WEBHOOK_URL", "")
    with TestClient(create_app(Settings())) as c:
        yield c


def post_event(client, **kw):
    body = {"type": "FALL", "detail": "Nằm trên sàn", "track_id": 1, **kw}
    r = client.post("/api/events", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["demo_mode"] is True
    assert body["cameras"] == 0 and body["events_db"] is True and body["notify"] == []


def test_matlab_iqa_missing(client):
    assert client.get("/matlab_iqa").json() == {"available": False}


def test_matlab_iqa_present(client, tmp_path):
    (tmp_path / "x_iqa.json").write_text(json.dumps({"summary": {"overall": 77}}))
    body = client.get("/matlab_iqa").json()
    assert body["available"] and body["overall"] == 77


def test_ws_demo_frame(client):
    with client.websocket_connect("/ws/pose") as ws:
        ws.send_text("{}")
        msg = json.loads(ws.receive_text())
    assert msg["mode"] == "DEMO" and "persons" in msg and msg["alerts"] == []


def test_bridge_tolerates_partial_write(tmp_path):
    (tmp_path / "a_iqa.json").write_text("{not json")
    assert MatlabBridge(tmp_path).read() is None


def test_events_crud_csv_stats(client):
    img = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    e1 = post_event(client, image=img, source="browser")
    post_event(client, type="POSTURE", detail="Cúi 63°", source="kho")
    assert e1["level"] == "CRITICAL" and e1["has_image"]

    page = client.get("/api/events", params={"limit": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert client.get("/api/events", params={"type": "FALL"}).json()["total"] == 1
    assert client.get("/api/events", params={"source": "kho"}).json()["total"] == 1

    assert client.get(f"/api/events/{e1['id']}/image").content == JPEG
    assert client.get("/api/events/999").status_code == 404
    assert client.post(f"/api/events/{e1['id']}/ack").json()["acknowledged"] is True
    assert client.post("/api/events/999/ack").status_code == 404

    stats = client.get("/api/stats", params={"hours": 1}).json()
    assert stats["total"] == 2 and stats["unacknowledged"] == 1
    assert stats["by_type"] == {"FALL": 1, "POSTURE": 1}

    csv = client.get("/api/events.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv.headers["content-disposition"]
    assert len(csv.text.strip().splitlines()) == 3


def test_event_clip_and_false_alarm_endpoints(client):
    import cv2
    import numpy as np

    ev = post_event(client, type="MANDOWN", detail="Nằm bất động 12 s")
    assert ev["level"] == "CRITICAL" and ev["has_clip"] is False
    assert client.get(f"/api/events/{ev['id']}/clip").status_code == 404
    jpeg = cv2.imencode(".jpg", np.zeros((48, 64, 3), np.uint8))[1].tobytes()
    client.app.state.store.save_clip(ev["id"], [jpeg] * 3, 30.0)
    mp4 = client.get(f"/api/events/{ev['id']}/clip.mp4")
    assert mp4.status_code == 200 and mp4.headers["content-type"] == "video/mp4"
    stream = client.get(f"/api/events/{ev['id']}/clip")
    assert stream.headers["content-type"].startswith("multipart/x-mixed-replace")
    assert stream.content.count(b"--frame") == 3
    assert client.post(f"/api/events/{ev['id']}/false-alarm").json()["false_alarm"] is True
    got = client.get(f"/api/events/{ev['id']}").json()
    assert got["false_alarm"] and got["acknowledged"] and got["has_clip"]
    assert client.post("/api/events/999/false-alarm").status_code == 404


def test_event_validation(client):
    assert client.post("/api/events", json={"type": "NOPE"}).status_code == 422
    assert client.post("/api/events", json={"type": "FALL", "detail": "x" * 500}).status_code == 422


def test_ws_events_pushes_new_alerts(client):
    with client.websocket_connect("/ws/events") as ws:
        post_event(client)
        msg = json.loads(ws.receive_text())
    assert msg["type"] == "FALL" and msg["id"] >= 1


def test_cameras_empty_and_404(client):
    assert client.get("/api/cameras").json() == []
    assert client.get("/api/cameras/x/snapshot.jpg").status_code == 404
    with client.websocket_connect("/ws/camera/x") as ws:
        assert "error" in json.loads(ws.receive_text())


def test_camera_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ECHO_DEMO_MODE", "1")
    monkeypatch.setenv("ECHO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ECHO_CAMERAS", f"kho={tmp_path / 'missing.mp4'}")
    zone = {"name": "Máy dập", "points": [[0, 0.5], [0.5, 0.5], [0.5, 1]], "dwell_s": 2}
    with TestClient(create_app(Settings())) as c:
        assert c.get("/api/cameras/kho/config").json()["zones"] == []
        r = c.put("/api/cameras/kho/config", json={"zones": [zone], "disabled_rules": ["posture"]})
        assert r.status_code == 200 and r.json()["disabled_rules"] == ["POSTURE"]
        cam = c.get("/api/cameras").json()[0]
        assert cam["zones"][0]["name"] == "Máy dập" and cam["disabled_rules"] == ["POSTURE"]
        bad = {"zones": [{"points": [[0, 0], [2, 2], [0, 1]]}]}
        assert c.put("/api/cameras/kho/config", json=bad).status_code == 422
        assert c.put("/api/cameras/kho/config",
                     json={"disabled_rules": ["NOPE"]}).status_code == 422
        assert c.put("/api/cameras/x/config", json={}).status_code == 404
    saved = json.loads((tmp_path / "camera_config.json").read_text())
    assert saved["kho"]["zones"][0]["dwell_s"] == 2.0
    with TestClient(create_app(Settings())) as c:  # survives a restart
        assert c.get("/api/cameras/kho/config").json()["disabled_rules"] == ["POSTURE"]


def test_web_ui_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200 and "ECHO" in r.text
    assert client.get("/js/human3d.js").status_code == 200


def test_demo_observe_raises_confirmed_alerts():
    cfg = Settings(demo_mode=True, fall_confirm_s=1.0, posture_confirm_s=1.0)
    pipe = StreamPipeline("demo", PoseDetector(cfg), cfg)
    gen = DemoGenerator(20)
    seen = set()
    for i in range(20 * 30):  # 30 s of demo at 20 fps covers every scenario
        payload = gen.next_frame(None)
        seen |= {a["type"] for a in pipe.observe(payload, i / 20)["alerts"]}
    assert {"FALL", "POSTURE"} <= seen
