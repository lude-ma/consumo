DEV_PROJECT  = consumo-dev
DEV_FILES    = -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: dev-up dev-down dev-logs dev-ps dev-restart \
        pi-up pi-down pi-logs pi-discover pi-history \
        synology-validate \
        build-dashboards build-dashboards-dev build-dashboards-synology \
        help

# ── Dev (runs on your laptop, via Docker CLI) ───────────────────────────────
dev-up:
	docker compose -p $(DEV_PROJECT) $(DEV_FILES) --env-file .env.dev up -d --build

dev-down:
	docker compose -p $(DEV_PROJECT) $(DEV_FILES) down

dev-logs:
	docker compose -p $(DEV_PROJECT) $(DEV_FILES) logs -f

dev-ps:
	docker compose -p $(DEV_PROJECT) $(DEV_FILES) ps

dev-restart:
	docker compose -p $(DEV_PROJECT) $(DEV_FILES) restart

# ── Prod (Synology NAS via Container Manager — see deploy/synology/) ───────
# There are no "prod-*" make targets: prod runs as a Container Manager
# Project on the NAS, where `make` isn't installed. Deployment happens
# through the Container Manager GUI (Build / Start / Stop / Restart).
# `restart: unless-stopped` means containers survive NAS reboots automatically
# — no make, no CLI action needed for normal operation.
#
# This target only *validates* the Synology compose file locally before you
# upload it — catches YAML/syntax errors early.
synology-validate:
	docker compose -f synology/docker-compose.yml --env-file synology/.env.example config > /dev/null \
		&& echo "✓ deploy/synology/docker-compose.yml is valid"

# ── Pi Scanner ───────────────────────────────────────────────────────────────
PI_FILES = -f docker-compose.pi.yml

pi-up:
	docker compose $(PI_FILES) --env-file .env.pi up -d --build

pi-down:
	docker compose $(PI_FILES) --env-file .env.pi down

pi-logs:
	docker compose $(PI_FILES) --env-file .env.pi logs -f

pi-discover:
	docker compose $(PI_FILES) --env-file .env.pi run --rm scanner python main.py --mode discover

pi-history:
	docker compose $(PI_FILES) --env-file .env.pi run --rm scanner python main.py --mode history --history-mode year

# ── Dashboards ──────────────────────────────────────────────────────────────
# Run after creating/editing deploy/synology/.env (uses its INFLUXDB_BUCKET)
build-dashboards-synology:
	python3 ../infrastructure/grafana/dashboard_template/build_dashboards.py --env synology/.env

build-dashboards-dev:
	python3 ../infrastructure/grafana/dashboard_template/build_dashboards.py --env .env.dev

build-dashboards: build-dashboards-synology

# ── Help ────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Consumo"
	@echo ""
	@echo "  Dev   — Web 8101 | Grafana 3001 | InfluxDB 8087 | API 8201"
	@echo "    make dev-up       make dev-down       make dev-logs"
	@echo ""
	@echo "  Prod  — deployed via Synology Container Manager, see deploy/synology/README.md"
	@echo "    make synology-validate   (lint the compose file before uploading)"
	@echo ""
	@echo "  Pi Scanner (run on the Pi)"
	@echo "    make pi-up           make pi-down         make pi-logs"
	@echo "    make pi-discover     (find TP357 MAC addresses)"
	@echo "    make pi-history      (import 1 year of history)"
	@echo ""
	@echo "  Dashboards"
	@echo "    make build-dashboards-synology   (uses deploy/synology/.env)"
	@echo "    make build-dashboards-dev        (uses .env.dev)"
	@echo ""
