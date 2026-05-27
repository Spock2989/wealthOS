#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# WealthOS — Git Save (one command)
# Stages everything, commits with timestamp, pushes to GitHub.
#
# Usage:
#   bash scripts/git-save.sh                    # auto timestamp message
#   bash scripts/git-save.sh "your message"     # custom commit message
#
# Run from the WealthOS repo root:
#   cd ~/Documents/Claude/Projects/WealthOS
#   bash scripts/git-save.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         WealthOS — Git Save & Push           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── Check we're in a git repo ─────────────────────────────────────────────
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "❌ Not inside a git repository. Run from the WealthOS root."
  exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
REMOTE=$(git remote get-url origin 2>/dev/null || echo "none")
echo "📂 Repo   : $REPO_ROOT"
echo "🌿 Branch : $BRANCH"
echo "🔗 Remote : $REMOTE"
echo ""

# ── Exclude generated/temp files ─────────────────────────────────────────
# Make sure these are in .gitignore — add them if missing
GITIGNORE="$REPO_ROOT/.gitignore"
declare -a IGNORE_ENTRIES=(
  "*.db"
  "*.db-shm"
  "*.db-wal"
  "*.db.bak"
  "venv/"
  "__pycache__/"
  "*.pyc"
  ".env"
  "*.zip"
  ".fuse_hidden*"
  "node_modules/"
  ".DS_Store"
)
for entry in "${IGNORE_ENTRIES[@]}"; do
  if ! grep -qF "$entry" "$GITIGNORE" 2>/dev/null; then
    echo "$entry" >> "$GITIGNORE"
    echo "  ➕ Added $entry to .gitignore"
  fi
done

# ── Stage all changes ────────────────────────────────────────────────────
echo "▶ Staging all changes..."
git add -A
echo ""

# ── Show what's being committed ──────────────────────────────────────────
echo "📋 Changes staged:"
git diff --cached --name-status | sed 's/^/   /'
echo ""

STAGED_COUNT=$(git diff --cached --name-only | wc -l | tr -d ' ')
if [ "$STAGED_COUNT" -eq 0 ]; then
  echo "✅ Nothing to commit — working tree is clean."
  exit 0
fi

# ── Build commit message ─────────────────────────────────────────────────
TIMESTAMP=$(date "+%Y-%m-%d %H:%M")
if [ -n "$1" ]; then
  MSG="$1 [$TIMESTAMP]"
else
  # Auto-generate from changed file count + key areas
  BACKEND_COUNT=$(git diff --cached --name-only | grep -c "^backend/" || true)
  FRONTEND_COUNT=$(git diff --cached --name-only | grep -c "^frontend/" || true)
  SCRIPTS_COUNT=$(git diff --cached --name-only | grep -c "^scripts/" || true)

  AREAS=()
  [ "$BACKEND_COUNT"  -gt 0 ] && AREAS+=("backend(${BACKEND_COUNT})")
  [ "$FRONTEND_COUNT" -gt 0 ] && AREAS+=("frontend(${FRONTEND_COUNT})")
  [ "$SCRIPTS_COUNT"  -gt 0 ] && AREAS+=("scripts(${SCRIPTS_COUNT})")
  AREA_STR=$(IFS=', '; echo "${AREAS[*]}")

  MSG="WealthOS update — ${STAGED_COUNT} files [${AREA_STR}] [$TIMESTAMP]"
fi

echo "💬 Commit: $MSG"
echo ""

# ── Commit ────────────────────────────────────────────────────────────────
git commit -m "$MSG"

# ── Push ──────────────────────────────────────────────────────────────────
echo ""
echo "▶ Pushing to origin/$BRANCH..."
git push origin "$BRANCH"

# ── Done ──────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║          ✅  SAVED TO GITHUB                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "  Branch : $BRANCH"
echo "  Remote : $REMOTE"
echo "  Files  : $STAGED_COUNT files committed"
echo ""
echo "  View at: https://github.com/Spock2989/wealthOS"
echo ""
