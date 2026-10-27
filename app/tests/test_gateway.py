import httpx
import pytest
from tenacity import wait_none

from app import idempotency, retry as retry_module, services
from app.gateway.main import create_app

PAYLOAD = {"valor": 10, "descricao": "Compra de teste"}


def connect_gateway(monkeypatch, transport):
    monkeypatch.setattr(
        retry_module,
        "criar_http_client",
        lambda: httpx.AsyncClient(transport=transport),
    )
    monkeypatch.setattr(
        services,
        "processar_pagamento_externo",
        retry_module.processar_pagamento_externo.retry_with(
            wait=wait_none()
        ),
    )


async def send(env):
    return await env.client.post(
        "/pagamentos",
        json=PAYLOAD,
        headers={
            **env.headers[1],
            "Idempotency-Key": "gateway-test",
        },
    )


@pytest.mark.parametrize("mode,status,attempts,processed", [
    ("success", 201, 1, 1),
    ("fail_once", 201, 2, 1),
    ("always_fail", 503, 4, 0),
    ("timeout", 504, 4, 0),
])
async def test_api_to_gateway(
    environment, monkeypatch, mode, status, attempts, processed
):
    gateway = create_app(mode=mode, timeout_delay=0)
    connect_gateway(monkeypatch, httpx.ASGITransport(app=gateway))

    response = await send(environment)
    assert response.status_code == status, response.text

    key = idempotency.chave_idempotencia(1, "gateway-test")
    assert gateway.state.tentativas[key] == attempts
    assert gateway.state.processamentos.get(key, 0) == processed

    if status == 201:
        replay = await send(environment)
        assert replay.json() == response.json()
        assert gateway.state.processamentos[key] == 1


@pytest.mark.parametrize("kind,status,attempts", [
    ("timeout", 504, 4),
    ("permanent", 502, 1),
    ("invalid", 502, 1),
])
async def test_http_failures(
    environment, monkeypatch, kind, status, attempts
):
    calls = []

    def handle(request):
        calls.append(request.headers["Idempotency-Key"])

        if kind == "timeout":
            raise httpx.ReadTimeout(
                "Timeout de teste", request=request
            )

        if kind == "permanent":
            return httpx.Response(
                400, json={"detail": "Dados recusados"}
            )

        return httpx.Response(
            200, json={"aprovado": "invalido"}
        )

    connect_gateway(monkeypatch, httpx.MockTransport(handle))

    response = await send(environment)
    assert response.status_code == status, response.text
    assert len(calls) == attempts
    assert len(set(calls)) == 1


async def test_gateway_itself_does_not_process_the_same_key_twice():
    gateway = create_app(mode="success")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway",
    ) as client:
        headers = {"Idempotency-Key": "same-key"}

        first = await client.post(
            "/processar", headers=headers, json=PAYLOAD
        )
        replay = await client.post(
            "/processar", headers=headers, json=PAYLOAD
        )
        conflict = await client.post(
            "/processar",
            headers=headers,
            json={**PAYLOAD, "valor": 20},
        )

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert conflict.status_code == 409
    assert gateway.state.processamentos["same-key"] == 1