Đặt video mẫu (`demo.mp4`) vào thư mục này. Video không được commit (xem `.gitignore`).
Chuyển định dạng: `ffmpeg -i input.mov -c:v libx264 -preset fast -crf 23 demo.mp4`
