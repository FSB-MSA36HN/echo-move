# Kiến trúc

## Luồng dữ liệu
1. **MATLAB** xử lý video → ghi `output/<video>_iqa.json` (ghi file tạm rồi `movefile` để Python không đọc phải file dở).
2. **Backend** `echo_move` (FastAPI): `MatlabBridge` đọc JSON mới nhất (cache theo mtime); `/ws/pose` nhận frame, chạy YOLOv8-Pose (toạ độ chuẩn hoá) → làm mượt One-Euro → phân loại tư thế → tính IQA → trả JSON.
3. **Web** hiển thị skeleton, robot 3D, cảnh báo, IQA; nếu không có server tự rơi về MediaPipe trong trình duyệt hoặc kịch bản offline.

## Module backend (`backend/src/echo_move`)
| Module | Nhiệm vụ |
|---|---|
| `config.py` | `Settings` đọc từ biến môi trường `ECHO_*` |
| `iqa/metrics.py`, `iqa/piqe.py` | 5 metric IQA, PIQE block-wise (vector hoá) |
| `pose/filters.py` | One-Euro filter, `KeypointSmoother` |
| `pose/classifier.py` | Luật phân loại tư thế (ngưỡng trong `Settings`) |
| `pose/detector.py` | Bọc YOLO + MediaPipe Hands (import tuỳ chọn) |
| `matlab_bridge.py` | Đọc JSON MATLAB |
| `scenarios.py` + `data/scenarios.json` | Kịch bản demo; `scripts/export_scenarios.py` sao chép sang web |
| `app.py` | `create_app()`: `/health`, `/matlab_iqa`, `/ws/pose` |

## Giao thức WebSocket `/ws/pose`
Client → server:
```json
{"image": "data:image/jpeg;base64,...", "timestamp": 12.34}
```
Server → client (rút gọn):
```json
{
  "detected": true, "mode": "AI", "version": "20.0",
  "persons": [{"id": 0, "keypoints": [[x, y, conf] x17], "safety": {"level": "SAFE|WARNING|RISK", "label": "...", "detail": "...", "technique": "NONE|PROPER_LIFT|IMPROPER|PARTIAL|FALL", "color": [r,g,b]}}],
  "hands": [], "quality": {"piqe": 0, "piqe_full": 0, "blur": 0, "contrast": 0, "noise": 0, "exposure": 0, "overall": 0, "time_fast_ms": 0, "time_full_ms": 0},
  "env_hazards": {"hazards": [], "overall_level": "SAFE", "overall_color": [0,1,0]},
  "matlab_iqa": null,
  "benchmark": {"frame_ms": 0, "avg_frame_ms": 0, "fps_actual": 0, "frames_total": 0}
}
```
- `keypoints` là toạ độ **chuẩn hoá 0–1** theo chuẩn COCO-17. Frame bị bỏ qua do giới hạn FPS nhận `{"skip": true}`; lỗi nhận `{"error": "..."}`.
- Tin nhắn lớn hơn `ECHO_MAX_MESSAGE_BYTES` (4 MB) bị từ chối.

## JSON của MATLAB
`{ "summary": {video, frames, fps, piqe, piqe_full, blur, contrast, noise, exposure, overall, time_fast_ms, time_full_ms, effective_fps, piqe_correlation, status, progress, updated_at, ...}, "per_frame": [...] }`. Backend thêm `_source_file`, `_age_seconds`.
