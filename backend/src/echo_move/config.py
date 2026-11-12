"""Runtime configuration, overridable through ``ECHO_*`` environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

PiqeMode = Literal["fast", "full", "both"]

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"ECHO_{name}", default)


def _default_output() -> Path:
    # Editable/source checkout → <repo>/output; installed package (Docker/Colab) → ./output.
    if (REPO_ROOT / "backend").is_dir():
        return REPO_ROOT / "output"
    return Path.cwd() / "output"


def _default_web() -> Path:
    for candidate in (REPO_ROOT / "web", Path.cwd() / "web", Path.cwd().parent / "web"):
        if (candidate / "index.html").is_file():
            return candidate
    return REPO_ROOT / "web"


@dataclass(frozen=True)
class Settings:
    # Server
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(_env("CORS_ORIGINS", "*").split(","))
    )
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    server_fps: int = field(default_factory=lambda: int(_env("SERVER_FPS", "20")))
    max_message_bytes: int = field(
        default_factory=lambda: int(_env("MAX_MESSAGE_BYTES", str(4 * 1024 * 1024)))
    )
    max_frame_width: int = 640
    web_dir: Path = field(default_factory=lambda: Path(_env("WEB_DIR", str(_default_web()))))

    # Models
    demo_mode: bool = field(default_factory=lambda: _env("DEMO_MODE", "0") == "1")
    model_name: str = field(default_factory=lambda: _env("MODEL", "yolov8n-pose.pt"))
    max_persons: int = field(default_factory=lambda: int(_env("MAX_PERSONS", "5")))
    yolo_conf: float = 0.25

    # Posture thresholds (degrees unless noted)
    visibility_threshold: float = 0.25
    spine_safe_deg: float = 30.0
    spine_risk_deg: float = 60.0
    knee_bent_deg: float = 140.0
    lift_spine_max_deg: float = 45.0
    fall_spine_deg: float = 65.0  # torso this far from vertical ...
    fall_bbox_ratio: float = 1.0  # ... and body box wider than tall → lying
    # Multi-signal fall rule (lying / head at hip level / body collapsed vs. standing height);
    # 0 = legacy single geometric rule, kept for A/B evaluation.
    fall_multisignal: bool = field(
        default_factory=lambda: _env("FALL_MULTISIGNAL", "1") == "1"
    )
    fall_collapse_ratio: float = 0.5  # body height below this fraction of standing height
    head_low_ratio: float = 0.15  # head less than this × body height above the hips

    # Temporal alert confirmation (seconds)
    fall_confirm_s: float = field(default_factory=lambda: float(_env("FALL_CONFIRM_S", "1.5")))
    posture_confirm_s: float = field(
        default_factory=lambda: float(_env("POSTURE_CONFIRM_S", "3"))
    )
    quality_confirm_s: float = field(
        default_factory=lambda: float(_env("QUALITY_CONFIRM_S", "5"))
    )
    alert_cooldown_s: float = field(
        default_factory=lambda: float(_env("ALERT_COOLDOWN_S", "30"))
    )
    mandown_s: float = field(default_factory=lambda: float(_env("MANDOWN_S", "10")))
    recover_s: float = 2.0
    zone_dwell_s: float = 1.0
    # REBA-lite cannot see load/coupling, so a stooped lift scores ~5-7 instead of 8+.
    ergo_reba_high: int = field(default_factory=lambda: int(_env("ERGO_REBA", "6")))
    ergo_exposure_s: float = field(
        default_factory=lambda: float(_env("ERGO_EXPOSURE_S", "60"))
    )
    ergo_window_s: float = 600.0

    # Optional PPE detector (YOLO detection model with helmet / vest classes)
    ppe_model: str = field(default_factory=lambda: _env("PPE_MODEL", ""))
    ppe_required: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            s.strip() for s in _env("PPE_REQUIRED", "helmet,vest").split(",") if s.strip()
        )
    )
    ppe_confirm_s: float = field(default_factory=lambda: float(_env("PPE_CONFIRM_S", "5")))

    # Image quality assessment
    piqe_mode: PiqeMode = field(default_factory=lambda: cast(PiqeMode, _env("PIQE_MODE", "both")))
    piqe_sample_every: int = field(default_factory=lambda: int(_env("PIQE_SAMPLE_N", "30")))
    # blur, noise, contrast, piqe, exposure → see docs/ALGORITHMS.md
    iqa_weights: tuple[float, float, float, float, float] = (0.25, 0.25, 0.20, 0.15, 0.15)
    low_quality_threshold: float = 40.0

    # Server-side cameras: "name=rtsp://...,dock=0,demo=/path/video.mp4" or a JSON file
    cameras: str = field(default_factory=lambda: _env("CAMERAS", ""))
    cameras_file: str = field(default_factory=lambda: _env("CAMERAS_FILE", ""))
    camera_fps: float = field(default_factory=lambda: float(_env("CAMERA_FPS", "10")))

    # Event storage
    data_dir: Path = field(
        default_factory=lambda: Path(_env("DATA_DIR", str(_default_output())))
    )
    record_browser_events: bool = field(
        default_factory=lambda: _env("RECORD_BROWSER_EVENTS", "1") == "1"
    )
    event_clips: bool = field(default_factory=lambda: _env("EVENT_CLIPS", "1") == "1")
    clip_pre_s: float = field(default_factory=lambda: float(_env("CLIP_PRE_S", "5")))
    clip_post_s: float = field(default_factory=lambda: float(_env("CLIP_POST_S", "5")))
    blur_faces: bool = field(default_factory=lambda: _env("BLUR_FACES", "1") == "1")
    retention_days: float = field(default_factory=lambda: float(_env("RETENTION_DAYS", "0")))
    offline_alert_s: float = field(
        default_factory=lambda: float(_env("OFFLINE_ALERT_S", "30"))
    )

    # Notifications (disabled unless configured)
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID", ""))
    webhook_url: str = field(default_factory=lambda: _env("WEBHOOK_URL", ""))
    zalo_token: str = field(default_factory=lambda: _env("ZALO_OA_TOKEN", ""))
    zalo_user_id: str = field(default_factory=lambda: _env("ZALO_USER_ID", ""))
    # Unacknowledged CRITICAL events are re-sent after this many minutes (0 = off)
    escalate_min: float = field(default_factory=lambda: float(_env("ESCALATE_MIN", "0")))
    escalate_chat_id: str = field(
        default_factory=lambda: _env("ESCALATE_TELEGRAM_CHAT_ID", "")
    )

    # MATLAB bridge
    matlab_dir: Path = field(
        default_factory=lambda: Path(_env("MATLAB_DIR", str(_default_output())))
    )


def get_settings() -> Settings:
    return Settings()
