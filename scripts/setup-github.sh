#!/usr/bin/env bash
# ============================================================
# WealthOS — Connect local folder to GitHub repo
# Run this ONCE to set up GitHub sync.
# Usage: bash scripts/setup-github.sh
# ============================================================
set -e

LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LOCAL_ROOT"

echo "🐙 WealthOS — GitHub Setup"
echo "================================"
echo ""

# Check if git already initialized
if [ -d ".git" ]; then
  echo "✅ Git already initialized in this folder"
  echo "   Current remotes:"
  git remote -v || echo "   (none)"
  echo ""
else
  echo "📁 Initializing git repository..."
  git init
  git add -A
  git commit -m "chore: initial commit — WealthOS project structure"
  echo "✅ Git initialized"
  echo ""
fi

# Ask for GitHub repo URL
echo "📋 Enter your GitHub repo URL (e.g. git@github.com:yourusername/wealthos.git)"
echo "   To find it: go to your GitHub repo → Code → SSH tab"
echo ""
read -p "   GitHub URL: " GITHUB_URL

if [ -z "$GITHUB_URL" ]; then
  echo "⚠️  No URL provided. Skipping remote setup."
  echo "   Run later: git remote add origin YOUR_GITHUB_URL && git push -u origin main"
  exit 0
fi

# Add or update remote
if git remote get-url origin &>/dev/null; then
  echo "🔄 Updating existing origin remote..."
  git remote set-url origin "$GITHUB_URL"
else
  echo "➕ Adding origin remote..."
  git remote add origin "$GITHUB_URL"
fi

# Push
echo ""
echo "📤 Pushing to GitHub..."
git branch -M main 2>/dev/null || true
git push -u origin main

echo ""
echo "✅ GitHub connected!"
echo "   Repo: $GITHUB_URL"
echo ""

# Set up server as additional remote (for direct git push to deploy)
echo "🖥️  Setting up server git remote (optional — for git push deploys)..."
echo "   This lets you do: git push server main"
echo ""
read -p "   Set up server remote? [y/N]: " SETUP_SERVER
if [ "$SETUP_SERVER" = "y" ] || [ "$SETUP_SERVER" = "Y" ]; then
  # Initialize bare repo on server
  ssh -o ServerAliveInterval=30 root@64.227.147.106 \
    "git init --bare /opt/wlthos/wealthos.git 2>/dev/null || echo 'already exists'"

  # Create post-receive hook on server
  ssh -o ServerAliveInterval=30 root@64.227.147.106 << 'REMOTE_EOF'
cat > /opt/wlthos/wealthos.git/hooks/post-receive << 'HOOK'
#!/bin/bash
echo "📦 Deploying WealthOS..."
cd /opt/wlthos
git --work-tree=/opt/wlthos/backend --git-dir=/opt/wlthos/wealthos.git checkout -f main -- backend/ 2>/dev/null || true
git --work-tree=/opt/wlthos/frontend/dist --git-dir=/opt/wlthos/wealthos.git checkout -f main -- frontend/dist/ 2>/dev/null || true
systemctl restart wealthos-api
sleep 5
echo "✅ Deploy done"
HOOK
chmod +x /opt/wlthos/wealthos.git/hooks/post-receive
echo "Hook installed"
REMOTE_EOF

  git remote add server "ssh://root@64.227.147.106/opt/wlthos/wealthos.git" 2>/dev/null || \
    git remote set-url server "ssh://root@64.227.147.106/opt/wlthos/wealthos.git"

  echo ""
  echo "✅ Server remote configured!"
  echo "   Now you can deploy with: git push server main"
fi

echo ""
echo "================================"
echo "Workflow going forward:"
echo "  1. Edit files locally in VSCode"
echo "  2. git add -A && git commit -m 'your message'"
echo "  3. git push origin main          # → GitHub"
echo "  4. bash scripts/deploy.sh        # → Production server"
echo "     OR: git push server main      # → Deploy via git"
echo "================================"
