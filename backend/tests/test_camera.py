import time

import numpy as np
import pytest

from echo_move.alerts import AlertHub
from echo_move.camera import CameraManager, parse_cameras
from echo_move.camera.worker import CameraWorker, is_file_source, mask_source
from echo_move.config import Settings
from echo_move.pipeline import StreamPipeline
from echo_move.scenarios import load_scenarios
from echo_move.storage import EventStore
from echo_move.storage.db import read_clip_frames
from echo_move.zones import foot_point, load_file_options, parse_options, point_in_polygon

FRAME = np.full((480, 640, 3), 128, np.uint8)
FRAME[::8] = 30  # some texture so IQA is not degenerate


class FakeDetector:
    available = True
    hands = None

    def __init__(self, kps):
        self.kps = kps

    def detect_raw(self, frame):
        return [self.kps], []


class FakeCapture:
    def __init__(self, frames=10**6, opened=True):
        self.frames, self.opened = frames, opened

    def isOpened(self):
        return self.opened

    def read(self):
        if self.frames <= 0:
            return False, None
        self.frames -= 1
        return True, FRAME.copy()

    def get(self, prop):
        return 0.0

    def set(self, prop, value):
        return True

    def release(self):
        pass


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_parse_cameras(tmp_path):
    f = tmp_path / "cams.json"
    f.write_text('[{"id": "kho", "source": "rtsp://u:p@10.0.0.5/s1"}]')
    cams = parse_cameras("cong=0, rtsp://host/live?channel=1", str(f))
    assert cams == {"kho": "rtsp://u:p@10.0.0.5/s1", "cong": 0,
                    "cam2": "rtsp://host/live?channel=1"}
    assert parse_cameras("") == {}


def test_source_helpers():
    assert mask_source("rtsp://admin:secret@10.0.0.5:554/s") == "rtsp://***@10.0.0.5:554/s"
    assert is_file_source("/videos/a.mp4") and not is_file_source("rtsp://x")
    assert not is_file_source(0)


def test_worker_processes_frames_and_raises_alerts(tmp_path):
    cfg = Settings(camera_fps=25, fall_confirm_s=0.3, alert_cooldown_s=60, demo_mode=True)
    store = EventStore(tmp_path)
    pipe = StreamPipeline("kho", FakeDetector(load_scenarios()["nga"]["kps"]), cfg,
                          AlertHub(store))
    w = CameraWorker("kho", "rtsp://cam", pipe, cfg, capture_factory=lambda s: FakeCapture())
    w.start()
    try:
        assert wait_for(lambda: store.list(type="FALL")[1] == 1)
    finally:
        w.stop()
    st = w.status()
    assert st["state"] == "stopped" and st["persons"] == 1 and st["source"] == "rtsp://cam"
    assert w.latest["camera"] == "kho" and w.latest["persons"][0]["id"] == 1
    assert w.latest_jpeg[:2] == b"\xff\xd8"
    event = store.list()[0][0]
    assert event["source"] == "kho" and event["has_image"]


def test_worker_records_event_clip(tmp_path):
    cfg = Settings(camera_fps=20, fall_confirm_s=0.3, alert_cooldown_s=60, demo_mode=True,
                   clip_pre_s=0.5, clip_post_s=0.5)
    store = EventStore(tmp_path)
    pipe = StreamPipeline("kho", FakeDetector(load_scenarios()["nga"]["kps"]), cfg,
                          AlertHub(store))
    w = CameraWorker("kho", "rtsp://cam", pipe, cfg, capture_factory=lambda s: FakeCapture())
    w.start()
    try:
        assert wait_for(lambda: store.list(type="FALL")[1] == 1 and store.list()[0][-1]["has_clip"])
    finally:
        w.stop()
    event = store.list(type="FALL")[0][0]
    mjpg, mp4 = store.clip_paths(event["id"])
    fps, frames = read_clip_frames(mjpg)
    assert len(frames) >= 4 and frames[0][:2] == b"\xff\xd8" and 1 <= fps <= 30
    assert mp4 is not None and mp4.stat().st_size > 0


