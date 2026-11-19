# Deploy VPS (demo tạm)

Stack **chỉ bổ sung**, không đụng nginx / aaPanel / MySQL / site khác.

| Mục | Giá trị |
|---|---|
| Host | `http://51.222.86.7:18080` |
| Thư mục | `/home/ubuntu/apps/echo-move` |
| Compose project | `echo-move` |
| Container | `echo-move-backend` |
| Port host | `18080` → container `8000` |

## Mở UI

```text
http://51.222.86.7:18080/
http://51.222.86.7:18080/health
http://51.222.86.7:18080/presentation/
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

Hoặc one-liner từ máy local (điền token thật):

```bash
export SSHPASS='…'   # chỉ dùng local, không commit
sshpass -e ssh ubuntu@51.222.86.7 'cd /home/ubuntu/apps/echo-move && \
  printf "\nECHO_TELEGRAM_TOKEN=%s\nECHO_TELEGRAM_CHAT_ID=%s\n" "TOKEN" "CHAT" >> .env && \
  sudo docker compose -p echo-move -f docker/docker-compose.vps.yml --env-file .env up -d'
```

Biến quan trọng: `ECHO_WITH_AI`, `ECHO_DEMO_MODE`, `ECHO_CAMERAS`, `ECHO_TELEGRAM_*`, `ECHO_ZALO_*`, `ECHO_CORS_ORIGINS`.

## CI/CD (GitHub Actions)

1. Tạo deploy key (một lần trên máy bạn):

```bash
ssh-keygen -t ed25519 -f echo-move-vps -N "" -C "echo-move-deploy"
# Public → VPS
ssh-copy-id -i echo-move-vps.pub ubuntu@51.222.86.7
# hoặc: cat echo-move-vps.pub | ssh ubuntu@51.222.86.7 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'
```

2. Repo GitHub → **Settings → Secrets and variables → Actions**:

| Secret | Nội dung |
|---|---|
| `VPS_HOST` | `51.222.86.7` |
| `VPS_USER` | `ubuntu` |
| `VPS_SSH_KEY` | toàn bộ file private `echo-move-vps` (kể cả dòng BEGIN/END) |

3. Push workflow `.github/workflows/deploy-vps.yml` lên `main` (bạn tự push — agent không push), hoặc chạy **Actions → Deploy VPS → Run workflow**.

## Xoá sau demo (chỉ stack này)

```bash
ssh ubuntu@51.222.86.7 'cd /home/ubuntu/apps/echo-move && \
  sudo docker compose -p echo-move -f docker/docker-compose.vps.yml down --rmi local && \
  sudo docker image rm echo-move-backend:demo 2>/dev/null; \
  rm -rf /home/ubuntu/apps/echo-move; \
  sudo ufw delete allow 18080/tcp 2>/dev/null; true'
```

Không chạy lệnh `docker system prune` toàn cục nếu còn container khác.
