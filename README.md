# ECHO MOVE — Worker Safety Warning System

Hệ thống cảnh báo an toàn lao động (đồ án môn **Xử lý ảnh**): nhận diện tư thế công nhân (cúi sai, nâng đúng kỹ thuật, ngã) bằng pose estimation và **đánh giá chất lượng ảnh (IQA)** để cảnh báo khi camera bị mờ/tối/bụi/che. Bản 21 chạy được ngoài thực tế: đọc **camera IP (RTSP) / USB / file video** ngay trên server, **xác nhận cảnh báo theo thời gian** (theo từng người, có tracking ID), **ghi nhật ký sự kiện** kèm ảnh chụp, gửi **Telegram / webhook**, và hiển thị **công nhân 3D** mặc đồ bảo hộ mô phỏng đúng tư thế.

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
| Web | Giao diện 3 tab (Giám sát / Camera / Sự kiện), công nhân 3D (GLTF có xương), còi + thông báo, 8 kịch bản offline | [web/](web/) |

## Chạy nhanh

**1. Chỉ giao diện (không cần cài gì)** — mở `web/index.html` bằng Chrome/Edge, bấm phím `1`–`8`. Bản GitHub Pages hoạt động y như vậy.

**2. Backend (giao diện được phục vụ luôn tại http://localhost:8000)**
```bash
make install          # cài backend + công cụ dev
make demo             # chế độ demo (không cần model AI)
make install-ai && make run   # AI đầy đủ (YOLOv8-Pose + MediaPipe), tự tải yolov8n-pose.pt lần đầu
```
Mở <http://localhost:8000> — web tự nhận backend (chấm xanh góc trên). Mở `web/index.html` trực tiếp vẫn được: web tự dò `localhost:8000`.

**3. Camera thật + thông báo (tuỳ chọn, chỉ cần biến môi trường)**
```bash
export ECHO_CAMERAS="kho=rtsp://user:pass@192.168.1.10:554/stream1,cong=0"
export ECHO_TELEGRAM_TOKEN=123456:ABC... ECHO_TELEGRAM_CHAT_ID=-100123...
make run
```
Không đặt biến nào thì các tính năng này tự tắt — cách deploy cũ (`make run/demo`, `docker compose up`, Colab, GitHub Pages) giữ nguyên.

**Docker:** `cd docker && docker compose up --build` (demo mode, có giao diện tại cổng 8000; nhật ký lưu ở `output/`).

MATLAB: mở `matlab/run_iqa_engine.m`, bấm Run. Kết quả ghi vào `output/`, backend tự đọc.

## Cấu trúc thư mục
```
backend/    package Python `echo_move`: camera/, pose/ (detector, tracker, classifier),
            alerts/ (engine, hub), storage/ (SQLite), notify/ (Telegram, webhook),
            pipeline.py, app.py; tests/
matlab/     run_iqa_engine.m, config.m, +iqa/ (hàm metric), tests/
web/        index.html, css/, js/ (app, human3d, backend, alerts, cameras, events),
            assets/models/ (worker.glb), data/scenarios.json
docs/       USER_GUIDE.md, ARCHITECTURE.md, ALGORITHMS.md, DEMO_SCRIPT.md
scripts/    benchmark.py, export_scenarios.py, embed_model.py
docker/     Dockerfile, docker-compose.yml
output/     MATLAB JSON, echo.db, snapshots/ (không commit)
data/       video mẫu (không commit)
```

## Tài liệu
- [Hướng dẫn sử dụng](docs/USER_GUIDE.md) — cài đặt, camera RTSP, Telegram, các tab web, troubleshooting
- [Kiến trúc & API](docs/ARCHITECTURE.md)
- [Thuật toán & trích dẫn](docs/ALGORITHMS.md) — IQA, phân loại tư thế, tracking, xác nhận theo thời gian, dựng người 3D
- [Kịch bản demo & Q&A bảo vệ](docs/DEMO_SCRIPT.md)
- [Changelog](CHANGELOG.md)

## Phát triển
```bash
make test     # pytest (tracker, alert engine, SQLite, notifier, camera worker, API)
make lint     # ruff + mypy
make bench    # đo tốc độ & tương quan PIQE fast vs full (số liệu thật)
```
CI (GitHub Actions) chạy lint + test mỗi lần push. Biến môi trường cấu hình: xem [.env.example](.env.example).

## Trích dẫn
Pech-Pacheco et al. 2000 (blur) · Immerkær 1996 (noise) · Peli 1990 (contrast) · Venkatanath et al. 2015 (PIQE) · ISO 18434-1 (exposure) · Casiez et al. 2012 (One-Euro filter) · Bewley et al. 2016 (SORT) · Ultralytics YOLOv8-Pose · Google MediaPipe · Mô hình 3D "Xbot" từ ví dụ three.js (Mixamo).

## Giấy phép
MIT — xem [LICENSE](LICENSE). Mô hình 3D: xem [web/assets/models/README.md](web/assets/models/README.md).
