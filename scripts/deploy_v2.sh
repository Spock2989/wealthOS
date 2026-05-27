#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# WealthOS v2.0 — Full Deploy Script
# Run from your Mac: bash scripts/deploy_v2.sh
#
# What this does (in order):
#   1. Builds the frontend
#   2. Pushes backend to server (excludes DB + venv + pyc)
#   3. Pushes frontend dist to server
#   4. Installs Python deps on server
#   5. Updates systemd service + reloads daemon
#   6. ONE-TIME: resets DB schema and seeds admin user
#   7. Restarts wealthos service
#   8. Verifies /health endpoint responds correctly
# ─────────────────────────────────────────────────────────────────────────────

set -e

SERVER="root@64.227.147.106"
REMOTE="/opt/wlthos"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)"   # repo root

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     WealthOS v2.0 — Production Deploy        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "📂 Local root:  $LOCAL"
echo "🌐 Server:      $SERVER"
echo ""

# ── Step 1: Verify frontend dist ─────────────────────────────────────────────
echo "▶ [1/8] Verifying frontend dist..."
if [ ! -f "$LOCAL/frontend/dist/app.html" ]; then
  echo "❌ frontend/dist/app.html not found — aborting"
  exit 1
fi
echo "✅ Frontend dist ready ($(ls $LOCAL/frontend/dist/*.html | wc -l | tr -d ' ') HTML files)"

# ── Step 2: Sync backend ─────────────────────────────────────────────────────
echo ""
echo "▶ [2/8] Syncing backend to server..."
rsync -avz --progress \
  "$LOCAL/backend/" \
  "$SERVER:$REMOTE/backend/" \
  --exclude='__pycache__' \
  --exclude='venv' \
  --exclude='.env' \
  --exclude='*.pyc' \
  --exclude='wealthos.db' \
  --exclude='wealthos.db-shm' \
  --exclude='wealthos.db-wal' \
  --exclude='wealthos.db.bak' \
  --exclude='wealthos_test.db*'
echo "✅ Backend synced"

# ── Step 3: Sync frontend dist ───────────────────────────────────────────────
echo ""
echo "▶ [3/8] Syncing frontend dist to server..."
rsync -avz --progress \
  "$LOCAL/frontend/dist/" \
  "$SERVER:$REMOTE/frontend/dist/"
ssh "$SERVER" "chmod 644 $REMOTE/frontend/dist/*.html && echo '✅ Frontend permissions set'"

# ── Step 4: Sync infra files ─────────────────────────────────────────────────
echo ""
echo "▶ [4/8] Syncing infra (nginx + systemd) to server..."
rsync -avz "$LOCAL/infra/" "$SERVER:$REMOTE/infra/"
echo "✅ Infra synced"

# ── Step 5: Install Python deps ──────────────────────────────────────────────
echo ""
echo "▶ [5/8] Installing Python deps on server..."
ssh "$SERVER" bash << 'ENDSSH'
set -e
cd /opt/wlthos/backend
source venv/bin/activate
pip install --quiet python-jose[cryptography] passlib bcrypt python-multipart pymupdf openpyxl python-dotenv
pip install --quiet -r requirements.txt
echo "✅ Python deps installed"
ENDSSH

# ── Step 6: Update systemd service ───────────────────────────────────────────
echo ""
echo "▶ [6/8] Updating systemd service..."
ssh "$SERVER" bash << 'ENDSSH'
set -e
cp /opt/wlthos/infra/systemd/wealthos-api.service /etc/systemd/system/wealthos.service
systemctl daemon-reload
echo "✅ systemd service updated and daemon reloaded"
ENDSSH

# ── Step 7: Migrate schema (safe — never drops data) ─────────────────────────
# Pass --reset flag explicitly to wipe and re-seed: bash scripts/deploy_v2.sh --reset
echo ""
if [[ "$*" == *"--reset"* ]]; then
  echo "▶ [7/8] --reset flag detected: dropping DB and re-seeding..."
  ssh "$SERVER" bash << 'ENDSSH'
set -e
cd /opt/wlthos/backend
source venv/bin/activate
python3 scripts/reset_and_seed.py
ENDSSH
else
  echo "▶ [7/8] Applying schema migrations (data preserved)..."
  ssh "$SERVER" bash << 'ENDSSH'
set -e
cd /opt/wlthos/backend
source venv/bin/activate
python3 - << 'PYEOF'
from app.database import engine, Base
import app.models.user, app.models.portfolio, app.models.holding
import app.models.analytics_snapshot, app.models.ai_report, app.models.client
import app.models.fund_constituent   # v2.0 look-through cache
Base.metadata.create_all(bind=engine)
print("✅ Schema applied (tables created if missing, existing data preserved)")
PYEOF
ENDSSH
fi

# ── Step 8: Restart service + verify ─────────────────────────────────────────
echo ""
echo "▶ [8/8] Restarting wealthos service and verifying..."
ssh "$SERVER" bash << 'ENDSSH'
set -e
systemctl restart wealthos
sleep 4
systemctl is-active wealthos && echo "✅ Service is running" || (echo "❌ Service failed to start"; systemctl status wealthos --no-pager; exit 1)
HEALTH=$(curl -s http://127.0.0.1:8000/health)
echo "🔍 Health check: $HEALTH"
echo "$HEALTH" | grep -q '"status":"ok"' && echo "✅ API is healthy" || (echo "❌ API not healthy"; exit 1)
ENDSSH

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║            ✅  DEPLOY COMPLETE               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Login page:   https://wlthos.in/app.html"
echo "  Dashboard:    https://wlthos.in/dashboard.html"
echo "  API health:   https://api.wlthos.in/health"
echo "  API docs:     https://api.wlthos.in/docs"
echo ""
echo "  Credentials:"
echo "    Email:    tiwarikshitij20@gmail.com"
echo "    Password: WealthOS2026!"
echo ""
