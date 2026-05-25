# Consumo

Self-hosted utility tracking platform for modern homelabs.

Track electricity, water, pellets and other consumption data with a clean API-first architecture powered by InfluxDB and Grafana.

---

## Features

- 📊 Track consumption data (electricity, water, pellets)
- 🕒 Time-series storage via InfluxDB
- 📈 Visualization with Grafana
- 🐳 Docker Compose deployment
- 🔌 API-first architecture
- 🔒 Fully self-hosted

---

## Architecture

```
Web UI (8100)  ──┐
Sensor/Script    ├──► REST API (8200) ──► InfluxDB (8086)
Grafana (3000) ──┘                            ▲
                                      (direktly via Flux)
```

---

## Structure

```
consumo/
├── apps/
│   ├── common/          # Shared models (METERS, MeterType) — pip package
│   ├── api/             # REST API — InfluxDB abstraction
│   └── web/             # Web UI — pure API consumer
├── deploy/              # Docker Compose, Makefile, .env.*
└── infrastructure/
    └── grafana/         # Datasource + Dashboard provisioning
```

---

## Setup

```bash
git clone https://github.com/lude-ma/consumo.git
cd consumo/deploy

# 1. Set secrets
cp .env.prod .env.prod.local   # then modify
# or directly modify .env.prod

# Generate token
openssl rand -hex 32

# 2. Start
make prod-up

# Dev
make dev-up
```

---

## Ports

| Service   | Prod | Dev  |
|-----------|------|------|
| Web UI    | 8100 | 8101 |
| REST API  | —    | 8201 |
| Grafana   | 3000 | 3001 |
| InfluxDB  | 8086 | 8087 |

The API is not exposed externally in prod!

## API — Quick reference

Interactive docs (Dev): http://localhost:8201/docs

```bash
# All meters
curl -H "X-API-Key: dev-key" http://localhost:8201/api/v1/meters

# Write a value
curl -X POST -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"value": 12345.6, "note": "Ablesung Januar"}' \
  http://localhost:8201/api/v1/meters/strom/readings

# Read values
curl -H "X-API-Key: dev-key" \
  "http://localhost:8201/api/v1/meters/strom/readings?start=-30d&limit=50"

# Statistics
curl -H "X-API-Key: dev-key" http://localhost:8201/api/v1/meters/strom/stats
```

## Add a new meter

`apps/common/consumo_common/models.py` — Append an entry in `METERS`.
API and Web UI recognize it automatically after the next build.
