# ECHO MOVE — Worker Safety Warning System

Hệ thống cảnh báo an toàn lao động (đồ án môn **Xử lý ảnh**): nhận diện tư thế công nhân (cúi sai, nâng đúng kỹ thuật, ngã) bằng pose estimation và **đánh giá chất lượng ảnh (IQA)** để cảnh báo khi camera bị mờ/tối/bụi/che.

```
┌────────────┐  *_iqa.json   ┌──────────────────────┐  WebSocket /ws/pose  ┌─────────────────────┐
│  MATLAB    │ ────────────▶ │  Python (FastAPI)    │ ───────────────────▶ │  Web (Three.js)     │
│ IQA offline│  output/      │ YOLOv8-Pose + IQA    │ ◀─────────────────── │ UI + robot 3D + demo│
└────────────┘               └──────────────────────┘   frames (JPEG b64)  └─────────────────────┘
```

| Tầng | Vai trò | Thư mục |
|---|---|---|
| MATLAB | Phân tích IQA offline trên video, 9 biểu đồ, xuất JSON/CSV/PNG | [matlab/](matlab/) |
| Python | AI realtime (YOLOv8-Pose, MediaPipe Hands), 5 metric IQA, cầu nối MATLAB | [backend/](backend/) |
| Web | Giao diện, robot 3D mô phỏng tư thế, 8 kịch bản demo offline | [web/](web/) |

## Chạy nhanh (3 cách)

**1. Chỉ giao diện (không cần cài gì)** — mở `web/index.html` bằng Chrome/Edge, bấm phím `1`–`8`.

**2. Backend ở chế độ demo**
```bash
make install          # cài backend + công cụ dev
make demo             # http://localhost:8000/health
```
Mở `web/index.html`, nhập `ws://localhost:8000/ws/pose`, bấm **Server**.

**3. Backend AI đầy đủ (YOLO + MediaPipe)**
```bash
make install-ai
make run              # tự tải yolov8n-pose.pt lần đầu (~6 MB)
```

MATLAB: mở `matlab/run_iqa_engine.m`, bấm Run (chọn video; hoặc đặt `cfg.demoMode = true`). Kết quả ghi vào `output/`, backend tự đọc.

## Cấu trúc thư mục
```
backend/    package Python `echo_move` (src/, tests/, pyproject.toml)
matlab/     run_iqa_engine.m, config.m, +iqa/ (hàm metric), tests/
web/        index.html, css/, js/, data/scenarios.json
docs/       USER_GUIDE.md, ARCHITECTURE.md, ALGORITHMS.md, DEMO_SCRIPT.md, legacy/
scripts/    benchmark.py, export_scenarios.py
docker/     Dockerfile, docker-compose.yml
output/     nơi MATLAB ghi kết quả (không commit)
data/       video mẫu (không commit)
```

## Tài liệu
- [Hướng dẫn sử dụng](docs/USER_GUIDE.md) — cài đặt, 3 chế độ web, Python, MATLAB, troubleshooting, FAQ
- [Kiến trúc & giao thức](docs/ARCHITECTURE.md)
- [Thuật toán & trích dẫn](docs/ALGORITHMS.md)
- [Kịch bản demo & Q&A bảo vệ](docs/DEMO_SCRIPT.md)
- [Changelog](CHANGELOG.md)

## Phát triển
```bash
make test     # pytest
make lint     # ruff + mypy
make bench    # đo tốc độ & tương quan PIQE fast vs full (số liệu thật)
```
CI (GitHub Actions) chạy lint + test mỗi lần push. Biến môi trường cấu hình: xem [.env.example](.env.example).

## Trích dẫn
Pech-Pacheco et al. 2000 (blur) · Immerkær 1996 (noise) · Peli 1990 (contrast) · Venkatanath et al. 2015 (PIQE) · ISO 18434-1 (exposure) · Casiez et al. 2012 (One-Euro filter) · Ultralytics YOLOv8-Pose · Google MediaPipe.

## Giấy phép
MIT — xem [LICENSE](LICENSE).
