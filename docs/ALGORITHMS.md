# Thuật toán

Mọi điểm IQA nằm trong 0–100 (cao = tốt). `gray` là ảnh xám trong [0,1].

| Metric | Công thức (cài đặt) | Nguồn |
|---|---|---|
| Blur | `min(Var(Laplacian(gray_u8)) / 10, 100)` | Pech-Pacheco et al., 2000 |
| Noise | `max(100 − 4·σ̂, 0)` với σ̂ kiểu Immerkær (mặt nạ Laplacian 3×3 trên ảnh ×255) | Immerkær, 1996 |
| Contrast | `min(400·std(gray), 100)` (RMS contrast) | Peli, 1990 |
| PIQE (full) | chia khối 16×16 trên MSCN, bỏ khối phẳng (var<0.1), khối var>0.5 trọng số 2, `100 − 180·điểm_trung_bình` | Venkatanath et al., 2015 (xấp xỉ) |
| "PIQE fast" | `100 − 100·std(MSCN)` toàn ảnh | **không phải PIQE gốc**; proxy nhanh — lưu ý: có thể tăng khi ảnh mờ |
| Exposure | `max(100 − 1000·(tỉ lệ >0.95 + tỉ lệ <0.05), 0)` | ISO 18434-1 (tinh thần) |

**Overall** = `0.05·PIQE + 0.50·Blur + 0.20·Contrast + 0.15·Noise + 0.10·Exposure` (mặc định sau hiệu chỉnh). Hệ số scale (10, 400, 4, 180) là thực nghiệm.

Trọng số được **tìm kiếm và kiểm chứng** bằng `make calibrate-iqa`:
1. Sinh cảnh nhà xưởng + (tuỳ chọn) ảnh thật trong `data/iqa_clean/`.
2. Áp suy giảm có kiểm soát (blur / noise / contrast / exposure / mixed, severity 0–4).
3. Tìm trọng số trên simplex với mục tiêu vận hành: F1 của ngưỡng `Overall < 40` để bắt severity ≥ 3, ràng buộc `keep_clean ≥ 0.95` (không báo nhầm ảnh sạch).
4. Báo cáo: `output/iqa_calib/report.md`. Trọng số tốt được ghi cố định vào `Settings.iqa_weights`.

Blur được trọng số cao vì PIQE-fast có thể *tăng* khi ảnh mờ (std MSCN giảm) — nếu PIQE nặng bằng Blur thì Overall không giảm khi camera mất nét.

Pipeline realtime chỉ đưa PIQE fast vào Overall. PIQE full (khối 16×16) không chạy trên camera; dùng `make bench` để đo tương quan fast↔full và `calibrate-iqa --full-piqe` khi muốn hiệu chỉnh bằng điểm khối.

> Lưu ý trung thực: PIQE là bản xấp xỉ; tối ưu là trên dataset suy giảm có kiểm soát (không phải MOS người xem trên toàn bộ ảnh hiện trường). Chạy lại `make calibrate-iqa` khi đổi camera/miền.

## Phân loại tư thế theo từng frame (COCO-17, toạ độ chuẩn hoá)
Năm kỹ thuật / sự kiện: **PARTIAL**, **FALL**, **SQUAT**, **STOOP**, **STANDING** (`pose/classifier.py`, cùng luật trong `web/js/app.js`).

- Trước khi tính góc, `x` được nhân với tỉ lệ khung hình `W/H` (toạ độ chuẩn hoá làm méo góc: khung 16:9 lệch góc lưng tới ~40 %).
- `spine` = `atan2(|x_vai − x_hông|, |y_vai − y_hông|)` (độ so với phương thẳng đứng).
- `knee` = trung bình góc hông–gối–cổ chân hai bên (180° nếu thiếu điểm).
- `bbox_ratio` = rộng / cao của khung bao các keypoint nhìn thấy.
- Thứ tự luật:
  1. **PARTIAL** — YOLO/MediaPipe chỉ thấy một phần cơ thể: &lt; 8 joint conf đủ, thiếu vai/hông, hoặc bbox sát mép + &lt; 2 chân.
  2. **FALL** — ngã đa tín hiệu (xem dưới).
  3. **SQUAT** — `knee < 140°` và `spine < 45°` (ngồi xổm).
  4. **STOOP** — `spine > 60°` (cúi khom).
  5. **STANDING** — còn lại (đứng thẳng).

