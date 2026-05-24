FROM python:3.12-slim

WORKDIR /app

COPY ../common ./common
RUN pip install --no-cache-dir -e ./common

COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8100

CMD ["python", "app.py"]
