from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.ledger import Ledger
from app.gateway.main import create_app
from app.telemetry import configure_http


@pytest.mark.asyncio
async def test_metrics_use_route_templates_and_exclude_scrapes():
    app = FastAPI()

    @app.get("/payment/{identifier}")
    async def payment(identifier: int):
        return {"id": identifier}

    configure_http(app, "test-api", None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/payment/12345")).status_code == 200
        assert (await client.get("/private/67890")).status_code == 404
        metrics = (await client.get("/metrics/")).text
    assert 'route="/payment/{identifier}"' in metrics
    assert 'route="unmatched"' in metrics
    assert "12345" not in metrics and "67890" not in metrics
    assert 'route="/metrics' not in metrics


@pytest.mark.asyncio
async def test_gateway_ledger_survives_restart_and_requires_token(tmp_path, monkeypatch):
    path = tmp_path / "gateway.sqlite"
    monkeypatch.setenv("GATEWAY_LEDGER_PATH", str(path))
    monkeypatch.setenv("RECONCILIATION_TOKEN", "test-value")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        original = await client.post("/processar", headers={"Idempotency-Key": "test-key"},
                                     json={"valor": 18.5, "descricao": "compra"})
        assert original.status_code == 200

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(mode="always_fail")), base_url="http://test"
    ) as client:
        replay = await client.post("/processar", headers={"Idempotency-Key": "test-key"},
                                   json={"valor": 18.5, "descricao": "compra"})
        assert replay.json() == original.json()
        now = datetime.now(timezone.utc)
        params = {"start": (now - timedelta(minutes=1)).isoformat(), "end": now.isoformat()}
        assert (await client.get("/internal/ledger", params=params)).status_code == 401
        response = await client.get("/internal/ledger", params=params,
                                    headers={"Authorization": "Bearer test-value"})
        assert response.json() == [{"key": "test-key", "amount": 18.5}]
    assert Ledger(path).find("absent") is None
