PROD_PROJECT = consumo-prod
DEV_PROJECT  = consumo-dev
PROD_FILES   = -f docker-compose.yml -f docker-compose.prod.yml
DEV_FILES    = -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: prod-up prod-down prod-logs prod-ps prod-restart \
        dev-up dev-down dev-logs dev-ps dev-restart \
        build-dashboards help

# ── Prod ────────────────────────────────────────────────────────────────────
prod-up:
	docker compose -p $(PROD_PROJECT) $(PROD_FILES) --env-file .env.prod up -d --build

prod-down:
	docker compose -p $(PROD_PROJECT) $(PROD_FILES) down

prod-logs:
	docker compose -p $(PROD_PROJECT) $(PROD_FILES) logs -f

prod-ps:
	docker compose -p $(PROD_PROJECT) $(PROD_FILES) ps

prod-restart:
	docker compose -p $(PROD_PROJECT) $(PROD_FILES) restart

# ── Dev ─────────────────────────────────────────────────────────────────────
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

# ── Dashboards ──────────────────────────────────────────────────────────────
build-dashboards:
	python3 ../infrastructure/grafana/build_dashboards.py

# ── Help ────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Consumo"
	@echo ""
	@echo "  Prod  — Web 8100 | Grafana 3000 | InfluxDB 8086"
	@echo "    make prod-up      make prod-down      make prod-logs"
	@echo ""
	@echo "  Dev   — Web 8101 | Grafana 3001 | InfluxDB 8087 | API 8201"
	@echo "    make dev-up       make dev-down       make dev-logs"
	@echo ""
