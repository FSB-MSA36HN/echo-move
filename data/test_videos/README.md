# Video test cases (ECHO MOVE)

Clips để mở bằng nút **Video** trên UI (`https://test.antokr.com` hoặc local), bật AI Detect.

| File | Kỳ vọng | Nguồn |
|---|---|---|
| `fall_demo.mp4` / `fall_loop.mp4` / `fall-*-cam0.mp4` | **FALL** (≥ 1.5 s nằm) | [UR Fall](https://fenix.ur.edu.pl/~mkepski/ds/uf.html) |
| `standing_adl_demo.mp4` / `adl-*-cam0.mp4` | **STANDING** (chỉ tăng thống kê) | UR Fall ADL |
| `squat_demo.mp4` / `squat_deep_demo.mp4` | **SQUAT** (≥ 3 s) | [workout-free-videos](https://github.com/namnq/workout-free-videos) (CC0) |
| `stoop_demo.mp4` | **STOOP** (≥ 3 s cúi) | same — *good mornings* |
| `partial_no_legs.mp4` | **PARTIAL** bbox vàng, không alert | crop ADL (mất chân) |
| `partial_no_face.mp4` | **PARTIAL** | crop ADL (mất mặt) |
| `partial_edge.mp4` | **PARTIAL** | crop mép khung |

## Cách test nhanh

1. Backend chạy (`make run` hoặc VPS).
2. UI → **Video** → chọn file trong thư mục này.
3. Bật **AI Detect**; giữ tư thế đủ thời gian confirm.
4. PARTIAL: chỉ thấy bbox vàng `P# - Chỉ hiển thị một phần người`, không toast.
5. STANDING: ô **Đứng** trong thống kê tăng; không vào Danh sách & ảnh.

## Tải lại / thêm clip

```bash
bash scripts/download_test_videos.sh
```

Thêm UR Fall: `https://fenix.ur.edu.pl/~mkepski/ds/data/fall-XX-cam0.mp4` (01–30), `adl-XX-cam0.mp4` (01–40).

## Webcam (bổ sung)

| Hành động | Kỳ vọng |
|---|---|
| Đứng thẳng | STANDING (thống kê) |
| Ngồi xổm ≥ 3 s | SQUAT |
| Cúi khom lưng ≥ 3 s | STOOP |
| Nằm ≥ 1.5 s | FALL |
| Chỉ nửa người trong khung | PARTIAL bbox |

Video **không commit** (xem `.gitignore`).
