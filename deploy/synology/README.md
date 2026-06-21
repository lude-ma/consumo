# Consumo auf Synology DSM (Container Manager)

Diese Anleitung deployt Consumo als **Container Manager Project** auf einem
Synology NAS (getestet mit DS925+, DSM 7.2). Kein `make`, kein SSH zwingend
nötig — alles läuft über die Container Manager GUI.

## Warum ein eigener Ordner?

Container Manager's Project-Feature erkennt pro Ordner genau eine
`docker-compose.yml` und eine `.env` — keine `-f file1 -f file2`-Overlays,
keine frei benannten Env-Files. `deploy/synology/docker-compose.yml` ist
deshalb eine **eigenständige, vollständige** Compose-Datei (kein Overlay auf
die Basis-Datei in `deploy/`), extra für diesen Zweck zusammengeführt.

## Setup

### 1. Repo auf das NAS bringen

Egal wie — File Station Upload, `git clone` per SSH, oder SMB-Share von
deinem Rechner aus mit Finder/Explorer auf das NAS kopieren. Wichtig ist nur:
die **Ordnerstruktur muss erhalten bleiben**, da `docker-compose.yml` über
relative Pfade (`../../apps`, `../../config`, `../../infrastructure`) auf den
Rest des Repos zugreift.

```
/volume2/docker/consumo/
├── apps/
├── config/
├── infrastructure/
└── deploy/
    └── synology/
        ├── docker-compose.yml
        └── .env.example
```

### 2. `.env` anlegen

```bash
cd deploy/synology
cp .env.example .env
nano .env   # alle "change-me"-Werte durch echte Secrets ersetzen
```

Token generieren:
```bash
openssl rand -hex 32
```

`.env` ist gitignored — landet nie im Repo.

### 3. Optional: lokal validieren bevor du hochlädst

Falls du Docker auf deinem Rechner hast:
```bash
cd deploy
make synology-validate
```

Prüft die YAML-Syntax, ohne dass du dafür auf dem NAS sein musst.

### 4. Container Manager → Project → Create

1. **Project name**: z.B. `consumo`
2. **Path**: `deploy/synology` auswählen (genau dieser Ordner, nicht das Repo-Root)
3. Container Manager erkennt `docker-compose.yml` und `.env` automatisch
4. **Build** ausführen (lädt Images, baut `api` und `web`)
5. **Start**

### 5. Zugriff

- Web UI: `http://NAS-IP:8100`
- Grafana: `http://NAS-IP:3000`
- InfluxDB: `http://NAS-IP:8086`

## Was bei einem NAS-Neustart passiert

**Nichts, was du tun musst.** Alle Container haben `restart: unless-stopped`
— das ist eine Docker-Engine-Policy, kein Skript und kein `make`. Sobald das
NAS hochfährt:

1. DSM startet Container Manager als Paket (Standard-Verhalten, prüfbar unter
   *Paketzentrum → Container Manager → Einstellungen*)
2. Der Docker-Daemon startet
3. Der Daemon startet automatisch alle Container mit `unless-stopped`-Policy

Das funktioniert unabhängig davon, ob `make` installiert ist — `make` wird
nur für *Deployment-Aktionen* gebraucht (Rebuild nach Code-Änderung), nicht
für den laufenden Betrieb.

## Updates / Config-Änderungen

Nach Änderungen an Code oder `config/meters.yml`:

1. Geänderte Dateien aufs NAS kopieren (überschreiben)
2. Container Manager → Project → `consumo` → **Build** (baut Images neu)
3. **Restart**

Für reine Config-Änderungen (`config/*.yml`, kein Code) reicht **Restart**
ohne Rebuild, da `config/` als Read-Only-Volume gemountet ist.

## Optional: SSH als Fallback für Power-User

Falls du SSH aktivierst (*Systemsteuerung → Terminal & SNMP*), bringt
Container Manager den `docker compose`-Befehl mit — `make` ist zwar nicht
da, aber `docker compose` direkt funktioniert:

```bash
cd /volume2/docker/consumo/deploy/synology
docker compose logs -f
docker compose restart
docker compose up -d --build
```

Das ist nützlich für Live-Logs oder schnelles Debugging, aber für den
Normalbetrieb nicht nötig — die GUI deckt alles ab.

## Troubleshooting

**Build schlägt fehl mit "context not found" o.ä.**
Die relative Pfadstruktur (`../../apps`) stimmt nicht — prüfe, dass der
Ordner exakt wie oben beschrieben aufgebaut ist und `deploy/synology/` nicht
isoliert kopiert wurde.

**Grafana zeigt keine Dashboards**
`infrastructure/grafana/dashboards/consumo_*.json` muss mitkopiert worden
sein — diese Dateien werden vorab lokal generiert (`make build-dashboards-synology`)
und sind Teil des Repos, nicht etwas das auf dem NAS gebaut wird.
