#!/usr/bin/env bash
# ============================================================
# WealthOS — Deploy local changes to production server
# Usage:
#   bash scripts/deploy.sh              # deploy everything
#   bash scripts/deploy.sh --backend    # backend only
#   bash scripts/deploy.sh --frontend   # frontend only
#   bash scripts/deploy.sh --restart    # just restart service
# ============================================================
set -e

SERVER="root@64.227.147.106"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_BACKEND=true
DEPLOY_FRONTEND=true
RESTART_ONLY=false

# Parse flags
for arg in "$@"; do
  case $arg in
    --backend)   DEPLOY_FRONTEND=false ;;
    --frontend)  DEPLOY_BACKEND=false ;;
    --restart)   DEPLOY_BACKEND=false; DEPLOY_FRONTEND=false; RESTART_ONLY=true ;;
  esac
done

echo "🚀 WealthOS — Deploying to production..."
echo "   Remote: $SERVER"
echo ""

# Git commit check
if [ "$DEPLOY_BACKEND" = true ] || [ "$DEPLOY_FRONTEND" = true ]; then
  if ! git -C "$LOCAL_ROOT" diff --quiet 2>/dev/null; then
    echo "⚠️  You have uncommitted changes. Committing before deploy..."
    git -C "$LOCAL_ROOT" add -A
    git -C "$LOCAL_ROOT" commit -m "deploy: $(date '+%Y-%m-%d %H:%M')" || true
  fi
fi

# Deploy backend
if [ "$DEPLOY_BACKEND" = true ]; then
  echo "📦 Deploying backend..."
  rsync -avz --progress \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='*.log' \
    -e "ssh -o ServerAliveInterval=30" \
    "$LOCAL_ROOT/backend/" \
    "$SERVER:/opt/wlthos/backend/"
  echo "✅ Backend deployed"
fi

# Deploy frontend
if [ "$DEPLOY_FRONTEND" = true ]; then
  echo ""
  echo "🖥️  Deploying frontend..."
  rsync -avz --progress \
    -e "ssh -o ServerAliveInterval=30" \
    "$LOCAL_ROOT/frontend/dist/" \
    "$SERVER:/opt/wlthos/frontend/dist/"
  echo "✅ Frontend deployed"
fi

# Restart API service
echo ""
echo "🔄 Restarting wealthos-api service..."
ssh -o ServerAliveInterval=30 "$SERVER" "systemctl restart wealthos-api"
echo "⏳ Waiting 12 seconds for service to start..."
sleep 12

# Health check
echo ""
echo "🏥 Health check..."
HEALTH=$(curl -s https://api.wlthos.in/health 2>/dev/null || echo "FAILED")
echo "   API: $HEALTH"

if echo "$HEALTH" | grep -q '"ok"'; then
  echo ""
  echo "✅ Deploy complete! API is healthy."
else
  echo ""
  echo "❌ API health check failed. Check logs:"
  echo "   ssh -o ServerAliveInterval=30 root@64.227.147.106"
  echo "   journalctl -u wealthos-api -n 30 --no-pager"
  exit 1
fi

# Push to GitHub
echo ""
echo "📤 Pushing to GitHub..."
git -C "$LOCAL_ROOT" push origin main 2>/dev/null || \
  git -C "$LOCAL_ROOT" push origin master 2>/dev/null || \
  echo "⚠️  GitHub push skipped. Run: git remote add origin git@github.com:Spock2989/wealthOS.git"

echo ""
echo "🎉 All done!"
echo "   Live:  https://wlthos.in"
echo "   API:   https://api.wlthos.in"
echo "   Docs:  https://api.wlthos.in/docs"
