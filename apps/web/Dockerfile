FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir setuptools

COPY common ./common
RUN pip install --no-cache-dir -e ./common

COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web/ .

EXPOSE 8100

CMD ["python", "app.py"]
