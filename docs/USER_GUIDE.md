# Hướng dẫn sử dụng

> Chuyển từ `docs/legacy/HUONG_DAN_ECHO_MOVE_v20.docx`, đã cập nhật theo cấu trúc mã nguồn mới.

## 1. Yêu cầu hệ thống
| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| CPU | Intel i3 / Ryzen 3 | i5 / Ryzen 5 |
| RAM | 4 GB | 8 GB+ |
| GPU | Không cần | CUDA (tăng tốc YOLO) |
| Camera | Webcam 480p | 720p+ |
| Ổ cứng | 500 MB | 2 GB |

| Phần mềm | Phiên bản | Ghi chú |
|---|---|---|
| Chrome / Edge | v90+ | Cần cho File System API |
| Python | 3.10 – 3.12 | Chưa hỗ trợ 3.13+ (một số thư viện AI chưa có wheel) |
| MATLAB | R2020a+ | Image Processing Toolbox khuyến nghị; Wavelet Toolbox tuỳ chọn |
| OS | Windows 10+, macOS 11+, Ubuntu 20.04+ | |

Cần internet lần đầu (tải thư viện, model YOLO, MediaPipe); sau đó chạy offline được.

## 2. Cài đặt
```bash
git clone https://github.com/FSB-MSA36HN/echo-move.git && cd echo-move
make install        # hoặc: cd backend && pip install -e ".[dev]"
make install-ai     # thêm YOLO + MediaPipe (tuỳ chọn)
```
- Model `yolov8n-pose.pt` (~6 MB) tự tải lần chạy đầu. Tải tay: <https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n-pose.pt>, đặt cạnh nơi chạy lệnh (thư mục `backend/`).
- Video mẫu: đặt `data/demo.mp4`. Chuyển định dạng: `ffmpeg -i input.mov -c:v libx264 -preset fast -crf 23 demo.mp4`.
- Kiểm tra nhanh: mở `web/index.html` → đợi ~2 giây → bấm `1` (công nhân 3D đứng, vòng sàn xanh) → bấm `T` (self-test; `MediaPipe` và `Backend` hiện ⚠/✗ là bình thường khi chưa bật AI/backend).

## 3. Giao diện web
Có 2 cách mở: **http://localhost:8000** (backend phục vụ giao diện — khuyến nghị) hoặc mở thẳng `web/index.html` / GitHub Pages (web tự dò backend ở `localhost:8000`; không có backend thì vẫn chạy kịch bản offline). Góc trên: chấm xanh **Backend v21 · AI/DEMO · n cam** khi đã kết nối; nút 🔔/🔕 bật/tắt còi (bấm lần đầu để trình duyệt cho phép âm thanh và hỏi quyền thông báo desktop).

Ba tab:
- **🎥 Giám sát** — nguồn cục bộ (kịch bản, webcam, video, chế độ Server) + IQA + báo cáo. Cột phải: công nhân 3D mặc đồ bảo hộ trong nhà xưởng, dải phản quang và vòng sàn đổi màu theo mức an toàn (xanh / cam / đỏ), đèn cảnh báo xoay khi nguy hiểm.
- **📡 Camera** — lưới camera server (MJPEG có vẽ skeleton), trạng thái (Đang chạy / Mất tín hiệu — thử lại / Khựng hình), FPS, số người, IQA. Bấm một camera để người 3D mô phỏng người đầu tiên của camera đó; bấm lại để thôi.
- **📋 Sự kiện** — lịch sử cảnh báo đã xác nhận: lọc theo loại / thời gian / chưa xử lý, thống kê và biểu đồ theo giờ, ảnh chụp (bấm để phóng to), nút **Xác nhận** (đã xử lý), **⬇ CSV**. Số đỏ trên tab = số sự kiện chưa xử lý trong 24 giờ.

Khi một cảnh báo được xác nhận (ngã ≥ 1.5 s, cúi sai ≥ 3 s, camera kém ≥ 5 s): toast góc phải (bấm để mở tab Sự kiện), còi (ngã: còi hú; còn lại: 2 tiếng bíp), thông báo desktop nếu tab đang ẩn.

### 3.1 Nguồn ở tab Giám sát
1. **OFFLINE (mặc định)** — kịch bản giả lập, không cần Python/MATLAB. Cảnh báo kịch bản chỉ hiện trên trình duyệt, không ghi vào nhật ký.

