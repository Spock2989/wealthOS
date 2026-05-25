#!/usr/bin/env bash
# ============================================================
# WealthOS — Pull code from production server to local
# Usage: bash scripts/pull-from-server.sh
# ============================================================
set -e

SERVER="root@64.227.147.106"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🔄 WealthOS — Pulling from production server..."
echo "   Local:  $LOCAL_ROOT"
echo "   Remote: $SERVER"
echo ""

# Pull backend Python code (exclude venv, __pycache__, .env)
echo "📦 Pulling backend..."
rsync -avz --progress \
  --exclude='venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='*.log' \
  --exclude='celerybeat*' \
  -e "ssh -o ServerAliveInterval=30" \
  "$SERVER:/opt/wlthos/backend/" \
  "$LOCAL_ROOT/backend/"

# Pull frontend
echo ""
echo "🖥️  Pulling frontend..."
rsync -avz --progress \
  -e "ssh -o ServerAliveInterval=30" \
  "$SERVER:/opt/wlthos/frontend/" \
  "$LOCAL_ROOT/frontend/"

# Pull nginx config for reference
echo ""
echo "⚙️  Pulling nginx config..."
mkdir -p "$LOCAL_ROOT/infra/nginx"
ssh -o ServerAliveInterval=30 "$SERVER" \
  "cat /etc/nginx/sites-available/wealthos-api" \
  > "$LOCAL_ROOT/infra/nginx/wealthos-api.conf" 2>/dev/null || true

ssh -o ServerAliveInterval=30 "$SERVER" \
  "cat /etc/nginx/sites-available/wealthos-frontend" \
  > "$LOCAL_ROOT/infra/nginx/wealthos-frontend.conf" 2>/dev/null || true

# Pull systemd service file
mkdir -p "$LOCAL_ROOT/infra/systemd"
ssh -o ServerAliveInterval=30 "$SERVER" \
  "cat /etc/systemd/system/wealthos-api.service" \
  > "$LOCAL_ROOT/infra/systemd/wealthos-api.service" 2>/dev/null || true

echo ""
echo "✅ Pull complete!"
echo ""
echo "💡 Next: review changes, then commit:"
echo "   cd $LOCAL_ROOT"
echo "   git status"
echo "   git add -A && git commit -m 'chore: sync from prod $(date +%Y-%m-%d)'"
