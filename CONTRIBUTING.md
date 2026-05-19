# Contributing to Consumo

Thanks for your interest in contributing!

---

## Principles

- Keep it simple
- Docker-first design
- Self-hostable on NAS systems
- No cloud dependency

---

## Development Setup

```bash
docker compose up -d
```
For API development:
```bash
cd apps/api
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## Guidelines
- Use type hints in Python
- Keep endpoints RESTful
- Avoid tight coupling to Grafana
- Prefer InfluxDB-friendly data models

---

## Pull Requests
- Small and focused PRs
- Clear description
- Include screenshots for UI changes
