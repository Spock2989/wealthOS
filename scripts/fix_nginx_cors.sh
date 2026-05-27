#!/bin/bash
# Run this on the server (SSH as root) to fix browser login CORS
# Usage: bash fix_nginx_cors.sh

set -e

echo "▶ Writing clean nginx config..."
cat > /etc/nginx/sites-available/wealthos-api << 'NGINXEOF'
server {
    listen 80;
    server_name api.wlthos.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.wlthos.in;

    ssl_certificate     /etc/letsencrypt/live/api.wlthos.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.wlthos.in/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        if ($request_method = OPTIONS) {
            add_header 'Access-Control-Allow-Origin'      'https://wlthos.in' always;
            add_header 'Access-Control-Allow-Methods'     'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers'     'Authorization, Content-Type, Accept, X-Requested-With' always;
            add_header 'Access-Control-Allow-Credentials' 'true' always;
            add_header 'Access-Control-Max-Age'           '86400' always;
            add_header 'Content-Length'                   '0' always;
            add_header 'Content-Type'                     'text/plain' always;
            return 204;
        }

        add_header 'Access-Control-Allow-Origin'      'https://wlthos.in' always;
        add_header 'Access-Control-Allow-Methods'     'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers'     'Authorization, Content-Type, Accept, X-Requested-With' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;

        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   Connection        "";
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }
}
NGINXEOF

echo "▶ Testing nginx config..."
nginx -t

echo "▶ Reloading nginx..."
systemctl reload nginx

echo ""
echo "✅ Nginx reloaded. Testing CORS preflight..."
curl -s -o /dev/null -w "OPTIONS preflight status: %{http_code}\n" \
  -X OPTIONS https://api.wlthos.in/api/v1/auth/login \
  -H "Origin: https://wlthos.in" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type"

echo ""
echo "▶ Checking CORS headers returned..."
curl -sI -X OPTIONS https://api.wlthos.in/api/v1/auth/login \
  -H "Origin: https://wlthos.in" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  | grep -i "access-control"

echo ""
echo "▶ Testing login endpoint..."
curl -s -X POST https://api.wlthos.in/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: https://wlthos.in" \
  -d '{"email":"tiwarikshitij20@gmail.com","password":"WealthOS2026!"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ Login OK — token:', d.get('access_token','')[:40]+'...')" 2>/dev/null \
  || echo "⚠️ Login returned unexpected response"

echo ""
echo "Done. If all checks pass, browser login at https://wlthos.in/app.html should work."
