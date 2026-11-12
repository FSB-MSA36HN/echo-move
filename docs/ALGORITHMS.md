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

### Ngã đa tín hiệu (v22, `pose/classifier.py` + `pose/fall.py`, cùng luật trong `web/js/app.js`)
Luật "nằm ngang" ở trên bỏ sót khi người ngã **về phía** camera: thân co ngắn nên góc lưng nhỏ và khung không nằm ngang. Vì vậy có thêm hai tín hiệu:
- **lying**: thân lớn hơn 65° và khung rộng hơn cao (luật v21).
- **head_low**: đầu thấp ngang hông, cụ thể `y_đầu > y_hông − 0.15·chiều_cao_khung`. Đầu là trung bình các điểm mũi, mắt và tai nhìn thấy.
- **collapsed**: `FallAnalyzer` giữ chiều cao lúc đứng của từng track (median của các frame đứng thẳng, cần ít nhất 5 mẫu). Tín hiệu bật khi chiều cao hiện tại nhỏ hơn 50 % chiều cao đó **và** hông đã rơi hơn 20 %.

Kết luận FALL khi có ít nhất 2 tín hiệu, hoặc khi lying và không thấy đầu. Ngồi xổm hay nâng đồ (gối gập) không bị nâng thành FALL dù sụp chiều cao. Đặt `ECHO_FALL_MULTISIGNAL=0` để quay về luật v21.

### REBA rút gọn
Từ một frame 2D tính điểm thân, cổ, chân, cánh tay trên và cẳng tay theo bảng A/B/C của REBA (Hignett & McAtamney 2000). Không có tải trọng, độ bám hay độ xoay cổ tay vì không đo được từ pose. Điểm 1–15 được trả trong `safety.reba`. **ERGO** là phơi nhiễm tích lũy: tổng thời gian có REBA ≥ `ECHO_ERGO_REBA` (6) trong cửa sổ 10 phút vượt `ECHO_ERGO_EXPOSURE_S` (60 s).

### Vùng nguy hiểm và PPE
- **Vùng**: polygon chuẩn hoá 0–1. Điểm chân là trung bình hai cổ chân, không có thì lấy đáy khung bao. Kiểm tra trong vùng bằng ray casting.
- **PPE** (`pose/ppe.py`): detection của model PPE được gán cho người có vùng đầu (mũ) hoặc vùng thân, từ vai đến hông (áo), chứa nhiều nhất diện tích hộp, tối thiểu 30 %. Lớp dương cho kết quả True. Lớp âm (`NO-Hardhat`, `head`...) hoặc không thấy gì trong vùng nhìn rõ cho kết quả False. Vùng không nhìn thấy cho None, không bao giờ báo.

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
| FALL | `technique = FALL` | `ECHO_FALL_CONFIRM_S` = 1.5 s (0.75 s nếu hông rơi nhanh) | CRITICAL |
| POSTURE | `technique = IMPROPER` | `ECHO_POSTURE_CONFIRM_S` = 3 s | WARNING |
| MANDOWN | vẫn FALL sau khi đã báo ngã (lệch ≤ 2 s không reset) | `FALL_CONFIRM_S + ECHO_MANDOWN_S` (10 s) | CRITICAL |
| RECOVERED | đã ngã, nay đứng / nâng / cúi nhẹ | 2 s | INFO (không còi) |
| ERGO | REBA ≥ 6 tích lũy trong 10 phút | ≥ 60 s | WARNING |
| ZONE | chân trong polygon vùng cấm | `dwell_s` của vùng (mặc định 1 s) | WARNING |
| PPE | thiếu đồ bắt buộc (`ECHO_PPE_REQUIRED`) | `ECHO_PPE_CONFIRM_S` = 5 s | WARNING |
| CAMERA | IQA tổng < 40 | `ECHO_QUALITY_CONFIRM_S` = 5 s | WARNING |
| OFFLINE | camera ở trạng thái reconnecting/stalled | `ECHO_OFFLINE_ALERT_S` = 30 s, mỗi lần mất 1 lần | WARNING |

MANDOWN ghi rõ "bất động" nếu chuyển động keypoint trung bình (EMA, đơn vị chiều cao người/giây) < 0.05, ngược lại "còn cử động".

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

Một video dương tính được tính là phát hiện đúng nếu có FALL trong khoảng `[bắt đầu ngã − 2 s, kết thúc + MANDOWN + 2 s]`. Le2i có nhãn frame trong `Annotation_files`. UR Fall dùng tên file (`fall-*` / `adl-*`). Thư mục tự do dùng `labels.csv`. Kết quả gồm precision, recall, F1, độ trễ phát hiện (trung vị, p90) và số báo nhầm/giờ trên video ADL, ghi ra `output/eval_<dataset>.json` cùng bảng Markdown.

## Hạn chế đã biết
- Luật tư thế dựa trên 2D, nhạy với góc camera (camera nên đặt cao 2–3 m, nhìn chéo xuống).
- Tracker có dự đoán vận tốc nhưng không có đặc trưng ngoại hình (re-ID): hai người mặc giống nhau đi sát và che nhau lâu vẫn có thể đổi ID.
- Tín hiệu "sụp người" cần track đã thấy người đó đứng ≥ 5 frame. Người vào khung hình khi đã nằm thì chỉ dựa vào lying và head_low.
- PPE phụ thuộc hoàn toàn vào chất lượng model PPE bên ngoài, và mũ ở xa camera (< 20 px) thường bị bỏ sót.
- Ngưỡng thời gian, góc và hệ số IQA là giá trị thực nghiệm, cần hiệu chỉnh trên dữ liệu nhà xưởng thật.
- Chiều sâu 3D chỉ là ước lượng (một camera); hướng trước/sau của chi có thể sai khi chi song song trục camera.
