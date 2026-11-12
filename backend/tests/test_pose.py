from echo_move.config import Settings
from echo_move.pose.classifier import classify_posture
from echo_move.pose.fall import FallAnalyzer
from echo_move.pose.filters import KeypointSmoother, OneEuro
from echo_move.pose.tracker import PoseTracker, iou, keypoint_bbox
from echo_move.scenarios import load_scenarios

CFG = Settings()
ASPECT = 4 / 3  # scenarios are authored for a 4:3 webcam frame


def shifted(kps, dx=0.0, dy=0.0):
    return [[x + dx, y + dy, c] for x, y, c in kps]


def test_scenarios_classified_as_expected():
    sc = load_scenarios()
    expected = {"an_toan": "NONE", "nang_dung": "PROPER_LIFT", "cui_sai": "IMPROPER", "nga": "FALL"}
    for name, technique in expected.items():
        assert classify_posture(sc[name]["kps"], CFG, ASPECT)["technique"] == technique, name


def test_low_visibility_is_safe():
    kps = [[0.5, 0.5, 0.0]] * 17
    assert classify_posture(kps, CFG, ASPECT)["detail"] == "Không đủ điểm"


def test_fall_needs_wide_body_not_just_tilted_spine():
    # Same fallen pose squeezed horizontally (tall, narrow box) is not a fall.
    fall = load_scenarios()["nga"]["kps"]
    narrow = [[0.5 + (x - 0.5) * 0.15, y, c] for x, y, c in fall]
    assert classify_posture(fall, CFG, ASPECT)["technique"] == "FALL"
    assert classify_posture(narrow, CFG, ASPECT)["technique"] != "FALL"


def _stand_then(analyzer, final, frames=8):
    stand = load_scenarios()["an_toan"]["kps"]
    for i in range(frames):
        analyzer.refine(1, classify_posture(stand, CFG, ASPECT), i * 0.1)
    return analyzer.refine(1, classify_posture(final, CFG, ASPECT), frames * 0.1)


def test_fall_towards_camera_needs_standing_baseline():
    stand = load_scenarios()["an_toan"]["kps"]
    # Torso stays vertical in the image (foreshortened) but the body collapsed to 30 % of
    # its height near the floor with the head below the hips.
    towards = [[x, 0.95 - (y - 0.12) * 0.3, c] for x, y, c in stand]
    single = classify_posture(towards, CFG, ASPECT)
    assert single["technique"] != "FALL" and single["signals"]["head_low"] is True
    out = _stand_then(FallAnalyzer(CFG), towards)
    assert out["technique"] == "FALL" and out["signals"]["collapsed"] is True
    legacy = Settings(fall_multisignal=False)
    assert FallAnalyzer(legacy).refine(1, classify_posture(towards, legacy, ASPECT),
                                       0)["technique"] != "FALL"


def test_sitting_down_is_not_a_fall():
    stand = load_scenarios()["an_toan"]["kps"]
    # Shorter body near the floor, head still well above the hips.
    sit = [[x, 0.6 + (y - 0.12) * 0.4, c] for x, y, c in stand]
    out = _stand_then(FallAnalyzer(CFG), sit)
    assert out["signals"]["collapsed"] is True and out["technique"] != "FALL"


def test_reba_scores_bending_higher_than_standing():
    sc = load_scenarios()
    stand = classify_posture(sc["an_toan"]["kps"], CFG, ASPECT)["reba"]
    bend = classify_posture(sc["cui_sai"]["kps"], CFG, ASPECT)["reba"]
    assert 1 <= stand <= 3 and bend > stand


def test_one_euro_smooths_jitter():
    f = OneEuro()
    outs = [f(v, i * 0.05) for i, v in enumerate([0.5, 0.52, 0.48, 0.51, 0.49])]
    assert max(outs) - min(outs) < 0.04


def test_smoother_resets_after_gap():
    s = KeypointSmoother()
    kps = [[0.1, 0.1, 0.9]] * 17
    s.apply(kps, 0.0)
    out = s.apply([[0.9, 0.9, 0.9]] * 17, 5.0)  # >1 s gap → reset → passthrough
    assert out[0][0] == 0.9


def test_keypoint_bbox_and_iou():
    kps = [[0.2, 0.1, 0.9], [0.4, 0.5, 0.9], [0.9, 0.9, 0.0]]
    assert keypoint_bbox(kps) == (0.2, 0.1, 0.4, 0.5)
    assert keypoint_bbox([[0.1, 0.1, 0.0]] * 17) is None
    assert iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
    assert iou((0, 0, 1, 1), (2, 2, 3, 3)) == 0.0


def test_tracker_keeps_ids_when_people_swap_order():
    stand = load_scenarios()["an_toan"]["kps"]
    left, right = shifted(stand, -0.3), shifted(stand, 0.3)
    tr = PoseTracker()
    first = {round(p.bbox[0], 2): p.track_id for p in tr.update([left, right], 0.0)}
    # Detector returns them in the opposite order and slightly moved.
    second = tr.update([shifted(right, 0.01), shifted(left, 0.01)], 0.1)
    for p in second:
        assert p.track_id == first[round(p.bbox[0] - 0.01, 2)]
    assert len({p.track_id for p in second}) == 2


def test_tracker_keeps_id_through_sudden_collapse_and_weak_detections():
    stand = load_scenarios()["an_toan"]["kps"]
    collapsed = [[x, 0.95 - (y - 0.12) * 0.3, c] for x, y, c in stand]
    tr = PoseTracker()
    a = tr.update([stand], 0.0)[0].track_id
    assert tr.update([collapsed], 0.1)[0].track_id == a  # size-gated centre match
    weak = [[x, y, 0.3] for x, y, _ in collapsed]  # occluded: mean confidence 0.3
    assert tr.update([weak], 0.2)[0].track_id == a
    fresh = PoseTracker()
    assert fresh.update([[[x, y, 0.15] for x, y, _ in stand]], 0.0) == []  # too weak to start


def test_tracker_predicts_motion():
    stand = load_scenarios()["an_toan"]["kps"]
    tr = PoseTracker(max_centre_dist=0.01)
    ids = {tr.update([shifted(stand, 0.08 * i)], i * 0.1)[0].track_id for i in range(4)}
    assert len(ids) == 1


def test_tracker_new_id_after_track_expires():
    stand = load_scenarios()["an_toan"]["kps"]
    tr = PoseTracker(max_age_s=1.0)
    a = tr.update([stand], 0.0)[0].track_id
    assert tr.update([stand], 0.5)[0].track_id == a
    assert tr.update([stand], 3.0)[0].track_id != a
