FROM python:3.12-slim

# Install BlueZ and DBus - required for bleak on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Config is mounted at runtime via docker-compose volume
ENV CONSUMO_SENSORS_PATH=/config/sensors.yml

CMD ["python", "main.py", "--mode", "scan"]
