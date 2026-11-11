from echo_move.config import Settings
from echo_move.pose.classifier import classify_posture
from echo_move.pose.filters import KeypointSmoother, OneEuro
from echo_move.scenarios import load_scenarios

CFG = Settings()
H = 1.0


def test_scenarios_classified_as_expected():
    sc = load_scenarios()
    expected = {"an_toan": "NONE", "nang_dung": "PROPER_LIFT", "cui_sai": "IMPROPER", "nga": "FALL"}
    for name, technique in expected.items():
        assert classify_posture(sc[name]["kps"], CFG, H)["technique"] == technique, name


def test_low_visibility_is_safe():
    kps = [[0.5, 0.5, 0.0]] * 17
    assert classify_posture(kps, CFG, H)["detail"] == "Không đủ điểm"


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
