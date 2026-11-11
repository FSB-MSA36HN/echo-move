# Changelog

## 21.0.0 — người 3D thật + hệ thống chạy thực tế
- **Người 3D**: thay robot bằng mô hình người GLTF có xương (Xbot/Mixamo, ~2.9 MB, nhúng base64 để chạy cả khi mở `file://`), mặc đồ bảo hộ (mũ cứng, áo phản quang có dải sáng đổi màu theo mức nguy hiểm, găng, ủng) bằng shader; retarget COCO-17 → xương với ước lượng chiều sâu từ độ co ngắn chi, nhận MediaPipe world landmarks khi có. Cảnh nhà xưởng: sàn bê tông, vạch nguy hiểm, kệ, đèn xoay cảnh báo, khói/bụi, lửa. Fallback: người dựng bằng code (cùng tên xương) → 2D.
- **Camera server**: `ECHO_CAMERAS` / `ECHO_CAMERAS_FILE` nhận RTSP/HTTP, webcam USB, file video (tự lặp); luôn xử lý frame mới nhất, tự kết nối lại có backoff; ẩn mật khẩu RTSP trong log/API.
- **Tracking**: `PoseTracker` gán ID ổn định theo IoU + khoảng cách tâm, làm mượt One-Euro theo từng người.
- **Xác nhận cảnh báo theo thời gian**: ngã phải kéo dài 1.5 s (giảm một nửa nếu hông rơi nhanh), cúi sai 3 s, camera kém 5 s; bỏ qua mất dấu < 0.5 s; cooldown 30 s cho mỗi (loại, người). Luật ngã mới: thân nghiêng > 65° **và** khung người rộng hơn cao (thay cho `|y_vai − y_hông| < 0.08` dễ báo nhầm khi cúi sâu).
- **Sửa**: phân loại tư thế nay hiệu chỉnh tỉ lệ khung hình (16:9 làm lệch góc lưng ~40 %); web trước đây dùng chiều cao video thay cho tỉ lệ.
- **Nhật ký sự kiện**: SQLite (`output/echo.db`) + ảnh chụp có vẽ skeleton; API lọc/phân trang, thống kê theo giờ, xác nhận đã xử lý, xuất CSV.
- **Thông báo**: Telegram (kèm ảnh) và webhook JSON, chạy nền, thử lại; tự tắt khi chưa cấu hình.
- **Web**: 3 tab Giám sát / Camera (lưới MJPEG, chọn camera để điều khiển người 3D) / Sự kiện; còi WebAudio, thông báo desktop, toast; tự dò backend cùng origin hoặc `localhost:8000`.
- **Backend phục vụ giao diện** tại `/` (`ECHO_WEB_DIR`, tự tìm thư mục `web/`); Docker image kèm `web/`.
- Test mới: tracker, alert engine, SQLite, notifier (giả lập mạng), camera worker (capture giả + file video thật), API sự kiện/camera/WS.
- Cách deploy không đổi: `make run/demo`, `docker compose up`, notebook Colab, GitHub Pages.

## 20.0.0 — tái cấu trúc
- Tách backend thành package `echo_move` (config, iqa, pose, bridge, app), có test, lint, Docker, CI.
- MATLAB tách thành package `+iqa` + `run_iqa_engine.m`; ghi JSON an toàn (ghi file tạm rồi `movefile`).
- Web tách `index.html` / `css/` / `js/`.
- **Sửa lỗi**: YOLO trả toạ độ pixel còn web/bộ phân loại dùng toạ độ chuẩn hoá 0–1 → dùng `keypoints.xyn`; công thức góc cột sống dùng `+1` (pixel) nay là epsilon.
- **Sửa**: MATLAB ghi `../Python/ketqua` còn Python đọc `../ketqua` → thống nhất `output/`.
- Inference chạy trong executor (không chặn event loop); bỏ tự `pip install`.
