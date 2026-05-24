FROM python:3.12-slim

WORKDIR /app

# Install common package first (layer cache friendly)
RUN pip install --no-cache-dir setuptools

COPY common ./common
RUN pip install --no-cache-dir -e ./common

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ .

EXPOSE 8200

CMD ["python", "app.py"]
