# GitHub Setup — Run Once

Your repo: https://github.com/Spock2989/wealthOS

## Step 1 — Open Terminal in the WealthOS folder

```bash
cd /Users/user/Documents/Claude/Projects/WealthOS
```

## Step 2 — Initialize git and connect to GitHub

```bash
# Init
git init

# Add everything
git add -A

# First commit
git commit -m "feat: WealthOS project structure, app.html v2, AMFI seeder, price provider"

# Connect to your GitHub repo (SSH — recommended)
git remote add origin git@github.com:Spock2989/wealthOS.git

# OR if you prefer HTTPS:
# git remote add origin https://github.com/Spock2989/wealthOS.git

# Push
git branch -M main
git push -u origin main
```

## Step 3 — Verify

Open https://github.com/Spock2989/wealthOS — your files should appear.

---

## Step 4 — Pull existing code from server (optional but recommended)

This pulls the backend engines and existing code from your live server into this folder:

```bash
bash scripts/pull-from-server.sh
git add -A && git commit -m "chore: pull existing backend from server"
git push origin main
```

---

## After that — daily workflow

```bash
make deploy    # deploy + push to GitHub in one command
```

Or step by step:
```bash
git add -A
git commit -m "your message"
git push origin main          # → GitHub
bash scripts/deploy.sh        # → Production server
```

---

## Open in VSCode

```bash
code wealthos.code-workspace
```

This opens all folders (Root, Backend, Frontend, Scripts) as a multi-root workspace with:
- VSCode tasks wired to deploy/pull/status scripts (Ctrl+Shift+P → Tasks: Run Task)
- Debug config for local FastAPI dev
- Recommended extensions list
