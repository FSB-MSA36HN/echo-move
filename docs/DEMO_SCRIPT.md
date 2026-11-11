# Kịch bản demo & Q&A bảo vệ

## Chuẩn bị (5 phút trước)
- [ ] Tắt wifi để thử chế độ offline
- [ ] Chrome mở `web/index.html` (đã test)
- [ ] `make run` đang chạy (xem console)
- [ ] MATLAB mở `run_iqa_engine.m` (chưa Run)
- [ ] USB backup: mã nguồn + video + `yolov8n-pose.pt`

## Luồng 5 phút
| Phút | Người | Hành động | Kết quả |
|---|---|---|---|
| 0:00 | NV1 | MATLAB chọn `data/demo.mp4`, Run | 9 biểu đồ + `output/demo_iqa.json` |
| 0:30 | NV1 | Chỉ biểu đồ 9 | PIQE fast vs full + hệ số tương quan **đo được** |
| 0:45 | NV2 | `make run` | "AI MODE" hoặc "DEMO" |
| 1:00 | NV3 | Mở `index.html` | Robot 3D + laser xanh |
| 1:15 | NV3 | Bấm **Server** | Badge SERVER xanh |
| 1:30 | NV2 | Bấm **Camera** | Skeleton bám người thật |
| 2:00 | NV2 | Cúi sai tư thế | Badge đỏ "SAI TƯ THẾ" |
| 2:15 | NV2 | Nâng đúng | Badge xanh "NÂNG ĐÚNG KỸ THUẬT" |
| 2:30 | NV3 | Phím 1–8 | 8 kịch bản không cần diễn |
| 3:00 | NV3 | `B` | Panel benchmark |
| 3:15 | NV3 | `C` | Slider trước/sau |
| 3:30 | NV3 | `P` | Tải báo cáo HTML |
| 3:45 | NV2 | Ctrl+C backend | Web tự về OFFLINE |
| 4:00 | NV3 | Phím 4 | Demo ngã không cần AI |
| 4:15 | NV3 | `T` | Self-test |
| 4:30 | NV1 | Mở JSON MATLAB | Chứng minh bridge |

## Câu hỏi thường gặp
> Số liệu trong phần trả lời phải là số **bạn tự đo** (`make bench`, MATLAB subplot 9). Các con số "22×", "r=0.85", "50 ảnh nhà xưởng" trong tài liệu cũ chưa được xác minh bằng mã nguồn — đừng dùng nếu chưa có dữ liệu.

**PIQE của em là gì?** Hai phiên bản: *full* — xấp xỉ block-wise theo Venkatanath 2015; *fast* — thống kê MSCN toàn ảnh, rẻ hơn, dùng cho realtime. Em đo tương quan giữa hai bản trên video của em (MATLAB subplot 9 / `make bench`).

**Tối ưu hoá gì?** PIQE full chỉ tính 1/30 frame; vector hoá thay vòng lặp khối; vẽ biểu đồ mỗi 5 frame; suy luận chạy ngoài event loop. Đo bằng panel Benchmark (`B`).

**Pech-Pacheco dùng cho kính hiển vi, sao dùng cho nhà xưởng?** Variance of Laplacian là thước đo độ sắc nét độc lập miền ảnh; em dùng như chỉ báo tương đối (ảnh mờ/bụi → giá trị giảm), cần hiệu chỉnh ngưỡng theo camera thực.

**Mất mạng?** Ba tầng dự phòng: MediaPipe trong trình duyệt (đã tải) → kịch bản preset → khi Python tắt, web tự về OFFLINE.

**Camera bị che?** Bấm `8` hoặc che thật: IQA tụt <30, cảnh báo đỏ. IQA không chỉ hiển thị mà kích hoạt cảnh báo an toàn.

**Câu hỏi khó chưa biết?** Trả lời trung thực: "Phần này em chưa nghiên cứu sâu; hướng tiếp cận của em là X, em sẽ tìm hiểu thêm."

## Nếu demo hỏng giữa chừng
F5 tải lại → `T` để chứng minh hệ thống ổn → phím `1` (offline) → mở video quay sẵn trong USB.
