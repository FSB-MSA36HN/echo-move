Đặt video mẫu (`demo.mp4`) vào thư mục này. Video không được commit (xem `.gitignore`).
Chuyển định dạng: `ffmpeg -i input.mov -c:v libx264 -preset fast -crf 23 demo.mp4`

**Test theo từng tư thế:** dùng `data/test_videos/curated/` (RGB 1 góc máy, không depth|RGB). Xem `data/test_videos/README.md` — tải lại: `bash scripts/download_test_videos.sh`.