def test_offline_alert_once_per_outage(tmp_path):
    cfg = Settings(offline_alert_s=30, demo_mode=True)
    store = EventStore(tmp_path)
    pipe = StreamPipeline("kho", FakeDetector([]), cfg, AlertHub(store))
    w = CameraWorker("kho", "rtsp://cam", pipe, cfg, capture_factory=lambda s: FakeCapture())
    w.state, w.error = "reconnecting", "cannot open"
    w._check_offline(100.0)
    w._check_offline(120.0)
    assert store.list(type="OFFLINE")[1] == 0
    w._check_offline(131.0)
    w._check_offline(200.0)
    events = store.list(type="OFFLINE")[0]
    assert len(events) == 1 and events[0]["source"] == "kho"
    assert "cannot open" in events[0]["detail"]
    w.state = "online"
    w._check_offline(201.0)
    w.state = "stalled"
    w._check_offline(300.0)
    w._check_offline(331.0)
    assert store.list(type="OFFLINE")[1] == 2
    pipe.engine.disabled = {"OFFLINE"}
    w.state = "online"
    w._check_offline(400.0)
    w.state = "reconnecting"
    w._check_offline(400.0)
    w._check_offline(500.0)
    assert store.list(type="OFFLINE")[1] == 2


def test_zone_geometry_and_parsing(tmp_path):
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert point_in_polygon((0.5, 0.5), square) and not point_in_polygon((1.5, 0.5), square)
    kps = [[0.5, 0.5, 0.9]] * 17
    assert foot_point(kps, None, 0.25) == (0.5, 0.5)
    assert foot_point([[0, 0, 0]] * 17, [0.2, 0.1, 0.4, 0.9], 0.25) == (0.30000000000000004, 0.9)
    with pytest.raises(ValueError):
        parse_options({"zones": [{"points": [[0, 0], [1, 1]]}]})
    f = tmp_path / "cams.json"
    f.write_text('[{"id": "kho", "source": "0", "zones": [{"name": "A", '
                 '"points": [[0,0],[1,0],[1,1]]}], "disabled_rules": ["CAMERA"]}]')
    opts = load_file_options(str(f))
    assert parse_options(opts["kho"]).disabled_rules == ["CAMERA"]


def test_zone_intrusion_raises_alert(tmp_path):
    cfg = Settings(demo_mode=True)
    store = EventStore(tmp_path)
    stand = load_scenarios()["an_toan"]["kps"]  # ankles at y≈0.87
    pipe = StreamPipeline("kho", FakeDetector(stand), cfg, AlertHub(store))
    pipe.configure(parse_options({"zones": [{"name": "Máy dập", "dwell_s": 0.5,
                                             "points": [[0, 0.7], [1, 0.7], [1, 1], [0, 1]]}],
                                  "disabled_rules": ["CAMERA"]}))
    out = [pipe.process(FRAME, i * 0.1) for i in range(10)]
    assert out[0]["persons"][0]["zones"][0]["name"] == "Máy dập"
    events = [a for o in out for a in o["alerts"]]
    assert [e["type"] for e in events] == ["ZONE"] and events[0]["detail"] == "Vùng: Máy dập"
    assert store.get(events[0]["id"])["has_image"]


def test_worker_reconnects_after_open_failure():
    cfg = Settings(camera_fps=25, demo_mode=True)
    caps = iter([FakeCapture(opened=False), FakeCapture()])
    pipe = StreamPipeline("x", FakeDetector([[0, 0, 0]] * 17), cfg)
    w = CameraWorker("x", "rtsp://cam", pipe, cfg, capture_factory=lambda s: next(caps))
    w.start()
    try:
        assert wait_for(lambda: w.state == "online" and w.result_seq > 0, timeout=4)
    finally:
        w.stop()
    assert w.reconnects == 1


def test_manager_with_real_video_file(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "clip.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (320, 240))
    for i in range(20):
        img = np.full((240, 320, 3), i * 10, np.uint8)
        cv2.circle(img, (160, 120), 40, (255, 255, 255), -1)
        vw.write(img)
    vw.release()
    cfg = Settings(camera_fps=20, demo_mode=True)
    from echo_move.pose.detector import PoseDetector

    mgr = CameraManager(cfg, PoseDetector(cfg), None, sources={"file": str(path)})
    mgr.start()
    try:
        w = mgr.get("file")
        assert wait_for(lambda: w.result_seq > 25)  # > 20 frames → the file looped
    finally:
        mgr.stop()
    assert mgr.statuses()[0]["quality"] is not None and mgr.get("nope") is None
