# Kiến trúc

## Luồng dữ liệu
1. **Nguồn ảnh**
   - *Camera server* (`ECHO_CAMERAS`): mỗi camera có 1 luồng đọc (luôn giữ frame mới nhất, không dồn hàng đợi RTSP, tự kết nối lại 1 → 30 s) và 1 luồng xử lý chạy ở `ECHO_CAMERA_FPS`.
   - *Webcam/video trên trình duyệt* gửi frame qua `/ws/pose` (chế độ **Server**), hoặc chạy MediaPipe ngay trong trình duyệt.
   - *MATLAB* ghi `output/<video>_iqa.json` (ghi file tạm rồi `movefile`); `MatlabBridge` đọc file mới nhất (cache theo mtime).
2. **`StreamPipeline`** (một instance cho mỗi nguồn): YOLOv8-Pose (dùng chung, có khoá vì Ultralytics không thread-safe) → `PoseTracker` (ID ổn định + One-Euro theo từng người) → `classify_posture` → IQA → `AlertEngine` (xác nhận theo thời gian, cooldown).
3. **`AlertHub`**: cảnh báo đã xác nhận → `EventStore` (SQLite `echo.db` + ảnh `snapshots/`) → `Notifier` (Telegram/webhook, luồng nền, hàng đợi có giới hạn, thử lại 3 lần) → đẩy realtime tới mọi client `/ws/events`.
4. **Web**: tab *Giám sát* (nguồn cục bộ + người 3D), tab *Camera* (lưới MJPEG, chọn 1 camera để điều khiển người 3D), tab *Sự kiện* (lịch sử, thống kê, xác nhận, CSV). Còi WebAudio + thông báo desktop khi có cảnh báo.

## Module backend (`backend/src/echo_move`)
| Module | Nhiệm vụ |
|---|---|
| `config.py` | `Settings` đọc từ biến môi trường `ECHO_*` |
| `iqa/metrics.py`, `iqa/piqe.py` | 5 metric IQA, PIQE block-wise (vector hoá) |
| `pose/detector.py` | Bọc YOLO + MediaPipe Hands (import tuỳ chọn), `detect_raw` không trạng thái |
| `pose/tracker.py` | Tracker tham lam IoU + khoảng cách tâm (kiểu SORT, không Kalman) |
| `pose/filters.py` | One-Euro filter, `KeypointSmoother` |
| `pose/classifier.py` | Luật tư thế theo từng frame (có hiệu chỉnh tỉ lệ khung hình) |
| `alerts/engine.py` | Xác nhận FALL / POSTURE / CAMERA theo thời gian, cooldown |
| `alerts/hub.py` | Lưu → thông báo → phát realtime (thread-safe) |
| `storage/db.py` | `EventStore` SQLite (WAL) + ảnh JPEG, thống kê, CSV |
| `notify/` | Telegram `sendPhoto`/`sendMessage`, webhook JSON |
| `camera/worker.py`, `camera/manager.py` | Đọc RTSP/USB/file, kết nối lại, che mật khẩu trong log/API |
| `pipeline.py` | `StreamPipeline` dùng chung cho camera server và `/ws/pose` |
| `render.py` | Vẽ skeleton + nhãn lên ảnh (MJPEG, ảnh sự kiện) |
| `matlab_bridge.py` | Đọc JSON MATLAB |
| `scenarios.py` + `data/scenarios.json` | Kịch bản demo; `scripts/export_scenarios.py` sao chép sang web |
| `app.py` | `create_app()`: REST + WebSocket + phục vụ thư mục `web/` tại `/` |

