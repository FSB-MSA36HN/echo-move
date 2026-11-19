# ECHO MOVE — Worker Safety Warning System

Hệ thống cảnh báo an toàn lao động (đồ án môn **Xử lý ảnh**): nhận diện **5 sự kiện tư thế** — **Ngã (FALL)**, **Đứng (STANDING)**, **Ngồi xổm (SQUAT)**, **Cúi khom (STOOP)**, **Một phần cơ thể (PARTIAL)** — bằng YOLOv8-Pose (COCO-17) + tracking nhiều người, kèm **IQA** trên dashboard. Đọc **camera IP (RTSP) / USB / file**, **xác nhận theo thời gian**, nhật ký + clip, Telegram/webhook, **SOC dashboard** và người 3D.

Luật ngã **đa tín hiệu** (nằm ngang / đầu thấp / sụp người). PARTIAL dựa conf keypoints YOLO (thiếu core joints hoặc cắt mép). Clip 5 s trước+sau, leo thang CRITICAL, làm mờ mặt, Báo nhầm, retention, `make eval` trên UR Fall / Le2i.

```
 Camera IP/USB/file ──▶ ┌───────────────────────────────┐ ── /api/cameras/*/stream (MJPEG) ──▶ ┌──────────────────────┐
                        │ Python (FastAPI) echo_move     │ ── /ws/events (cảnh báo realtime) ─▶ │ Web (Three.js)       │
 MATLAB *_iqa.json ───▶ │ YOLOv8-Pose → tracker → luật   │ ◀─ /ws/pose (frame webcam) ───────── │ Giám sát · Camera ·  │
                        │ → xác nhận theo thời gian      │ ── /api/events, /api/stats, CSV ──▶ │ Sự kiện · người 3D   │
                        │ → SQLite + ảnh → Telegram/hook │                                      └──────────────────────┘
                        └───────────────────────────────┘
```

| Tầng | Vai trò | Thư mục |
|---|---|---|
| MATLAB | Phân tích IQA offline trên video, 9 biểu đồ, xuất JSON/CSV/PNG | [matlab/](matlab/) |
| Python | Camera server, YOLOv8-Pose + tracking, 5 metric IQA, xác nhận cảnh báo, nhật ký SQLite, thông báo, phục vụ giao diện web | [backend/](backend/) |
| Web | SOC dashboard (live | 3D+IQA | Cameras/Events/System), công nhân 3D, còi + thông báo, 5 loại sự kiện tư thế | [web/](web/) |

## Chạy nhanh

**1. Chỉ giao diện (không cần cài gì)** — mở `web/index.html` bằng Chrome/Edge, bấm phím `1`–`8`. Bản GitHub Pages hoạt động y như vậy.

**2. Backend (giao diện được phục vụ luôn tại http://localhost:8000)**
```bash
make install-ai && make run   # YOLOv8-Pose + MediaPipe; tự tải yolov8n-pose.pt lần đầu
```
Mở <http://localhost:8000> — web tự nhận backend (chấm xanh góc trên). Mở `web/index.html` trực tiếp vẫn được: web tự dò `localhost:8000`.

**3. Camera thật + thông báo (tuỳ chọn, chỉ cần biến môi trường)**
```bash
export ECHO_CAMERAS="kho=rtsp://user:pass@192.168.1.10:554/stream1,cong=0"
export ECHO_TELEGRAM_TOKEN=123456:ABC... ECHO_TELEGRAM_CHAT_ID=-100123...
make run
```
Không đặt biến nào thì các tính năng này tự tắt.

**Docker:** `cd docker && docker compose up --build` (AI bật, cổng 8000; nhật ký ở `output/`).

**VPS:** <https://test.antokr.com> (HTTPS; Docker nội bộ port 18080) — chi tiết: [docs/DEPLOY_VPS.md](docs/DEPLOY_VPS.md).

MATLAB: mở `matlab/run_iqa_engine.m`, bấm Run. Kết quả ghi vào `output/`, backend tự đọc.

## Cấu trúc thư mục
```
backend/    package Python `echo_move`: camera/, pose/ (detector, tracker, classifier, fall),
            alerts/ (engine, hub), storage/ (SQLite + clip), notify/ (Telegram, webhook),
            zones.py, maintenance.py, evaluation.py, pipeline.py, app.py; tests/
matlab/     run_iqa_engine.m, config.m, +iqa/ (hàm metric), tests/
web/        index.html, css/, js/ (app, human3d, backend, alerts, cameras, events),
            assets/models/ (worker.glb)
docs/       USER_GUIDE.md, ARCHITECTURE.md, ALGORITHMS.md, DEMO_SCRIPT.md
scripts/    benchmark.py, evaluate.py, embed_model.py
docker/     Dockerfile, docker-compose.yml
output/     MATLAB JSON, echo.db, snapshots/, clips/, camera_config.json (không commit)
data/       video mẫu (không commit)
```

## Tài liệu
- [Hướng dẫn sử dụng](docs/USER_GUIDE.md) — cài đặt, camera RTSP, Telegram, các tab web, troubleshooting
- [Kiến trúc & API](docs/ARCHITECTURE.md)
- [Thuật toán & trích dẫn](docs/ALGORITHMS.md) — IQA, phân loại tư thế, tracking, xác nhận theo thời gian, dựng người 3D
- [Kịch bản thuyết trình & Q&A](docs/DEMO_SCRIPT.md)
- [Changelog](CHANGELOG.md)

## Phát triển
```bash
make test     # pytest (tracker, alert engine, SQLite, notifier, camera worker, API)
make lint     # ruff + mypy
make bench    # đo tốc độ & tương quan PIQE fast vs full (số liệu thật)
make calibrate-iqa   # chứng minh / tìm trọng số Overall IQA trên ảnh suy giảm có kiểm soát
make eval DATASET=urfd ROOT=data/urfd   # precision/recall/F1 + độ trễ trên dataset ngã (cần AI)
```
CI (GitHub Actions) chạy lint + test mỗi lần push. Biến môi trường cấu hình: xem [.env.example](.env.example).

## Trích dẫn
Pech-Pacheco et al. 2000 (blur) · Immerkær 1996 (noise) · Peli 1990 (contrast) · Venkatanath et al. 2015 (PIQE) · ISO 18434-1 (exposure) · Casiez et al. 2012 (One-Euro filter) · Bewley et al. 2016 (SORT) · Zhang et al. 2022 (ByteTrack) · Hignett & McAtamney 2000 (REBA) · Kwolek & Kepski 2014 (UR Fall) · Charfi et al. 2013 (Le2i) · Ultralytics YOLOv8-Pose · Google MediaPipe · Mô hình 3D "Xbot" từ ví dụ three.js (Mixamo).

## Giấy phép
MIT — xem [LICENSE](LICENSE). Mô hình 3D: xem [web/assets/models/README.md](web/assets/models/README.md).
