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
Web UI (8100)     ──┐
TP357 Scanner (Pi) ─┼──► REST API (8200) ──► InfluxDB (8086)
Sensor/Script       |
Grafana (3000)    ──┘                            ▲
                                         (direktly via Flux)
```

---

## Structure

```
consumo/
├── apps/
│   ├── common/          # Shared models (METERS, MeterType) - pip package, reads config/meters.yml
│   ├── api/             # REST API - InfluxDB abstraction
│   ├── web/             # Web UI - pure API consumer
│   └── sensors/tp357/   # BLE-Scanner for ThermoPro TP357, running on a Raspberry Pi
├── config/
│   ├── meters.yml         # All meters & sensors — add new ones here
│   └── sensors.yml        # Mapping for TP357 MAC-addresses
├── deploy/
│   ├── docker-compose.yml + .dev.yml   # local Dev-Setup (CLI/make)
│   ├── docker-compose.pi.yml           # TP357-Scanner on the Pi
│   └── synology/                       # Custom stack for Synology Container Manager
└── infrastructure/
    └── grafana/         # Datasource + dashboard provisioning + generated dashboards
```

---

## Setup

### Produktion (Synology NAS)

Läuft über Container Manager GUI, nicht über `make` — siehe
[`deploy/synology/README.md`](deploy/synology/README.md) für die vollständige Anleitung.

### Dev (lokal)

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

### Pi (TP357-Scanner)

Siehe [`apps/sensors/tp357/README.md`](apps/sensors/tp357/README.md).

---

## Ports

| Service   | Synology Prod | Dev  |
|-----------|---------------|------|
| Web UI    | 8100          | 8101 |
| REST API  | - (internal)  | 8201 |
| Grafana   | 3000          | 3001 |
| InfluxDB  | 8086          | 8087 |

The API is not exposed externally in prod!

## API - Quick reference

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

## Neuen Zähler / Sensor hinzufügen

`config/meters.yml` — Eintrag unter `meters:` oder `sensors:` ergänzen, kein
Code nötig. API und Web UI übernehmen ihn automatisch nach einem Neustart
der Container (Config ist read-only gemountet, kein Rebuild nötig).

Für mehrsprachige Labels: `apps/web/i18n/de.json` + `en.json` —
`meter_<id>_label` ergänzen.

## Dashboards neu generieren

Nach Änderungen an `infrastructure/grafana/dashboard_template.json` oder
neuen Sprachen in `apps/web/i18n/`:

```bash
cd deploy
make build-dashboards-synology   # nutzt deploy/synology/.env
make build-dashboards-dev        # nutzt .env.dev
```
