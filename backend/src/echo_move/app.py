"""FastAPI application: /health, /matlab_iqa, /ws/pose."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from . import __version__
from .config import Settings, get_settings
from .iqa import compute_iqa
from .logging_setup import setup_logging
from .matlab_bridge import MatlabBridge
from .pose.detector import PoseDetector
from .scenarios import DemoGenerator
from .schemas import FrameMessage

log = logging.getLogger("echo_move")


def _env_from_quality(iqa: dict[str, float], cfg: Settings) -> dict[str, Any]:
    if iqa["overall"] < cfg.low_quality_threshold:
        return {"hazards": [{"name": "LOW_Q", "label": "ẢNH KÉM", "advice": "Kiểm tra camera"}],
                "overall_level": "RISK", "overall_color": [1, 0.65, 0]}
    return {"hazards": [], "overall_level": "SAFE", "overall_color": [0, 1, 0]}


def decode_frame(data_url: str, max_width: int) -> np.ndarray | None:
    try:
        payload = data_url.split(",", 1)[-1]
        frame = cv2.imdecode(np.frombuffer(base64.b64decode(payload), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    if frame is None:
        return None
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
    return frame


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or get_settings()
    setup_logging(cfg.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.detector = PoseDetector(cfg)
        yield

    app = FastAPI(title="ECHO MOVE", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    bridge = MatlabBridge(cfg.matlab_dir)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        det: PoseDetector = app.state.detector
        return {"status": "ok", "demo_mode": not det.available, "yolo": det.available,
                "hands": det.hands is not None, "version": __version__,
                "piqe_mode": cfg.piqe_mode, "matlab_dir": str(cfg.matlab_dir.resolve())}

    @app.get("/matlab_iqa")
    async def matlab_iqa() -> dict[str, Any]:
        data = bridge.read()
        return {"available": False} if data is None else {"available": True, **data}

    @app.websocket("/ws/pose")
    async def ws_pose(ws: WebSocket) -> None:
        await ws.accept()
        det: PoseDetector = app.state.detector
        det.reset()
        demo = DemoGenerator(cfg.server_fps)
        loop = asyncio.get_running_loop()
        last_ts, frame_count = 0.0, 0
        bench: deque[float] = deque(maxlen=100)
        try:
            while True:
                text = await ws.receive_text()
                started = time.perf_counter()
                now = time.time()
                if now - last_ts < 1.0 / cfg.server_fps:
                    await ws.send_text(json.dumps({"skip": True}))
                    continue
                last_ts = now
                if not det.available:
                    await ws.send_text(json.dumps(demo.next_frame(bridge.read())))
                    frame_count += 1
                    continue
                if len(text) > cfg.max_message_bytes:
                    await ws.send_text(json.dumps({"error": "frame too large"}))
                    continue
                try:
                    msg = FrameMessage.model_validate_json(text)
                except ValidationError:
                    await ws.send_text(json.dumps({"error": "invalid message"}))
                    continue
                frame = decode_frame(msg.image, cfg.max_frame_width)
                if frame is None:
                    continue
                t = msg.timestamp if msg.timestamp is not None else now
                # Blocking CV/NN work runs off the event loop.
                persons, hands = await loop.run_in_executor(None, det.detect, frame, t)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                iqa = compute_iqa(
                    gray, gray.astype(np.float64) / 255.0, mode=cfg.piqe_mode,  # type: ignore[arg-type]
                    weights=cfg.iqa_weights,
                    compute_full=frame_count % cfg.piqe_sample_every == 0,
                ).to_dict()
                frame_ms = (time.perf_counter() - started) * 1000
                bench.append(frame_ms)
                avg = sum(bench) / len(bench)
                await ws.send_text(json.dumps({
                    "detected": bool(persons), "persons": persons, "hands": hands,
                    "quality": iqa, "env_hazards": _env_from_quality(iqa, cfg),
                    "matlab_iqa": bridge.read(),
                    "benchmark": {"frame_ms": round(frame_ms, 2), "avg_frame_ms": round(avg, 2),
                                  "fps_actual": round(1000.0 / max(avg, 1), 1),
                                  "frames_total": frame_count},
                    "mode": "AI", "version": "20.0",
                }))
                frame_count += 1
        except WebSocketDisconnect:
            log.info("client disconnected")
        except Exception:
            log.exception("websocket error")

    return app


app = create_app()
