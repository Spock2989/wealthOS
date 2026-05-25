# WealthOS — Makefile
# Usage: make <target>

.PHONY: help pull deploy status logs restart frontend backend github seed

help:
	@echo ""
	@echo "  WealthOS Commands"
	@echo "  ================="
	@echo "  make pull       ← Pull current code from server to local"
	@echo "  make deploy     ← Deploy local changes to production"
	@echo "  make frontend   ← Deploy frontend only"
	@echo "  make backend    ← Deploy backend only"
	@echo "  make restart    ← Restart API service only"
	@echo "  make status     ← Check server health + service status"
	@echo "  make logs       ← Stream live server logs"
	@echo "  make seed       ← Run AMFI data seeder on server"
	@echo "  make github     ← Set up GitHub connection"
	@echo "  make ssh        ← SSH into production server"
	@echo ""

pull:
	bash scripts/pull-from-server.sh

deploy:
	bash scripts/deploy.sh

frontend:
	bash scripts/deploy.sh --frontend

backend:
	bash scripts/deploy.sh --backend

restart:
	bash scripts/deploy.sh --restart

status:
	bash scripts/status.sh

logs:
	ssh -o ServerAliveInterval=30 root@64.227.147.106 'journalctl -u wealthos-api -f'

seed:
	ssh -o ServerAliveInterval=30 root@64.227.147.106 \
		'cd /opt/wlthos/backend && source venv/bin/activate && python3 scripts/seed_amfi.py'

github:
	bash scripts/setup-github.sh

ssh:
	ssh -o ServerAliveInterval=30 root@64.227.147.106
