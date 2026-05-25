#!/usr/bin/env bash
# ============================================================
# WealthOS — Check production server status
# Usage: bash scripts/status.sh
# ============================================================

SERVER="root@64.227.147.106"

echo "📊 WealthOS Production Status"
echo "================================"
echo ""

# API health
echo "🏥 API Health:"
curl -s https://api.wlthos.in/health | python3 -m json.tool 2>/dev/null || echo "   ❌ API unreachable"
echo ""

# Service status
echo "⚙️  Service Status:"
ssh -o ServerAliveInterval=30 "$SERVER" \
  "systemctl is-active wealthos-api && echo '   ✅ wealthos-api: RUNNING' || echo '   ❌ wealthos-api: STOPPED'" 2>/dev/null
echo ""

# Recent logs
echo "📋 Last 10 log lines:"
ssh -o ServerAliveInterval=30 "$SERVER" \
  "journalctl -u wealthos-api -n 10 --no-pager" 2>/dev/null
echo ""

# Disk usage
echo "💾 Disk Usage:"
ssh -o ServerAliveInterval=30 "$SERVER" \
  "df -h /opt/wlthos 2>/dev/null || df -h /" 2>/dev/null
echo ""

echo "================================"
echo "🔗 https://wlthos.in | https://api.wlthos.in/docs"
