# Video test cases (ECHO MOVE)

Dùng thư mục **`curated/`** — toàn bộ **1 góc máy**, không còn depth|RGB ghép 2 nửa.

| File | Kỳ vọng | Ghi chú |
|---|---|---|
| `curated/01_fall.mp4` | **FALL** | UR Fall cam0, **chỉ RGB** (đã cắt nửa depth) |
| `curated/01b_fall_alt.mp4` | **FALL** | Fall khác |
| `curated/02_standing.mp4` | **STANDING** | ADL RGB-only |
| `curated/03_squat.mp4` | **SQUAT** | Gym thật (CC0) — giống kiểu `stoop_demo` |
| `curated/04_stoop.mp4` | **STOOP** | Good mornings gym |
| `curated/05*_partial_*.mp4` | **PARTIAL** | Crop mất chân / mặt / mép |
| `curated/06_multiperson_hallway.mp4` | Nhiều người (lần lượt) | Intel — hành lang CCTV 1 góc |
| `curated/06b_multiperson_street.mp4` | Nhiều người / xe | Intel — bãi xe góc cao |
| `curated/06c_multiperson_room.mp4` | Người trong phòng | Intel — phòng góc cao |
| `curated/07_multiperson_then_fall.mp4` | Multi rồi FALL | Nối hallway → đoạn ngã RGB (demo flow) |

> File UR Fall gốc `*-cam0.mp4` là **depth \| RGB** (640×240) — script đã crop nửa phải. Đừng mở file raw nếu còn; chỉ dùng `curated/` hoặc `*_rgb.mp4` / `*_demo.mp4`.

## Cách test

1. UI → **Video** → chọn file trong `data/test_videos/curated/`
2. Bật **AI Detect**
3. FALL ≥ 1.5 s · SQUAT/STOOP ≥ 3 s · PARTIAL chỉ bbox vàng

## Tải / tạo lại

```bash
bash scripts/download_test_videos.sh
```

Script sẽ: tải UR Fall → **crop nửa phải (RGB)** → upscale 1280×720; tải squat/stoop CC0; tải Intel multi-person; tạo PARTIAL + `07_multiperson_then_fall`.

Nguồn: [UR Fall](https://fenix.ur.edu.pl/~mkepski/ds/uf.html) (mp4 gốc là depth\|RGB — không dùng trực tiếp), [workout-free-videos](https://github.com/namnq/workout-free-videos) (CC0), [intel-iot-devkit/sample-videos](https://github.com/intel-iot-devkit/sample-videos).
