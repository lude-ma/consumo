FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CONSUMO_REMINDERS_PATH=/config/reminders.yml

CMD ["python", "scheduler.py"]
