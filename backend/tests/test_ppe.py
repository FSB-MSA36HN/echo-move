import numpy as np

from echo_move.config import Settings
from echo_move.pipeline import StreamPipeline
from echo_move.pose.ppe import PPEDetection, assign_ppe, normalize_label, regions
from echo_move.scenarios import load_scenarios

STAND = load_scenarios()["an_toan"]["kps"]
VIS = 0.25


def shifted(kps, dx):
    return [[x + dx, y, c] for x, y, c in kps]


def inside(box, frac=0.6):
    """A detection box centred in ``box`` covering ``frac`` of its size."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    hw, hh = (box[2] - box[0]) * frac / 2, (box[3] - box[1]) * frac / 2
    return (cx - hw, cy - hh, cx + hw, cy + hh)


def test_normalize_label_handles_common_datasets():
    assert normalize_label("Hardhat") == ("helmet", True)
    assert normalize_label("NO-Hardhat") == ("helmet", False)
    assert normalize_label("head") == ("helmet", False)
    assert normalize_label("Safety Vest") == ("vest", True)
    assert normalize_label("NO-Safety Vest") == ("vest", False)
    assert normalize_label("Person") is None and normalize_label("machinery") is None


def test_assign_ppe_to_the_right_person():
    left, right = shifted(STAND, -0.25), shifted(STAND, 0.25)
    rl, rr = regions(left, VIS), regions(right, VIS)
    assert rl["helmet"] and rl["vest"] and rl["helmet"][3] < rl["vest"][3]
    dets = [PPEDetection("helmet", True, 0.9, inside(rl["helmet"])),
            PPEDetection("vest", True, 0.8, inside(rl["vest"])),
            PPEDetection("helmet", False, 0.7, inside(rr["helmet"]))]
    a, b = assign_ppe([left, right], dets, VIS)
    assert a == {"helmet": True, "vest": True}
    assert b == {"helmet": False, "vest": False}  # torso visible, no vest found
    headless = [[x, y, 0.0 if i < 7 else c] for i, (x, y, c) in enumerate(STAND)]
    assert assign_ppe([headless], [], VIS)[0] == {"helmet": None, "vest": None}
    far = PPEDetection("helmet", True, 0.9, (0.0, 0.0, 0.02, 0.02))
    assert assign_ppe([left], [far], VIS)[0]["helmet"] is False


class PPEFakeDetector:
    available = True

    def __init__(self, kps, dets):
        self.kps, self.dets = kps, dets

    def detect_raw(self, frame):
        return [self.kps], []

    def detect_ppe(self, frame):
        return self.dets


def test_pipeline_raises_ppe_alert_for_missing_helmet():
    reg = regions(STAND, VIS)
    dets = [PPEDetection("vest", True, 0.9, inside(reg["vest"]))]
    cfg = Settings(demo_mode=True, ppe_confirm_s=1.0, ppe_required=("helmet", "vest"))
    pipe = StreamPipeline("kho", PPEFakeDetector(STAND, dets), cfg)
    frame = np.full((480, 640, 3), 128, np.uint8)
    alerts = []
    for i in range(15):
        out = pipe.process(frame, t=i * 0.1)
        alerts += out["alerts"]
    assert out["persons"][0]["ppe"] == {"helmet": False, "vest": True}
    ppe = [a for a in alerts if a["type"] == "PPE"]
    assert len(ppe) == 1 and "mũ bảo hộ" in ppe[0]["detail"]
    assert "áo" not in ppe[0]["detail"]


def test_pipeline_skips_ppe_without_model():
    class NoPPE(PPEFakeDetector):
        def detect_ppe(self, frame):
            return None

    pipe = StreamPipeline("kho", NoPPE(STAND, []), Settings(demo_mode=True))
    out = pipe.process(np.full((480, 640, 3), 128, np.uint8), t=0.0)
    assert "ppe" not in out["persons"][0]
