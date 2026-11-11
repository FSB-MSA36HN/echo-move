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
