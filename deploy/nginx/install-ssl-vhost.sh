#!/bin/bash
set -euo pipefail
sudo tee /www/server/panel/vhost/nginx/test.antokr.com.conf >/dev/null <<'NGINX'
upstream echo_move_backend {
    server 127.0.0.1:18080;
    keepalive 16;
}

server {
    listen 80;
    listen [::]:80;
    server_name test.antokr.com;

    include /www/server/panel/vhost/nginx/well-known/test.antokr.com.conf;

    location ^~ /.well-known/acme-challenge/ {
        root /www/wwwroot/test.antokr.com;
        default_type text/plain;
        allow all;
    }

    location / {
        return 301 https://$host$request_uri;
    }

    access_log /www/wwwlogs/test.antokr.com.log;
    error_log  /www/wwwlogs/test.antokr.com.error.log;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name test.antokr.com;

    ssl_certificate     /www/server/panel/vhost/cert/test.antokr.com/fullchain.pem;
    ssl_certificate_key /www/server/panel/vhost/cert/test.antokr.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers EECDH+CHACHA20:EECDH+AES128:RSA+AES128:EECDH+AES256:RSA+AES256:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header Strict-Transport-Security "max-age=31536000" always;
    error_page 497 https://$host$request_uri;

    location / {
        proxy_pass http://echo_move_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_connect_timeout 60s;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_cache off;
    }

    access_log /www/wwwlogs/test.antokr.com.log;
    error_log  /www/wwwlogs/test.antokr.com.error.log;
}
NGINX

sudo nginx -t
sudo nginx -s reload

sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/echo-move-test-antokr.sh >/dev/null <<'HOOK'
#!/bin/bash
DOMAIN=test.antokr.com
SRC=/etc/letsencrypt/live/$DOMAIN
DST=/www/server/panel/vhost/cert/$DOMAIN
cp -L "$SRC/fullchain.pem" "$DST/fullchain.pem"
cp -L "$SRC/privkey.pem" "$DST/privkey.pem"
chmod 644 "$DST/fullchain.pem"
chmod 600 "$DST/privkey.pem"
nginx -t && nginx -s reload
HOOK
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/echo-move-test-antokr.sh

echo "=== verify ==="
curl -fsS -o /dev/null -w "http:%{http_code} redirect:%{redirect_url}\n" http://127.0.0.1/health -H 'Host: test.antokr.com' || true
curl -fsS https://test.antokr.com/health
echo
curl -fsS -o /dev/null -w "https_ui:%{http_code}\n" https://test.antokr.com/