### Ngã đa tín hiệu (`pose/classifier.py` + `pose/fall.py`)
Luật "nằm ngang" bỏ sót khi người ngã **về phía** camera: thân co ngắn nên góc lưng nhỏ. Ba tín hiệu:
- **lying**: thân lớn hơn 65° và khung rộng hơn cao.
- **head_low**: `y_đầu > y_hông − 0.15·chiều_cao_khung`.
- **collapsed**: chiều cao hiện tại &lt; 50 % chiều cao lúc đứng của track **và** hông rơi &gt; 20 %.

FALL khi ≥ 2 tín hiệu, hoặc lying mà không thấy đầu. SQUAT không bị nâng thành FALL dù chiều cao giảm. `ECHO_FALL_MULTISIGNAL=0` quay về chỉ dùng lying.

### REBA rút gọn (metric, không còn event)
Điểm REBA 1–15 vẫn trả trong `safety.reba` (bảng A/B/C, Hignett & McAtamney 2000) để hiển thị / phân tích — **không** phát sự kiện ERGO.

### Vùng nguy hiểm và PPE (metric / overlay, không còn event)
Vùng polygon và PPE vẫn có thể tính/vẽ trên MJPEG; **không** phát sự kiện ZONE/PPE. Event chỉ còn 5 loại tư thế ở trên.

## Tracking nhiều người
`PoseTracker` theo kiểu ByteTrack (Zhang 2022) và bỏ Kalman vì pose đã được làm mượt. Mỗi detection lấy khung bao keypoint, điểm tin cậy là trung bình confidence của các keypoint.
1. **Hai tầng**: detection mạnh (≥ 0.5) được ghép trước. Detection yếu (0.2–0.5, thường do bị che một phần) chỉ được dùng để nối tiếp track còn trống và không bao giờ tạo track mới.
2. **Dự đoán chuyển động**: mỗi track giữ vận tốc tâm (EMA). Điểm ghép là max(IoU với khung dự đoán, IoU với khung cuối), nên người đi nhanh vẫn giữ ID.
3. **Ghép theo tâm có giới hạn**: khi IoU bằng 0, ví dụ người ngã đột ngột làm khung từ đứng thành nằm, vẫn ghép nếu tâm cách nhau dưới max(0.12, 0.6 × đường chéo khung).
4. Track không xuất hiện quá 1.5 s thì bị xoá.

Không dùng `model.track` của Ultralytics vì một model dùng chung cho mọi camera sẽ trộn trạng thái tracking giữa các camera. Mỗi track giữ một `KeypointSmoother` riêng (One-Euro, min_cutoff=1, beta=0.007, reset khi mất dấu > 1 s).

## Xác nhận cảnh báo theo thời gian
Phân loại từng frame nhiễu (che khuất, mờ chuyển động, ngồi xổm 1 giây), nên cảnh báo chỉ phát khi điều kiện **kéo dài** (`alerts/engine.py`, cùng luật trong `web/js/alerts.js`):

| Loại | Điều kiện mỗi frame | Phải kéo dài | Mức |
|---|---|---|---|
| FALL | `technique = FALL` | `ECHO_FALL_CONFIRM_S` = 1.5 s (0.75 s nếu hông rơi nhanh) | CRITICAL · ảnh + clip |
| STOOP | `technique = STOOP` | `ECHO_POSTURE_CONFIRM_S` = 3 s | WARNING · ảnh + clip |
| SQUAT | `technique = SQUAT` | `ECHO_POSTURE_CONFIRM_S` = 3 s | INFO · ảnh + clip |
| STANDING | `technique = STANDING` | **0 s** (ghi ngay) | INFO · log-only, không ảnh, tự ack |
| PARTIAL | YOLO partial body | **0 s** (ghi ngay) | WARNING · log-only, không ảnh, tự ack |

`PARTIAL` dùng conf keypoints YOLOv8-Pose (vai+hông, ≥ 8 joint, hoặc bbox sát mép + thiếu chân).

