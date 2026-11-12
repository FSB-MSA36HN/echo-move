# Kịch bản demo & Q&A bảo vệ

## Chuẩn bị (5 phút trước)
- [ ] Tắt wifi để thử chế độ offline
- [ ] Chrome mở `web/index.html` (đã test)
- [ ] `ECHO_CAMERAS="demo=data/demo.mp4" make run` đang chạy (hoặc camera IP/USB thật); `/health` có `"cameras": 1`
- [ ] (Tuỳ chọn) Telegram đã cấu hình, điện thoại mở nhóm nhận cảnh báo
- [ ] MATLAB mở `run_iqa_engine.m` (chưa Run)
- [ ] USB backup: mã nguồn + video + `yolov8n-pose.pt`

## Luồng 6 phút
| Phút | Người | Hành động | Kết quả |
|---|---|---|---|
| 0:00 | NV1 | MATLAB chọn `data/demo.mp4`, Run | 9 biểu đồ + `output/demo_iqa.json` |
| 0:30 | NV1 | Chỉ biểu đồ 9 | PIQE fast vs full + hệ số tương quan **đo được** |
| 0:45 | NV2 | Mở <http://localhost:8000> | Chấm xanh "Backend v22 · AI · 1 cam", công nhân 3D đứng trong xưởng |
| 1:00 | NV3 | Phím `4` (Ngã) | Người 3D nằm xuống, đèn xoay; sau 1.5 s còi hú + toast |
| 1:20 | NV3 | Tab **Camera** | Lưới camera MJPEG có skeleton, FPS, IQA |
| 1:35 | NV3 | Bấm vào camera | Người 3D làm theo người trong camera |
| 2:00 | NV2 | Trước webcam: **Camera** → **Server**, cúi sai > 3 s | Badge đỏ, sau 3 s còi + toast; Telegram nhận ảnh (nếu bật) |
| 2:30 | NV2 | Nằm xuống (hoặc phím `4`) | Cảnh báo NGÃ (CRITICAL) |
| 2:40 | NV2 | Nằm yên thêm 10 s rồi đứng dậy | **Bất động sau ngã** (CRITICAL) → toast xanh **Đã đứng dậy** |
| 2:50 | NV3 | Tab **Sự kiện** | Sự kiện vừa rồi kèm ảnh, thống kê theo giờ; bấm **▶ Clip** (5 s trước + 5 s sau), **Xác nhận**, **Báo nhầm**, **⬇ CSV** |
| 3:10 | NV3 | Tab **Camera** → ⚙ → vẽ vùng quanh một góc sàn → Lưu | NV2 bước vào vùng → cảnh báo **Vùng cấm** |
| 3:30 | NV3 | Phím 1–8 | 8 kịch bản không cần diễn |
| 3:50 | NV3 | `B`, `C`, `P` | Benchmark, so sánh trước/sau, báo cáo HTML |
| 4:20 | NV2 | Rút dây mạng camera IP (hoặc đổi URL sai) | Trạng thái "Mất tín hiệu — thử lại"; sau 30 s có sự kiện **Mất tín hiệu camera**; cắm lại tự chạy tiếp |
| 4:50 | NV2 | Ctrl+C backend | Chấm xám "Chưa kết nối backend", web vẫn chạy offline |
| 5:10 | NV3 | `T` | Self-test |
| 5:30 | NV1 | Mở JSON MATLAB | Chứng minh bridge |

## Câu hỏi thường gặp
> Số liệu trong phần trả lời phải là số **bạn tự đo** (`make bench`, MATLAB subplot 9). Các con số "22×", "r=0.85", "50 ảnh nhà xưởng" trong tài liệu cũ chưa được xác minh bằng mã nguồn — đừng dùng nếu chưa có dữ liệu.

**PIQE của em là gì?** Hai phiên bản: *full* — xấp xỉ block-wise theo Venkatanath 2015; *fast* — thống kê MSCN toàn ảnh, rẻ hơn, dùng cho realtime. Em đo tương quan giữa hai bản trên video của em (MATLAB subplot 9 / `make bench`).

