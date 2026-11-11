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

## Phân loại tư thế theo từng frame (COCO-17, toạ độ chuẩn hoá)
- Trước khi tính góc, `x` được nhân với tỉ lệ khung hình `W/H` (toạ độ chuẩn hoá làm méo góc: khung 16:9 lệch góc lưng tới ~40 %).
- `spine` = `atan2(|x_vai − x_hông|, |y_vai − y_hông|)` (độ so với phương thẳng đứng).
- `knee` = trung bình góc hông–gối–cổ chân hai bên (180° nếu thiếu điểm).
- `bbox_ratio` = rộng / cao của khung bao các keypoint nhìn thấy.
- Thứ tự luật: thiếu điểm (vai/hông conf ≤ 0.25) → SAFE; `spine > 65°` **và** `bbox_ratio > 1` → **NGÃ**; `knee < 140°` và `spine < 45°` → **NÂNG ĐÚNG**; `spine > 60°` → **SAI TƯ THẾ**; `spine > 30°` → **CHÚ Ý**; còn lại SAFE. Ngưỡng ở `Settings`. Luật ngã cũ (`|y_vai − y_hông| < 0.08`) báo nhầm khi cúi sâu nên đã bỏ; điều kiện khung người nằm ngang loại trường hợp cúi gập người (lưng ngang nhưng chân vẫn thẳng đứng → khung cao).

## Tracking nhiều người
`PoseTracker` (kiểu SORT, Bewley 2016, bỏ Kalman vì pose đã được làm mượt): mỗi detection lấy khung bao keypoint; ghép tham lam theo điểm IoU, nếu IoU < 0.2 thì dùng khoảng cách tâm < 0.12 (điểm thấp hơn IoU); track không xuất hiện quá 1.5 s bị xoá. Mỗi track giữ một `KeypointSmoother` riêng (One-Euro, min_cutoff=1, beta=0.007, reset khi mất dấu > 1 s) nên nhiễu của người này không ảnh hưởng người khác và ID không đổi khi YOLO đổi thứ tự.

## Xác nhận cảnh báo theo thời gian
Phân loại từng frame nhiễu (che khuất, mờ chuyển động, ngồi xổm 1 giây), nên cảnh báo chỉ phát khi điều kiện **kéo dài** (`alerts/engine.py`, cùng luật trong `web/js/alerts.js`):

| Loại | Điều kiện mỗi frame | Phải kéo dài | Mức |
|---|---|---|---|
| FALL | `technique = FALL` | `ECHO_FALL_CONFIRM_S` = 1.5 s (0.75 s nếu hông rơi nhanh) | CRITICAL |
| POSTURE | `technique = IMPROPER` | `ECHO_POSTURE_CONFIRM_S` = 3 s | WARNING |
| CAMERA | IQA tổng < 40 | `ECHO_QUALITY_CONFIRM_S` = 5 s | WARNING |

- Mỗi (loại, track ID) là một "episode": mất điều kiện < 0.5 s không reset (chịu được vài frame lỗi); một episode chỉ phát 1 lần.
- **Hông rơi nhanh**: trong 1.5 s gần nhất, `y_hông` tăng hơn 25 % chiều cao khung người lớn nhất → khả năng ngã thật cao, nên rút ngắn thời gian xác nhận một nửa.
- Cooldown `ECHO_ALERT_COOLDOWN_S` = 30 s cho mỗi (loại, người) để không spam Telegram.
- Track biến mất > 5 s thì xoá trạng thái.

## Dựng người 3D từ keypoint 2D (`web/js/human3d.js`)
1. **Mô hình**: Xbot (Mixamo, xương `mixamorig*`, cao 1.8 m). Đồ bảo hộ tô bằng shader theo vị trí đỉnh ở tư thế gốc (bind pose): vùng da, găng, áo phản quang + 2 dải phản quang (phát sáng theo mức an toàn), áo, thắt lưng, quần, ủng; mũ cứng và mặt là mesh gắn vào xương đầu.
2. **Chiều sâu**: ước lượng số đơn vị ảnh / mét `u` từ đoạn ít bị co ngắn nhất (thân, đùi, cẳng chân, vai so với chiều dài chuẩn). Mỗi đoạn có độ dài ảnh `l` và độ dài thật `L` thì độ lệch sâu `dz = L·√(1 − (l / 0.88L)²)`; dấu chọn theo giải phẫu (gối ra trước, cẳng chân về sau). Nếu có MediaPipe world landmarks thì dùng trực tiếp toạ độ 3D.
3. **Retarget**: hệ trục thân từ (hông → vai, trái → phải); với mỗi xương, quaternion `setFromUnitVectors(hướng_gốc, hướng_mới)` trong hệ của xương cha; nội suy `slerp` để mượt; chân đặt phẳng khi đứng, toàn thân hạ xuống chạm sàn.
4. Không có WebGL/Three.js → người dựng bằng hình khối cùng tên xương; vẫn lỗi → vẽ 2D.

## Hạn chế đã biết
- Luật tư thế dựa trên 2D, nhạy với góc camera (camera nên đặt cao 2–3 m, nhìn chéo xuống).
- Tracker không có mô hình chuyển động: hai người đi sát và che nhau có thể đổi ID.
- Ngưỡng thời gian, góc và hệ số IQA là giá trị thực nghiệm, cần hiệu chỉnh trên dữ liệu nhà xưởng thật.
- Chiều sâu 3D chỉ là ước lượng (một camera); hướng trước/sau của chi có thể sai khi chi song song trục camera.
