Đặt video mẫu (`demo.mp4`) vào thư mục này. Video không được commit (xem `.gitignore`).
Chuyển định dạng: `ffmpeg -i input.mov -c:v libx264 -preset fast -crf 23 demo.mp4`

**Test theo từng tư thế:** xem `data/test_videos/README.md` — tải bằng `bash scripts/download_test_videos.sh`.