**Tối ưu hoá gì?** PIQE full chỉ tính 1/30 frame; vector hoá thay vòng lặp khối; vẽ biểu đồ mỗi 5 frame; suy luận chạy ngoài event loop; camera server luôn xử lý frame mới nhất (không dồn trễ). Đo bằng panel Benchmark (`B`).

**Sao không báo ngã ngay khi phát hiện?** Phân loại từng frame nhiễu (che khuất, cúi nhặt đồ). Em yêu cầu điều kiện kéo dài 1.5 s (0.75 s nếu hông rơi nhanh), chịu được mất dấu < 0.5 s, và cooldown 30 s mỗi người để không spam. Xem `docs/ALGORITHMS.md`.

**Nhiều người thì sao?** Tracker kiểu ByteTrack gán ID ổn định: ghép detection mạnh trước, detection yếu (bị che) sau, dự đoán vận tốc. Mỗi người có bộ lọc và bộ đếm thời gian riêng, và cảnh báo ghi rõ "người #ID".

**Ngã về phía camera thì sao?** Luật cũ chỉ nhìn góc thân nên bỏ sót. Bản 22 kết hợp 3 tín hiệu: nằm ngang, đầu thấp ngang hông, và chiều cao người sụp dưới 50 % so với lúc người đó đứng (hệ thống nhớ chiều cao đứng của từng track). FALL cần ít nhất 2 tín hiệu.

**Độ chính xác bao nhiêu?** Trả lời bằng số **tự đo**: `make eval DATASET=urfd` trên UR Fall (30 video ngã, 40 video sinh hoạt) cho precision, recall, F1, độ trễ phát hiện và số báo nhầm/giờ, so sánh luật cũ với luật mới. Chưa chạy thì nói rõ là chưa đo.

**Ngã xong người dậy được thì có còn báo không?** Có MANDOWN (vẫn nằm sau 10 s, kèm "bất động" hay "còn cử động") để ưu tiên cứu hộ, và RECOVERED (thông tin, không hú còi) khi đã đứng dậy. Sự kiện CRITICAL không ai xác nhận sau N phút sẽ được leo thang tới quản đốc.

**Quyền riêng tư?** Ảnh và clip lưu lại được làm mờ vùng đầu (`ECHO_BLUR_FACES=1`), dữ liệu tự xoá sau `ECHO_RETENTION_DAYS` ngày, chỉ xem trực tiếp mới thấy mặt.

**Người 3D lấy chiều sâu ở đâu khi chỉ có 1 camera?** Ước lượng từ độ co ngắn của chi so với chiều dài chuẩn (đoạn ít co nhất cho tỉ lệ ảnh/mét); MediaPipe có world landmarks thì dùng trực tiếp. Đây là ước lượng để trực quan hoá, luật cảnh báo vẫn dựa trên keypoint 2D.

**Pech-Pacheco dùng cho kính hiển vi, sao dùng cho nhà xưởng?** Variance of Laplacian là thước đo độ sắc nét độc lập miền ảnh; em dùng như chỉ báo tương đối (ảnh mờ/bụi → giá trị giảm), cần hiệu chỉnh ngưỡng theo camera thực.

**Mất mạng?** Bốn tầng dự phòng: camera server tự kết nối lại → MediaPipe trong trình duyệt (đã tải) → kịch bản preset → khi Python tắt, web tự về OFFLINE.

**Camera bị che?** Bấm `8` hoặc che thật: IQA tụt <30, sau 5 s thành sự kiện "Chất lượng camera kém". IQA không chỉ hiển thị mà kích hoạt cảnh báo an toàn.

**Câu hỏi khó chưa biết?** Trả lời trung thực: "Phần này em chưa nghiên cứu sâu; hướng tiếp cận của em là X, em sẽ tìm hiểu thêm."

## Nếu demo hỏng giữa chừng
F5 tải lại → `T` để chứng minh hệ thống ổn → phím `1` (offline) → mở video quay sẵn trong USB.