- Mỗi (loại, track ID) là một "episode": mất điều kiện < 0.5 s không reset (chịu được vài frame lỗi); một episode chỉ phát 1 lần.
- **Hông rơi nhanh**: trong 1.5 s gần nhất, `y_hông` tăng hơn 25 % chiều cao khung người lớn nhất → khả năng ngã thật cao, nên rút ngắn thời gian xác nhận một nửa.
- Cooldown `ECHO_ALERT_COOLDOWN_S` = 30 s cho mỗi (loại, người) để không spam Telegram.
- Track biến mất > 5 s thì xoá trạng thái.

## Dựng người 3D từ keypoint 2D (`web/js/human3d.js`)
1. **Mô hình**: Xbot (Mixamo, xương `mixamorig*`, cao 1.8 m). Đồ bảo hộ tô bằng shader theo vị trí đỉnh ở tư thế gốc (bind pose): vùng da, găng, áo phản quang + 2 dải phản quang (phát sáng theo mức an toàn), áo, thắt lưng, quần, ủng; mũ cứng và mặt là mesh gắn vào xương đầu.
2. **Chiều sâu**: ước lượng số đơn vị ảnh / mét `u` từ đoạn ít bị co ngắn nhất (thân, đùi, cẳng chân, vai so với chiều dài chuẩn). Mỗi đoạn có độ dài ảnh `l` và độ dài thật `L` thì độ lệch sâu `dz = L·√(1 − (l / 0.88L)²)`; dấu chọn theo giải phẫu (gối ra trước, cẳng chân về sau). Nếu có MediaPipe world landmarks thì dùng trực tiếp toạ độ 3D.
3. **Retarget**: hệ trục thân từ (hông → vai, trái → phải); với mỗi xương, quaternion `setFromUnitVectors(hướng_gốc, hướng_mới)` trong hệ của xương cha; nội suy `slerp` để mượt; chân đặt phẳng khi đứng, toàn thân hạ xuống chạm sàn.
4. Không có WebGL/Three.js → người dựng bằng hình khối cùng tên xương; vẫn lỗi → vẽ 2D.

## Đánh giá trên dataset (`make eval`)
`scripts/evaluate.py` và `echo_move/evaluation.py` hoạt động theo hai bước:
1. **Trích keypoint**: YOLO chạy một lần cho mỗi video và kết quả được cache trong `output/eval_cache/<dataset>/`.
2. **Phát lại**: keypoint đi qua tracker, classifier, `FallAnalyzer` và `AlertEngine` với từng cấu hình luật (v21 so với đa tín hiệu). Nhờ có cache, thay ngưỡng chỉ tốn vài giây.

Một video dương tính được tính là phát hiện đúng nếu có FALL trong khoảng `[bắt đầu ngã − 2 s, kết thúc + 2 s]`. Le2i có nhãn frame trong `Annotation_files`. UR Fall dùng tên file (`fall-*` / `adl-*`). Thư mục tự do dùng `labels.csv`. Kết quả gồm precision, recall, F1, độ trễ phát hiện (trung vị, p90) và số báo nhầm/giờ trên video ADL, ghi ra `output/eval_<dataset>.json` cùng bảng Markdown.

## Hạn chế đã biết
- Luật tư thế dựa trên 2D, nhạy với góc camera (camera nên đặt cao 2–3 m, nhìn chéo xuống).
- Tracker có dự đoán vận tốc nhưng không có đặc trưng ngoại hình (re-ID): hai người mặc giống nhau đi sát và che nhau lâu vẫn có thể đổi ID.
- Tín hiệu "sụp người" cần track đã thấy người đó đứng ≥ 5 frame. Người vào khung hình khi đã nằm thì chỉ dựa vào lying và head_low.
- PARTIAL dựa trên conf keypoints / mép khung — người xa camera hoặc che khuất mạnh vẫn có thể false positive/negative.
- Ngưỡng thời gian, góc và hệ số IQA là giá trị thực nghiệm, cần hiệu chỉnh trên dữ liệu nhà xưởng thật.
- Chiều sâu 3D chỉ là ước lượng (một camera); hướng trước/sau của chi có thể sai khi chi song song trục camera.
