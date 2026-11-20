#!/usr/bin/env bash
# Deploy local repo → VPS. Edit/test locally first; never hot-patch only on the server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${ECHO_VPS_HOST:-ubuntu@51.222.86.7}"
KEY="${ECHO_VPS_KEY:-$HOME/.ssh/echo-move-vps-deploy}"
APP="${ECHO_VPS_APP:-/home/ubuntu/apps/echo-move}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -az --delete -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new")

cd "$ROOT"

echo "==> Sync local working tree → $HOST:$APP"
"${RSYNC[@]}" \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '**/__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache/' \
  --exclude 'output/' \
  --exclude 'data/test_videos/' \
  --exclude 'data/datasets/' \
  --exclude 'node_modules/' \
  "$ROOT/" "$HOST:$APP/"

echo "==> Rebuild + restart from synced tree (no docker cp hot-patch)"
"${SSH[@]}" "$HOST" "bash -s" <<REMOTE
set -euo pipefail
APP='$APP'
cd "\$APP/docker"
sudo docker compose -p echo-move -f docker-compose.vps.yml --env-file ../.env build backend
# container_name is fixed; remove any leftover from a different compose project name
sudo docker rm -f echo-move-backend 2>/dev/null || true
sudo docker compose -p echo-move -f docker-compose.vps.yml --env-file ../.env up -d backend
for i in \$(seq 1 30); do
  if curl -fsS http://127.0.0.1:18080/health >/tmp/echo-health.json 2>/dev/null; then
    cat /tmp/echo-health.json; echo
    break
  fi
  sleep 2
done
sudo docker compose -p echo-move -f docker-compose.vps.yml ps
# Sanity: web mount + telegram from .env
CID=\$(sudo docker ps -qf name=echo-move-backend | head -1)
sudo docker exec "\$CID" sh -c 'python -c "import os; print(\"notify_telegram\", bool(os.getenv(\"ECHO_TELEGRAM_TOKEN\")), \"web_mount_ok\", open(\"/app/web/index.html\").read(80).find(\"Safety Operations\")>=0)"'
REMOTE

echo "==> Done. Local repo was source of truth; VPS mirrored + rebuilt."
