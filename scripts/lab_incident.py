"""Provoca falha no gateway do laboratório isolado e guarda provas verificáveis."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
FILES = ("docker-compose.yml", "deploy/compose.lab.yml", "deploy/compose.observability.yml")
COMPOSE = ["docker", "compose", "-p", "payment-lab"]
for file in FILES:
    COMPOSE.extend(("-f", file))
API = "http://127.0.0.1:8002"
PROMETHEUS = "http://127.0.0.1:9090"
GRAFANA = "http://127.0.0.1:3000"


def eventually(check, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (httpx.TransportError, httpx.HTTPStatusError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Evidência indisponível: {check.__name__}")


def gateway_mode(mode):
    subprocess.run(
        [*COMPOSE, "up", "-d", "--no-deps", "--force-recreate",
         "--wait", "--wait-timeout", "60", "gateway"],
        cwd=ROOT, env=dict(os.environ, GATEWAY_MODE=mode), check=True, timeout=120,
    )


def incident():
    started = time.time()
    with httpx.Client(timeout=40) as client:
        def api(path, payload, headers=None, expected=201):
            response = client.post(f"{API}{path}", json=payload, headers=headers)
            if response.status_code != expected:
                raise RuntimeError(f"{path}: HTTP {response.status_code}, esperado {expected}")
            return response.json()

        def get(base, path, **params):
            return client.get(f"{base}{path}", params=params).raise_for_status().json()

        identifier = secrets.token_hex(8)
        token = api("/auth/registro", {
            "nome": "Cliente fictício", "email": f"lab-{identifier}@example.com",
            "senha": secrets.token_urlsafe(20),
        })["token"]

        def payment(expected):
            return api("/pagamentos", {"valor": 19.9, "descricao": "Incidente simulado"}, {
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": secrets.token_hex(16),
            }, expected)

        def firing():
            alerts = get(PROMETHEUS, "/api/v1/alerts")["data"]["alerts"]
            return [a for a in alerts if a["state"] == "firing"
                    and a["labels"].get("alertname") == "PagamentoComFalhas"
                    and a["labels"].get("service") == "api"]

        def exemplar():
            series = get(PROMETHEUS, "/api/v1/query_exemplars", query=(
                'payment_http_duration_seconds_bucket{service="api",route="/pagamentos",status="503"}'
            ), start=started, end=time.time())["data"]
            return next((point for sample in series for point in reversed(sample["exemplars"])
                         if point["labels"].get("trace_id")), None)

        try:
            gateway_mode("always_fail")
            for _ in range(3):
                payment(503)
                time.sleep(6)
            alerts = eventually(firing)
            sample = eventually(exemplar)
            trace_id = sample["labels"]["trace_id"]

            def trace():
                return get(GRAFANA, f"/api/datasources/proxy/uid/tempo/api/traces/{trace_id}")

            def logs():
                streams = get(
                    GRAFANA, "/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
                    query='{service_name=~"api|gateway"} | json | trace_id="' + trace_id + '"',
                    start=int(started * 1e9), end=time.time_ns(),
                )["data"]["result"]
                if {"api", "gateway"} <= {stream["stream"].get("service_name") for stream in streams}:
                    return streams
                return None

            trace_data = eventually(trace)
            services = {
                attribute["value"].get("stringValue")
                for batch in trace_data.get("batches", trace_data.get("resourceSpans", []))
                for attribute in batch["resource"]["attributes"]
                if attribute["key"] == "service.name"
            }
            if not {"api", "gateway"} <= services:
                raise RuntimeError(f"Trace incompleto: {sorted(services)}")
            evidence = {"alerts": alerts, "exemplar": sample, "trace": trace_data, "logs": eventually(logs)}
        finally:
            gateway_mode("success")

        evidence["recovery_status"] = payment(201)["status"]
        output = ROOT / "reports" / "lab-incident.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Incidente e recuperação verificados: {output}")


if __name__ == "__main__":
    incident()