## API
| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/health` | Trạng thái, phiên bản, AI/demo, số camera, DB, kênh thông báo |
| GET | `/matlab_iqa` | JSON MATLAB mới nhất |
| GET | `/api/cameras` | Danh sách camera: `state` (`online/connecting/reconnecting/stalled/stopped`), fps, số người, IQA |
| GET | `/api/cameras/{id}/snapshot.jpg` | Ảnh mới nhất đã vẽ skeleton |
| GET | `/api/cameras/{id}/stream` | MJPEG (`multipart/x-mixed-replace`) — dùng trực tiếp trong `<img>` |
| WS | `/ws/camera/{id}` | Kết quả phân tích từng frame (cùng định dạng `/ws/pose`) + `status` |
| GET | `/api/events` | Lọc `type`, `source`, `level`, `since`, `until`, `hours`, `acknowledged`; phân trang `limit`, `offset` |
| GET | `/api/events.csv` | Xuất CSV (UTF-8 BOM, mở được bằng Excel) |
| POST | `/api/events` | Trình duyệt báo cảnh báo đã xác nhận (`type`, `detail`, `track_id`, `source`, `image` data URL) |
| GET | `/api/events/{id}`, `/api/events/{id}/image` | Chi tiết, ảnh chụp |
| POST | `/api/events/{id}/ack` | Đánh dấu đã xử lý |
| GET | `/api/stats?hours=24` | Tổng, chưa xử lý, theo loại / mức / nguồn / giờ |
| WS | `/ws/events` | Đẩy sự kiện mới; `{"ping": t}` mỗi 20 s |
| WS | `/ws/pose` | Frame từ trình duyệt (xem dưới) |

Sự kiện:
```json
{"id": 12, "ts": 1731300000.5, "source": "kho", "track_id": 3, "type": "FALL", "level": "CRITICAL",
 "message": "Phát hiện công nhân bị ngã", "detail": "Ngã đột ngột", "acknowledged": false,
 "ack_ts": null, "has_image": true, "data": {"spine_deg": 82.1, "bbox_ratio": 2.4, "rapid_drop": true}}
```

## Giao thức WebSocket `/ws/pose`
Client → server:
```json
{"image": "data:image/jpeg;base64,...", "timestamp": 12.34}
```
Server → client (rút gọn):
```json
{
  "detected": true, "mode": "AI", "version": "21.0.0", "source": "browser",
  "persons": [{"id": 1, "bbox": [x0, y0, x1, y1], "keypoints": [[x, y, conf] x17],
               "safety": {"level": "SAFE|WARNING|RISK", "label": "...", "detail": "...",
                          "technique": "NONE|PROPER_LIFT|IMPROPER|PARTIAL|FALL", "color": [r,g,b],
                          "spine_deg": 0, "knee_deg": 0, "bbox_ratio": 0}}],
  "hands": [], "quality": {"piqe": 0, "piqe_full": 0, "blur": 0, "contrast": 0, "noise": 0, "exposure": 0, "overall": 0, "time_fast_ms": 0, "time_full_ms": 0},
  "env_hazards": {"hazards": [], "overall_level": "SAFE", "overall_color": [0,1,0]},
  "alerts": [],
  "frame": {"w": 640, "h": 480},
  "matlab_iqa": null,
  "benchmark": {"frame_ms": 0, "avg_frame_ms": 0, "fps_actual": 0, "frames_total": 0}
}
```
- `keypoints` là toạ độ **chuẩn hoá 0–1** theo chuẩn COCO-17; `id` là track ID ổn định giữa các frame.
- `alerts` chỉ chứa cảnh báo **vừa được xác nhận** ở frame này (đã lưu DB nếu có).
- Frame bị bỏ qua do giới hạn FPS nhận `{"skip": true}`; lỗi nhận `{"error": "..."}`. Tin nhắn lớn hơn `ECHO_MAX_MESSAGE_BYTES` (4 MB) bị từ chối.

## Web (`web/js`)
| File | Nhiệm vụ |
|---|---|
| `config.js` | `?server=` (nhớ trong localStorage) |
| `backend.js` | Dò backend: `?server` → cùng origin → `localhost:8000`; kiểm tra sức khoẻ 15 s; giữ `/ws/events` |
| `alerts.js` | Bộ xác nhận theo thời gian (cùng luật backend), còi WebAudio, Notification API, toast, gửi sự kiện từ AI trình duyệt lên backend |
| `human3d.js` | Cảnh nhà xưởng, công nhân GLTF có xương + đồ bảo hộ, retarget COCO-17 → xương, fallback người dựng bằng code |
| `app.js` | Tab Giám sát: nguồn (kịch bản / webcam / video / server), MediaPipe, IQA, báo cáo |
| `cameras.js`, `events.js` | Tab Camera, tab Sự kiện |

Web luôn chạy được không cần backend (mở file trực tiếp hoặc GitHub Pages); các tab Camera/Sự kiện khi đó hiện hướng dẫn kết nối.

## JSON của MATLAB
`{ "summary": {video, frames, fps, piqe, piqe_full, blur, contrast, noise, exposure, overall, time_fast_ms, time_full_ms, effective_fps, piqe_correlation, status, progress, updated_at, ...}, "per_frame": [...] }`. Backend thêm `_source_file`, `_age_seconds`.
