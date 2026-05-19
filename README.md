# Consumo

Self-hosted utility tracking platform for modern homelabs.

Track electricity, water, pellets and other consumption data with a clean API-first architecture powered by InfluxDB and Grafana.

---

## Features

- 📊 Track consumption data (electricity, water, pellets)
- 🕒 Time-series storage via InfluxDB
- 📈 Visualization with Grafana
- 🐳 Docker Compose deployment
- 🔌 API-first architecture (FastAPI)
- 🔒 Fully self-hosted

---

## Stack

- Backend: FastAPI
- Database: InfluxDB
- Visualization: Grafana
- Deployment: Docker Compose

---

## Architecture
Sensor / Manual Input
↓
FastAPI
↓
InfluxDB
↓
Grafana Dashboards

---

## Quick Start

```bash
git clone https://github.com/lude-ma/consumo.git
cd consumo
docker compose up -d
```

---

## Services
|Service  |URL                  |
|:--------|---------------------|
|API      |http://localhost:8000|
|Grafana  |http://localhost:3000|
|InfluxDB |http://localhost:8086|
