# Changelog

## 20.0.0 — tái cấu trúc
- Tách backend thành package `echo_move` (config, iqa, pose, bridge, app), có test, lint, Docker, CI.
- MATLAB tách thành package `+iqa` + `run_iqa_engine.m`; ghi JSON an toàn (ghi file tạm rồi `movefile`).
- Web tách `index.html` / `css/` / `js/`.
- **Sửa lỗi**: YOLO trả toạ độ pixel còn web/bộ phân loại dùng toạ độ chuẩn hoá 0–1 → dùng `keypoints.xyn`; công thức góc cột sống dùng `+1` (pixel) nay là epsilon.
- **Sửa**: MATLAB ghi `../Python/ketqua` còn Python đọc `../ketqua` → thống nhất `output/`.
- Inference chạy trong executor (không chặn event loop); bỏ tự `pip install`.
