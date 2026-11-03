import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import create_engine, text
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def connect():
    return create_engine(os.environ["RECONCILIATION_DATABASE_URL"], pool_pre_ping=True)


def gateway_request(path, params=None):
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{os.environ['RECONCILIATION_GATEWAY_URL'].rstrip('/')}{path}{query}"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {os.environ['RECONCILIATION_TOKEN']}",
    })
    with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310
        return json.load(response)


def payments(start, end):
    engine = connect()
    try:
        with engine.connect() as db:
            rows = db.execute(text("""
                SELECT i.chave AS key, p.valor AS amount
                FROM pagamentos p
                JOIN idempotencias_pagamento i ON i.pagamento_id = p.id
                WHERE p.criado_em >= :start AND p.criado_em < :end
                  AND p.status = 'APROVADO'
                ORDER BY i.chave
            """), {
                "start": datetime.fromisoformat(start).astimezone(timezone.utc).replace(tzinfo=None),
                "end": datetime.fromisoformat(end).astimezone(timezone.utc).replace(tzinfo=None),
            })
            return [dict(row) for row in rows.mappings()]
    finally:
        engine.dispose()


def compare(api_rows, gateway_rows):
    api = {row["key"]: Decimal(str(row["amount"])) for row in api_rows}
    gateway = {row["key"]: Decimal(str(row["amount"])) for row in gateway_rows}
    shared = api.keys() & gateway.keys()
    different = sorted(key for key in shared if api[key] != gateway[key])
    return {
        "api_count": len(api),
        "gateway_count": len(gateway),
        "matched": len(shared) - len(different),
        "missing_in_gateway": sorted(api.keys() - gateway.keys()),
        "missing_in_api": sorted(gateway.keys() - api.keys()),
        "amount_mismatch": different,
    }


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tracer_for(service):
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint.rstrip('/')}/v1/traces", timeout=5),
        ))
    return provider