| Phím | Kịch bản | Kết quả |
|---|---|---|
| 1 | An toàn | Công nhân đứng, vòng xanh |
| 2 | Nâng đúng | Ngồi xổm nâng thùng, badge xanh |
| 3 | Cúi sai | Cúi gập lưng, đỏ; sau 3 s có cảnh báo |
| 4 | Ngã | Nằm trên sàn, đèn xoay; sau 1.5 s còi hú |
| 5 | Cháy | Lửa cạnh công nhân, alert "LỬA" |
| 6 | Bụi | Bụi/khói, alert "BỤI + KHÓI" |
| 7 | Tối | IQA tụt ~28, "THIẾU SÁNG" |
| 8 | Che cam | IQA ~14 |

   `Space` hoặc nút **Tự động chạy**: đổi kịch bản mỗi 4 giây.

2. **VIDEO/CAMERA + AI (MediaPipe trong trình duyệt)** — bấm **AI Detect** (`A`, chờ 3–8 giây tải lần đầu) → bấm **Camera** hoặc **Video**. Skeleton bám người thật, người 3D làm theo tư thế. Nếu đã kết nối backend, cảnh báo xác nhận được gửi lên nhật ký kèm ảnh (nguồn `browser`).

3. **SERVER (Python)** — bấm **Camera**/**Video** rồi **Server** (địa chỉ WebSocket được điền tự động khi đã kết nối backend). Dùng YOLOv8-Pose + tracking + xác nhận cảnh báo trên server.

### 3.2 Phím & nút
| Phím | Chức năng |
|---|---|
| `1`–`8` | Chọn kịch bản |
| `Space` | Tự động chạy |
| `A` | Bật/tắt AI Detect (MediaPipe) |
| `B` | Panel benchmark (FPS, thời gian PIQE, tương quan) |
| `C` | Thanh so sánh trước/sau |
| `P` | Xuất báo cáo HTML |
| `R` | Reset |
| `T` | Self-test 18 bước |

Các nút khác: **Log** (xuất nhật ký JSON), **📂 Nạp** (nạp JSON từ MATLAB), **🎭 Demo** (JSON demo), **✕** (xoá JSON).

### 3.3 Kết nối MATLAB → web
1. **Tự động (mặc định, nút 🔄 Tự động: BẬT)**: khi backend đang chạy, web hỏi `/matlab_iqa` mỗi 2 giây; backend đọc file `output/*_iqa.json` mới nhất nên MATLAB chạy xong là web tự hiện, không cần chọn file. Chưa có backend thì dòng trạng thái báo "chờ backend".
2. Thủ công (khi không chạy backend): **📂 Nạp** → chọn JSON; trên Chrome/Edge trang theo dõi file và cập nhật mỗi giây. Nạp tay, **🎭 Demo** hoặc **✕** sẽ tắt chế độ tự động; bấm 🔄 để bật lại.

## 4. Backend Python
```bash
make run                                   # AI nếu có model, ngược lại demo
make demo                                  # ép chế độ demo
curl http://localhost:8000/health
```
Phản hồi `/health` mẫu:
```json
{"status":"ok","demo_mode":false,"yolo":true,"hands":true,"version":"21.0.0","piqe_mode":"both","matlab_dir":".../output","cameras":2,"events_db":true,"notify":["telegram"]}
```
Cấu hình bằng biến môi trường `ECHO_*` (xem [.env.example](../.env.example)):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `ECHO_PORT` | 8000 | Cổng server |
| `ECHO_DEMO_MODE` | 0 | `1` = không nạp YOLO |
| `ECHO_SERVER_FPS` | 20 | Giảm xuống 15 nếu máy yếu |
| `ECHO_MAX_PERSONS` | 5 | Số người tối đa |
| `ECHO_PIQE_MODE` | both | `fast` / `full` / `both` |
| `ECHO_PIQE_SAMPLE_N` | 30 | Tính PIQE full mỗi N frame |
| `ECHO_MATLAB_DIR` | `./output` | Thư mục JSON của MATLAB |
| `ECHO_CAMERAS` | (trống) | Camera server, `tên=nguồn` cách nhau dấu phẩy |
| `ECHO_CAMERAS_FILE` | (trống) | File JSON danh sách camera |
| `ECHO_CAMERA_FPS` | 10 | Số frame phân tích mỗi giây cho mỗi camera |
| `ECHO_FALL_CONFIRM_S` / `ECHO_POSTURE_CONFIRM_S` / `ECHO_QUALITY_CONFIRM_S` | 1.5 / 3 / 5 | Thời gian điều kiện phải kéo dài trước khi cảnh báo |
| `ECHO_ALERT_COOLDOWN_S` | 30 | Không lặp cùng cảnh báo cho cùng người trong khoảng này |
| `ECHO_DATA_DIR` | `./output` | Nơi lưu `echo.db` và `snapshots/` |
| `ECHO_RECORD_BROWSER_EVENTS` | 1 | Ghi cả cảnh báo từ chế độ Server / AI trình duyệt |
| `ECHO_TELEGRAM_TOKEN`, `ECHO_TELEGRAM_CHAT_ID` | (trống) | Bật thông báo Telegram |
| `ECHO_WEBHOOK_URL` | (trống) | Bật webhook JSON |
| `ECHO_WEB_DIR` | tự tìm `web/` | Thư mục giao diện phục vụ tại `/` |

Dừng server: `Ctrl+C`. Thiếu YOLO hoặc lỗi nạp model → tự chuyển DEMO (có log cảnh báo).

### 4.1 Camera IP (RTSP), webcam USB, file video
```bash
# Camera IP Hikvision/Dahua/... (luồng phụ độ phân giải thấp là đủ và nhẹ hơn)
export ECHO_CAMERAS="kho=rtsp://admin:matkhau@192.168.1.64:554/Streaming/Channels/102"
# Nhiều nguồn: RTSP + webcam USB số 0 + file video (tự lặp, hợp để demo)
export ECHO_CAMERAS="kho=rtsp://...,cong=0,demo=data/demo.mp4"
make run
```
Hoặc file JSON (`ECHO_CAMERAS_FILE=cameras.json`): `{"kho": "rtsp://...", "cong": 0}` hoặc `[{"id": "kho", "source": "rtsp://..."}]`.

- Kiểm tra URL trước bằng VLC (*Media → Open Network Stream*). Mật khẩu được che (`rtsp://***@...`) trong log và API.
- Mất kết nối → trạng thái *Mất tín hiệu — thử lại*, server tự kết nối lại sau 1, 2, 4 … tối đa 30 s.
- Server luôn phân tích frame **mới nhất** (không bị trễ dồn); máy yếu thì giảm `ECHO_CAMERA_FPS` (ví dụ 5).
- YOLO dùng chung cho mọi camera; CPU xử lý được khoảng 5–10 frame/giây tổng cộng, GPU nhiều hơn nhiều.
- Docker: camera USB cần thêm `devices: ["/dev/video0:/dev/video0"]` vào compose (Linux); RTSP không cần gì thêm.

### 4.2 Thông báo Telegram / webhook
1. Chat với **@BotFather** → `/newbot` → nhận token `123456:ABC...`.
2. Thêm bot vào nhóm (hoặc nhắn riêng cho bot), mở `https://api.telegram.org/bot<TOKEN>/getUpdates` để lấy `chat.id` (nhóm có dạng `-100...`).
3. `export ECHO_TELEGRAM_TOKEN=... ECHO_TELEGRAM_CHAT_ID=...` rồi chạy lại server; `/health` sẽ có `"notify": ["telegram"]`.

Mỗi cảnh báo gửi 1 tin kèm ảnh có vẽ skeleton. Webhook (`ECHO_WEBHOOK_URL`) nhận POST JSON `{"event": {...}, "text": "..."}` — dùng cho Slack/Teams/Zalo qua dịch vụ trung gian, hoặc hệ thống riêng. Gửi chạy nền, thử lại 3 lần; lỗi mạng không làm chậm xử lý video.

### 4.3 Nhật ký sự kiện
SQLite tại `output/echo.db` (bảng `events`), ảnh tại `output/snapshots/`. Sao lưu: copy cả thư mục `output/`. Xem/xuất trong tab **Sự kiện** hoặc API (`/api/events`, `/api/events.csv`, `/api/stats` — xem [ARCHITECTURE.md](ARCHITECTURE.md)).

## 5. MATLAB
1. Mở MATLAB, `cd matlab`, mở `run_iqa_engine.m`, Run (F5).
2. Chọn video; huỷ chọn → chạy dữ liệu tổng hợp. Cấu hình ở [matlab/config.m](../matlab/config.m) (`piqeMode`, `piqeSampleN`, `demoMode`, `outputDir`…).
3. Chín biểu đồ: Gốc · Canny · Laplacian · Nhiễu (wavelet nếu có) · Histogram · Cân bằng histogram · Timeline IQA · Otsu · So sánh PIQE fast/full (kèm hệ số tương quan).
4. Xuất ra `output/`: `<video>_iqa.json` (summary + per-frame), `<video>_iqa.csv`, `<video>_report.png`.

| PIQE mode | Dùng khi |
|---|---|
| `fast` | Demo realtime |
| `full` | Cần độ chính xác block-wise |
| `both` | Khuyến nghị — có cả hai để so sánh |

Chạy test: `runtests('matlab/tests')`.

## 6. Troubleshooting
| Triệu chứng | Nguyên nhân / cách sửa |
|---|---|
| Web: trang trắng | F12 → Console xem lỗi |
| Web: loading mãi | CDN Three.js không tải được → kiểm tra mạng |
| Panel 3D đen | WebGL không khả dụng → đổi Chrome/Edge, bật hardware acceleration |
| "MediaPipe không tải được" | Cần internet lần đầu; dùng kịch bản 1–8 thay thế |
| Camera `NotAllowedError` | Cấp quyền ở `chrome://settings/content/camera`; đóng Zoom/Meet |
| Video không phát | Chuyển codec H.264 bằng ffmpeg |
| `ModuleNotFoundError` | Chưa `make install` |
| `Address already in use` | Đổi `ECHO_PORT` |
| YOLO lỗi torch | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| Web báo lỗi kết nối Python | Backend chưa chạy / sai port / firewall |
| "Chưa kết nối backend" ở tab Camera/Sự kiện | Chạy `make run`, bấm **Thử kết nối lại**; mở trang qua `http://localhost:8000` |
| Camera "Mất tín hiệu — thử lại" mãi | Sai URL/mật khẩu RTSP, camera khác mạng; thử URL bằng VLC |
| Hình camera trễ / FPS thấp | Dùng luồng phụ (sub-stream) của camera, giảm `ECHO_CAMERA_FPS` |
| Không nghe còi | Bấm vào trang 1 lần (trình duyệt chặn âm thanh trước khi người dùng tương tác); kiểm tra nút 🔔 |
| Không nhận Telegram | Kiểm tra `/health` có `"telegram"`; bot đã được thêm vào nhóm; xem log `notification failed` |
| Người 3D hiện dạng khối đơn giản | Không tải được mô hình GLTF/WebGL → fallback; kiểm tra Console |
| MATLAB `Undefined function` | Thiếu Image Processing Toolbox (đã có fallback cho phần lớn hàm) |
| MATLAB chậm | `cfg.piqeMode='fast'`, `cfg.piqeSampleN=60` |
| JSON MATLAB không hiện | Kiểm tra `cfg.outputDir` trùng `ECHO_MATLAB_DIR` |

Khi báo lỗi, kèm: dòng đỏ trong Console, phiên bản Chrome (`chrome://version`), `python --version`, hệ điều hành.

## 7. FAQ
- **Có cần internet khi demo?** Không, chỉ lần đầu tải thư viện/model.
- **Có cần GPU?** Không; YOLO trên CPU ~5–10 FPS.
- **Có cần MATLAB?** Không bắt buộc; MATLAB dùng cho phân tích offline và bridge JSON.
- **Chạy máy khác?** Copy thư mục, cài Python + Chrome.
- **Tại sao 3 ngôn ngữ?** Mỗi tầng làm đúng việc: MATLAB (phân tích offline, biểu đồ), Python (AI realtime), HTML/JS (UI, 3D, demo offline).

## 8. Deploy: web trên GitHub Pages + backend trên Colab
1. **Bật Pages một lần:** repo → Settings → Pages → Source = *GitHub Actions*. Mỗi lần push sửa `web/` workflow `pages.yml` tự deploy tới `https://fsb-msa36hn.github.io/echo-move/`.
2. **Chạy backend:** mở `notebooks/colab_backend.ipynb` trên Colab (Open in Colab → GitHub → `FSB-MSA36HN/echo-move`), chọn Runtime GPU, chạy lần lượt các cell.
3. Cell cuối in ra link dạng `https://fsb-msa36hn.github.io/echo-move/?server=https://xxxx.trycloudflare.com`. Mở link đó → web tự dùng `wss://xxxx.trycloudflare.com/ws/pose`, bấm **Server** → **Camera**.
4. Địa chỉ server được nhớ trong trình duyệt; dùng `?server=local` để quay về `localhost:8000`.

Lưu ý: URL tunnel đổi mỗi lần chạy lại notebook; phiên Colab miễn phí tự tắt sau một thời gian không hoạt động. Repo cần public (hoặc plan hỗ trợ Pages private).
