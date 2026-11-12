from dataclasses import replace

from echo_move.config import Settings
from echo_move.evaluation import (
    Extraction,
    VideoCase,
    discover,
    evaluate,
    load_extraction,
    markdown,
    replay,
    save_extraction,
    score,
    summarize,
    variants,
)
from echo_move.scenarios import load_scenarios

CFG = replace(Settings(), mandown_s=5.0)


def clip(final, stand_s=3.0, after_s=4.0, fps=10, fall_s=0.6):
    """Stand, then move to ``final`` over ``fall_s`` (a real fall is not instantaneous)."""
    sc = load_scenarios()
    stand = sc["an_toan"]["kps"]
    frames = [(i / fps, [stand]) for i in range(int(stand_s * fps))]
    steps = max(1, int(fall_s * fps))
    for i in range(int(after_s * fps)):
        a = min(1.0, (i + 1) / steps)
        kps = [[s[0] + (f[0] - s[0]) * a, s[1] + (f[1] - s[1]) * a, f[2]]
               for s, f in zip(stand, final, strict=True)]
        frames.append((stand_s + i / fps, [kps]))
    return Extraction(fps, 4 / 3, stand_s + after_s, frames)


def test_discover_urfd_and_le2i(tmp_path):
    for name in ("fall-01-cam0.mp4", "adl-02-cam0.mp4", "other.mp4"):
        (tmp_path / name).write_bytes(b"")
    cases = discover("urfd", tmp_path)
    assert [(c.path.split("/")[-1], c.positive) for c in cases] == [
        ("adl-02-cam0.mp4", False), ("fall-01-cam0.mp4", True)]
    scene = tmp_path / "le2i" / "Home_01"
    (scene / "Videos").mkdir(parents=True)
    (scene / "Annotation_files").mkdir()
    (scene / "Videos" / "video (1).avi").write_bytes(b"")
    (scene / "Videos" / "video (2).avi").write_bytes(b"")
    (scene / "Annotation_files" / "video (1).txt").write_text("50\n100\n1,1,10,10,5,5\n")
    (scene / "Annotation_files" / "video (2).txt").write_text("0\n0\n")
    le2i = {c.path.split("/")[-1]: c for c in discover("le2i", tmp_path / "le2i")}
    assert le2i["video (1).avi"].positive and le2i["video (1).avi"].fall_start_s == 2.0
    assert not le2i["video (2).avi"].positive


def test_replay_detects_fall_and_scores_latency():
    ex = clip(load_scenarios()["nga"]["kps"])
    alerts = replay(ex, CFG)
    assert alerts and alerts[0][0] == "FALL"
    r = score(VideoCase("v", True, 3.0, 3.5), alerts, ex.duration_s)
    assert r.detected and r.false_alarms == 0 and 1.0 <= r.latency_s <= 2.0


def test_multisignal_beats_legacy_on_fall_towards_camera():
    stand = load_scenarios()["an_toan"]["kps"]
    towards = [[x, 0.95 - (y - 0.12) * 0.3, c] for x, y, c in stand]
    cases = [VideoCase("pos", True), VideoCase("adl", False)]
    exs = {"pos": clip(towards), "adl": clip(load_scenarios()["nang_dung"]["kps"])}
    table = {name: evaluate(cases, exs, c)[0] for name, c in variants(CFG).items()}
    assert table["multi-signal"]["recall"] == 1.0 and table["legacy"]["recall"] == 0.0
    assert table["multi-signal"]["fp_videos"] == 0
    assert "| multi-signal |" in markdown(table)


def test_summary_counts_false_alarms(tmp_path):
    neg = score(VideoCase("adl", False), [("FALL", 1.0), ("POSTURE", 2.0)], 3600.0)
    pos = score(VideoCase("f", True, 10.0, 12.0), [("FALL", 40.0)], 60.0)
    s = summarize([neg, pos])
    assert s["fp_videos"] == 1 and s["fn"] == 1 and s["false_alarms"] == 2
    assert s["false_alarms_per_hour_adl"] == 1.0 and s["precision"] == 0.0
    ex = clip(load_scenarios()["nga"]["kps"], 0.2, 0.2)
    save_extraction(ex, tmp_path / "c.json")
    back = load_extraction(tmp_path / "c.json")
    assert back.frames[0][0] == ex.frames[0][0] and back.aspect == ex.aspect
