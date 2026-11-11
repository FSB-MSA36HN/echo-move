# Thuật toán

Mọi điểm IQA nằm trong 0–100 (cao = tốt). `gray` là ảnh xám trong [0,1].

| Metric | Công thức (cài đặt) | Nguồn |
|---|---|---|
| Blur | `min(Var(Laplacian(gray_u8)) / 10, 100)` | Pech-Pacheco et al., 2000 |
| Noise | `max(100 − 1000·std(gray − Gaussian5×5(gray)), 0)` | biến thể của Immerkær, 1996 |
| Contrast | `min(400·std(gray), 100)` (RMS contrast) | Peli, 1990 |
| PIQE (full) | chia khối 16×16 trên MSCN, bỏ khối phẳng (var<0.1), khối var>0.5 trọng số 2, `100 − 180·điểm_trung_bình` | Venkatanath et al., 2015 (xấp xỉ) |
| "PIQE fast" | `100 − 100·std(MSCN)` toàn ảnh | **không phải PIQE gốc**; proxy nhanh dựa trên thống kê MSCN |
| Exposure | `max(100 − 1000·(tỉ lệ >0.95 + tỉ lệ <0.05), 0)` | ISO 18434-1 (tinh thần) |

**Overall** = `0.25·PIQE + 0.25·Blur + 0.20·Contrast + 0.15·Noise + 0.15·Exposure`. Trọng số và hệ số (10, 400, 1000, 180) là giá trị thực nghiệm, chưa được hiệu chỉnh trên dữ liệu nhà xưởng.

> Lưu ý trung thực khi báo cáo: PIQE ở đây là bản xấp xỉ đơn giản hoá, không so với cài đặt chuẩn của MATLAB (`piqe`). Pech-Pacheco/Immerkær/Peli được dùng ngoài miền gốc; ngưỡng cần kiểm chứng trên ảnh thực tế. Chạy `make bench` để đo tốc độ và tương quan fast↔full trên dữ liệu của bạn — đừng trích số liệu mẫu cũ trong tài liệu .docx (ví dụ "22×", "r=0.85") nếu chưa tự đo.

## Phân loại tư thế (COCO-17, toạ độ chuẩn hoá)
- `spine` = `atan2(|x_vai − x_hông|, |y_vai − y_hông|)` (độ so với phương thẳng đứng).
- `knee` = trung bình góc hông–gối–cổ chân hai bên (180° nếu thiếu điểm).
- Thứ tự luật: thiếu điểm (vai/hông conf ≤ 0.25) → SAFE; `|y_vai − y_hông| < 0.08` → **NGÃ**; `knee < 140°` và `spine < 45°` → **NÂNG ĐÚNG**; `spine > 60°` → **SAI TƯ THẾ**; `spine > 30°` → **CHÚ Ý**; còn lại SAFE. Ngưỡng ở `Settings`.
- Làm mượt keypoint: One-Euro (min_cutoff=1, beta=0.007), reset khi mất dấu >1 giây.

## Hạn chế đã biết
- Theo dõi người theo chỉ số (không tracking ID) nên ID có thể đổi khi thứ tự phát hiện thay đổi.
- Luật tư thế dựa trên 2D, nhạy với góc camera.
