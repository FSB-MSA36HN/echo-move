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
- Kiểm tra nhanh: mở `web/index.html` → đợi ~2 giây → bấm `1` (robot + laser xanh) → bấm `T` (self-test, kỳ vọng ≥16/18 pass).

## 3. Giao diện web
Mở `web/index.html` bằng Chrome/Edge. Cột trái: video, điều khiển, thông số. Cột phải: robot 3D + 4 tia laser. Thanh dưới: debug realtime. Địa chỉ backend sửa tại [web/js/config.js](../web/js/config.js).

### 3.1 Ba chế độ
1. **OFFLINE (mặc định)** — kịch bản giả lập, không cần Python/MATLAB.

| Phím | Kịch bản | Kết quả |
|---|---|---|
| 1 | An toàn | Robot đứng, laser xanh |
| 2 | Nâng đúng | Robot cúi gối, badge xanh |
| 3 | Cúi sai | Laser đỏ |
| 4 | Ngã | Robot nằm ngang, cảnh báo đỏ |
| 5 | Cháy | Alert "LỬA" |
| 6 | Bụi | Alert "BỤI + KHÓI" |
| 7 | Tối | IQA tụt ~28, "THIẾU SÁNG" |
| 8 | Che cam | IQA ~14 |

   `Space` hoặc nút **Tự động chạy**: đổi kịch bản mỗi 4 giây.

2. **VIDEO/CAMERA + AI (MediaPipe trong trình duyệt)** — bấm **AI Detect** (`A`, chờ 3–8 giây tải lần đầu) → bấm **Camera** hoặc **Video**. Skeleton bám người thật, robot 3D mirror tư thế.

3. **SERVER (Python)** — chạy backend, nhập `ws://localhost:8000/ws/pose`, bấm **Server**; badge "SERVER" xanh. Dùng YOLOv8-Pose + MediaPipe Hands.

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
1. Qua Python (khuyến nghị): backend tự đọc `output/*_iqa.json` mới nhất và đẩy qua WebSocket.
2. Thủ công: **📂 Nạp** → chọn JSON; trên Chrome/Edge trang theo dõi file và cập nhật mỗi giây.

## 4. Backend Python
```bash
make run                                   # AI nếu có model, ngược lại demo
make demo                                  # ép chế độ demo
curl http://localhost:8000/health
```
Phản hồi `/health` mẫu:
```json
{"status":"ok","demo_mode":false,"yolo":true,"hands":true,"version":"20.0.0","piqe_mode":"both","matlab_dir":".../output"}
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

Dừng server: `Ctrl+C`. Thiếu YOLO hoặc lỗi nạp model → tự chuyển DEMO (có log cảnh báo).

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
