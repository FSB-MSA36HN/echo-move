"""FastAPI application.

Realtime:  /ws/pose (browser frames), /ws/camera/{id} (server cameras), /ws/events (alerts)
REST:      /health, /matlab_iqa, /api/cameras..., /api/events..., /api/stats
Static:    the web UI (web/) at /, when the folder is available.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .alerts import Alert, AlertHub
from .alerts.engine import ALERT_TYPES, MESSAGES
from .camera import CameraManager
from .config import Settings, get_settings
from .logging_setup import setup_logging
from .maintenance import Maintenance
from .matlab_bridge import MatlabBridge
from .notify import Notifier
from .pipeline import StreamPipeline, decode_frame
from .pose.detector import PoseDetector
from .scenarios import DemoGenerator
from .schemas import FrameMessage
from .storage import EventStore
from .storage.db import read_clip_frames
from .zones import OptionsStore, parse_options

log = logging.getLogger("echo_move")


class EventIn(BaseModel):
    """Alert confirmed client-side (browser AI mode) and reported for logging."""

    type: Literal["FALL", "MANDOWN", "RECOVERED", "POSTURE", "ERGO", "CAMERA"]
    detail: str = Field(default="", max_length=200)
    track_id: int | None = None
    source: str = Field(default="browser", max_length=40)
    image: str | None = None  # optional JPEG data URL


class ZoneIn(BaseModel):
    name: str = Field(default="", max_length=40)
    points: list[list[float]] = Field(min_length=3, max_length=50)
    dwell_s: float = Field(default=1.0, ge=0, le=600)


class CameraConfigIn(BaseModel):
    zones: list[ZoneIn] = Field(default_factory=list, max_length=20)
    disabled_rules: list[str] = Field(default_factory=list)


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or get_settings()
    setup_logging(cfg.log_level)
    bridge = MatlabBridge(cfg.matlab_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        detector = PoseDetector(cfg)
        try:
            store: EventStore | None = EventStore(cfg.data_dir)
        except Exception:
            log.exception("event store unavailable (%s) — events will not be saved", cfg.data_dir)
            store = None
        notifier = Notifier(cfg)
        notifier.start()
        hub = AlertHub(store, notifier)
        cameras = CameraManager(cfg, detector, hub,
                                options_store=OptionsStore(cfg.data_dir / "camera_config.json"))
        cameras.start()
        maintenance = Maintenance(cfg, store, notifier, hub)
        housekeeping = asyncio.create_task(maintenance.loop())
        app.state.detector, app.state.store, app.state.hub = detector, store, hub
        app.state.notifier, app.state.cameras = notifier, cameras
        app.state.maintenance = maintenance
        log.info("ECHO MOVE %s ready — AI=%s cameras=%d notify=%s web=%s", __version__,
                 detector.available, len(cameras.workers), notifier.channels() or "off",
                 cfg.web_dir if (cfg.web_dir / "index.html").is_file() else "off")
        yield
        housekeeping.cancel()
        cameras.stop()
        notifier.stop()
        if store:
            store.close()

    app = FastAPI(title="ECHO MOVE", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])

    def store_or_503(request: Request) -> EventStore:
        store: EventStore | None = request.app.state.store
        if store is None:
            raise HTTPException(503, "event store unavailable")
        return store

    # ------------------------------------------------------------------ status
    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        st = request.app.state
        det: PoseDetector = st.detector
        return {"status": "ok", "demo_mode": not det.available, "yolo": det.available,
                "hands": det.hands is not None, "version": __version__,
                "piqe_mode": cfg.piqe_mode, "matlab_dir": str(cfg.matlab_dir.resolve()),
                "cameras": len(st.cameras.workers), "events_db": st.store is not None,
                "notify": st.notifier.channels()}

    @app.get("/matlab_iqa")
    async def matlab_iqa() -> dict[str, Any]:
        data = bridge.read()
        return {"available": False} if data is None else {"available": True, **data}

    # ------------------------------------------------------------------ cameras
    def camera_or_404(request: Request, cam_id: str) -> Any:
        w = request.app.state.cameras.get(cam_id)
        if w is None:
            raise HTTPException(404, f"camera '{cam_id}' not found")
        return w

    @app.get("/api/cameras")
    async def list_cameras(request: Request) -> list[dict[str, Any]]:
        return list(request.app.state.cameras.statuses())

    @app.get("/api/cameras/{cam_id}/config")
    async def get_camera_config(request: Request, cam_id: str) -> dict[str, Any]:
        w = camera_or_404(request, cam_id)
        return {"id": cam_id, **w.pipeline.options.to_dict(), "rules": list(ALERT_TYPES)}

    @app.put("/api/cameras/{cam_id}/config")
    async def put_camera_config(request: Request, cam_id: str,
                                body: CameraConfigIn) -> dict[str, Any]:
        camera_or_404(request, cam_id)
        try:
            options = parse_options(body.model_dump(), cfg.zone_dwell_s)
        except (ValueError, TypeError, IndexError) as exc:
            raise HTTPException(422, str(exc)) from None
        unknown = set(options.disabled_rules) - set(ALERT_TYPES)
        if unknown:
            raise HTTPException(422, f"unknown rules: {sorted(unknown)}")
        request.app.state.cameras.configure(cam_id, options)
        return {"id": cam_id, **options.to_dict()}

    @app.get("/api/cameras/{cam_id}/snapshot.jpg")
    async def camera_snapshot(request: Request, cam_id: str) -> Response:
        w = camera_or_404(request, cam_id)
        if not w.latest_jpeg:
            raise HTTPException(503, "no frame yet")
        return Response(w.latest_jpeg, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/cameras/{cam_id}/stream")
    async def camera_stream(request: Request, cam_id: str) -> StreamingResponse:
        w = camera_or_404(request, cam_id)

        async def frames() -> AsyncIterator[bytes]:
            last = -1
            while not await request.is_disconnected():
                if w.result_seq != last and w.latest_jpeg:
                    last, jpeg = w.result_seq, w.latest_jpeg
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                await asyncio.sleep(0.04)

        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.websocket("/ws/camera/{cam_id}")
    async def ws_camera(ws: WebSocket, cam_id: str) -> None:
        w = ws.app.state.cameras.get(cam_id)
        await ws.accept()
        if w is None:
            await ws.send_text(json.dumps({"error": f"camera '{cam_id}' not found"}))
            await ws.close()
            return
        last = -1
        try:
            while True:
                if w.result_seq != last and w.latest is not None:
                    last = w.result_seq
                    await ws.send_text(json.dumps({**w.latest, "status": w.status()}))
                await asyncio.sleep(0.05)
        except (WebSocketDisconnect, RuntimeError):
            pass

    # ------------------------------------------------------------------ events
    @app.get("/api/events")
    async def list_events(
        request: Request,
        type: str | None = None, source: str | None = None, level: str | None = None,
        since: float | None = None, until: float | None = None,
        hours: float | None = Query(default=None, gt=0),
        acknowledged: bool | None = None,
        limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        store = store_or_503(request)
        if hours is not None:
            since = time.time() - hours * 3600
        items, total = store.list(type=type, source=source, level=level, since=since,
                                  until=until, acknowledged=acknowledged, limit=limit,
                                  offset=offset)
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/events.csv")
    async def events_csv(request: Request, type: str | None = None, source: str | None = None,
                         hours: float | None = Query(default=None, gt=0)) -> PlainTextResponse:
        store = store_or_503(request)
        since = time.time() - hours * 3600 if hours else None
        body = "\ufeff" + store.to_csv(type=type, source=source, since=since)
        name = time.strftime("echo_events_%Y%m%d_%H%M%S.csv")
        return PlainTextResponse(body, media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post("/api/events", status_code=201)
    async def create_event(request: Request, body: EventIn) -> dict[str, Any]:
        store_or_503(request)
        level, message = MESSAGES[body.type]
        jpeg = None
        if body.image:
            try:
                jpeg = base64.b64decode(body.image.split(",", 1)[-1], validate=False)
            except ValueError:
                raise HTTPException(422, "invalid image") from None
            if len(jpeg) > cfg.max_message_bytes:
                raise HTTPException(413, "image too large")
        alert = Alert(body.type, level, body.source, message, body.detail, body.track_id)
        hub: AlertHub = request.app.state.hub
        return await asyncio.get_running_loop().run_in_executor(None, hub.publish, alert, jpeg)

    @app.get("/api/events/{event_id}")
    async def get_event(request: Request, event_id: int) -> dict[str, Any]:
        event = store_or_503(request).get(event_id)
        if event is None:
            raise HTTPException(404, "event not found")
        return event

    @app.get("/api/events/{event_id}/image")
    async def event_image(request: Request, event_id: int) -> FileResponse:
        path = store_or_503(request).image_path(event_id)
        if path is None:
            raise HTTPException(404, "no snapshot for this event")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/events/{event_id}/clip.mp4")
    async def event_clip_mp4(request: Request, event_id: int) -> FileResponse:
        _, mp4 = store_or_503(request).clip_paths(event_id)
        if mp4 is None:
            raise HTTPException(404, "no clip for this event")
        return FileResponse(mp4, media_type="video/mp4", filename=f"event_{event_id}.mp4")

    @app.get("/api/events/{event_id}/clip")
    async def event_clip_stream(request: Request, event_id: int) -> StreamingResponse:
        """Replay the clip as MJPEG (plays in an <img> whatever codec the MP4 got)."""
        mjpg, _ = store_or_503(request).clip_paths(event_id)
        if mjpg is None:
            raise HTTPException(404, "no clip for this event")
        fps, frames = read_clip_frames(mjpg)

        async def replay() -> AsyncIterator[bytes]:
            for jpeg in frames:
                if await request.is_disconnected():
                    return
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                await asyncio.sleep(1.0 / max(fps, 1.0))

        return StreamingResponse(replay(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.post("/api/events/{event_id}/ack")
    async def ack_event(request: Request, event_id: int) -> dict[str, Any]:
        if not store_or_503(request).acknowledge(event_id):
            raise HTTPException(404, "event not found")
        return {"id": event_id, "acknowledged": True}

    @app.post("/api/events/{event_id}/false-alarm")
    async def false_alarm(request: Request, event_id: int) -> dict[str, Any]:
        if not store_or_503(request).acknowledge(event_id, false_alarm=True):
            raise HTTPException(404, "event not found")
        return {"id": event_id, "acknowledged": True, "false_alarm": True}

    @app.get("/api/stats")
    async def stats(request: Request,
                    hours: float = Query(default=24, gt=0, le=24 * 365)) -> dict[str, Any]:
        out = store_or_503(request).stats(since=time.time() - hours * 3600)
        out["hours"] = hours
        return out

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket) -> None:
        await ws.accept()
        hub: AlertHub = ws.app.state.hub
        q = hub.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20)
                    await ws.send_text(json.dumps(event, ensure_ascii=False))
                except asyncio.TimeoutError:
                    await ws.send_text(json.dumps({"ping": time.time()}))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.unsubscribe(q)

    # ------------------------------------------------------------------ browser frames
    @app.websocket("/ws/pose")
    async def ws_pose(ws: WebSocket) -> None:
        await ws.accept()
        st = ws.app.state
        det: PoseDetector = st.detector
        hub = st.hub if cfg.record_browser_events else None
        pipe = StreamPipeline("browser" if det.available else "demo", det, cfg, hub)
        demo = DemoGenerator(cfg.server_fps)
        loop = asyncio.get_running_loop()
        last_ts = 0.0
        try:
            while True:
                text = await ws.receive_text()
                now = time.time()
                if now - last_ts < 1.0 / cfg.server_fps:
                    await ws.send_text(json.dumps({"skip": True}))
                    continue
                last_ts = now
                if not det.available:
                    payload = pipe.observe(demo.next_frame(bridge.read()), now)
                    await ws.send_text(json.dumps(payload))
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
                    await ws.send_text(json.dumps({"error": "undecodable frame"}))
                    continue
                # Blocking CV/NN work runs off the event loop.
                payload = await loop.run_in_executor(None, pipe.process, frame, now)
                payload["matlab_iqa"] = bridge.read()
                await ws.send_text(json.dumps(payload))
        except WebSocketDisconnect:
            log.info("client disconnected")
        except Exception:
            log.exception("websocket error")

    # ------------------------------------------------------------------ web UI
    if (cfg.web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=cfg.web_dir, html=True), name="web")

    return app


app = create_app()
