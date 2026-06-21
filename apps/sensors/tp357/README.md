# TP357 BLE Scanner

Passive BLE scanner for ThermoPro TP357 sensors. Runs on a Raspberry Pi 4, writes to the Consumo API on the NAS.

## Hardware

- Raspberry Pi 4 (2GB+)
- Raspberry Pi OS Lite 64-bit
- Docker + Docker Compose
- No USB dongle needed (Pi 4 has integrated Bluetooth)

## Quick Start

```bash
# 1. Find sensor MAC addresses
make pi-discover

# 2. Fill in config/sensors.yml with MACs
# 3. Set NAS IP + API key in deploy/.env.pi

# 4. Import historical data (once)
make pi-history

# 5. Start continuous scanning
make pi-up
make pi-logs
```

## Modes

| Mode | Command | Description |
|---|---|---|
| Continuous scan | `make pi-up` | Passive advertisements, writes 1×/min per sensor |
| History import | `make pi-history` | One-time import of up to 1 year of stored data |
| Discovery | `make pi-discover` | Find nearby TP357 sensors and print MACs |

## Adding a new sensor

1. `make pi-discover` - find MAC address
2. `config/sensors.yml` - add sensor entry
3. `config/meters.yml` - add sensor_id under `sensors:`
4. `apps/web/i18n/de.json` + `en.json` - add label
5. `make pi-up` - restart (config is read on startup)

## Offline buffering

If the Consumo API (or the NAS InfluxDB behind it) is unreachable - e.g. during
a NAS reboot or network outage - readings are **not lost**. They're queued
locally in a SQLite database (`/data/queue.db`, persisted via the
`scanner-data` Docker volume) and automatically retried every
`retry_interval` seconds (see `config/sensors.yml`, default 30s) once the API
becomes reachable again.

```bash
# Check how many readings are currently queued (waiting for the NAS)
docker exec consumo-scanner python -c \
  "from offline_queue import ReadingQueue; print(ReadingQueue().count())"
```

4xx errors (bad data) are logged and dropped - only network/server errors are
queued, since retrying malformed data won't help.

## Troubleshooting

```bash
# Check BLE adapter in container
docker compose -f docker-compose.pi.yml run --rm scanner hciconfig

# Test API reachability from Pi
curl http://YOUR_NAS_IP:8200/api/v1/health
```
