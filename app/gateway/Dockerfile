FROM python:3.11-slim

WORKDIR /gateway

COPY app/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/telemetry.py app/logging_config.py ./app/
COPY app/gateway/main.py app/gateway/ledger.py ./app/gateway/

EXPOSE 8080

CMD ["uvicorn", "app.gateway.main:app", "--host", "0.0.0.0", "--port", "8080"]