FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir setuptools

COPY common ./common
RUN pip install --no-cache-dir -e ./common

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .

EXPOSE 8200

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
