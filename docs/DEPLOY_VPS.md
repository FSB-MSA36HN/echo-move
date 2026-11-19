# Deploy VPS (demo tạm)

Stack **chỉ bổ sung** Docker `echo-move` trên port `18080`. Domain public dùng **nginx aaPanel** reverse proxy + Let's Encrypt (không đụng site khác).

| Mục | Giá trị |
|---|---|
| Domain (HTTPS) | `https://test.antokr.com` |
| Direct (nội bộ) | `http://127.0.0.1:18080` / `http://51.222.86.7:18080` |
| Thư mục | `/home/ubuntu/apps/echo-move` |
| Compose project | `echo-move` |
| Container | `echo-move-backend` |
| Port host | `18080` → container `8000` |
| Nginx vhost | `/www/server/panel/vhost/nginx/test.antokr.com.conf` |
| TLS cert | `/www/server/panel/vhost/cert/test.antokr.com/` (copy từ Let's Encrypt) |

## Mở UI

```text
https://test.antokr.com/
https://test.antokr.com/health
https://test.antokr.com/presentation/
```

HTTP tự redirect → HTTPS. Webcam trình duyệt hoạt động vì có secure context.

## Domain / TLS (đã setup)

DNS: `test.antokr.com` → `A 51.222.86.7`.

File mẫu trong repo: `deploy/nginx/test.antokr.com.conf` + `deploy/nginx/install-ssl-vhost.sh`.

- Certbot webroot: `/www/wwwroot/test.antokr.com`
- Renew hook copy cert vào đường dẫn aaPanel rồi reload nginx:
  `/etc/letsencrypt/renewal-hooks/deploy/echo-move-test-antokr.sh`

Kiểm tra:

```bash
curl -fsS https://test.antokr.com/health
curl -sI http://test.antokr.com/ | head -5   # Expect 301 → https
```

## Set env trên VPS

SSH rồi sửa `/home/ubuntu/apps/echo-move/.env` (file không nằm trong git):

```bash
ssh ubuntu@51.222.86.7
cd /home/ubuntu/apps/echo-move
nano .env
```

Ví dụ bật Telegram + camera file demo:

```bash
cat >> /home/ubuntu/apps/echo-move/.env <<'EOF'
ECHO_TELEGRAM_TOKEN=123456:ABC...
ECHO_TELEGRAM_CHAT_ID=-100...
# ECHO_CAMERAS=demo=/data/output/demo.mp4
EOF

cd /home/ubuntu/apps/echo-move
sudo docker compose -p echo-move -f docker/docker-compose.vps.yml --env-file .env up -d
```

Biến quan trọng: `ECHO_WITH_AI`, `ECHO_DEMO_MODE`, `ECHO_CAMERAS`, `ECHO_TELEGRAM_*`, `ECHO_CORS_ORIGINS`.

## Deploy

Không dùng GitHub Actions deploy VPS nữa — cập nhật trực tiếp lên `/home/ubuntu/apps/echo-move` (rsync/scp + `docker cp` / `docker compose up -d` khi đổi image). Domain HTTPS giữ nguyên qua nginx.

## Xoá sau demo (chỉ stack này)

```bash
ssh ubuntu@51.222.86.7 'cd /home/ubuntu/apps/echo-move && \
  sudo docker compose -p echo-move -f docker/docker-compose.vps.yml down --rmi local && \
  sudo docker image rm echo-move-backend:demo 2>/dev/null; \
  rm -rf /home/ubuntu/apps/echo-move; \
  sudo ufw delete allow 18080/tcp 2>/dev/null; true'
```

Gỡ domain (tuỳ chọn): xoá `/www/server/panel/vhost/nginx/test.antokr.com.conf`, cert, renew hook, rồi `nginx -s reload`.

Không chạy lệnh `docker system prune` toàn cục nếu còn container khác.
