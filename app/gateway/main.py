import asyncio
import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.gateway.ledger import Ledger
from app.logging_config import setup_logging
from app.telemetry import configure_http, tracer_for

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class PagamentoInput(BaseModel):
    valor: float = Field(gt=0, allow_inf_nan=False)
    descricao: str = Field(min_length=3, max_length=255)


def create_app(mode=None, timeout_delay=6):
    mode = mode or os.getenv("GATEWAY_MODE", "success")

    if mode not in {"success", "fail_once", "always_fail", "timeout"}:
        raise ValueError(f"GATEWAY_MODE inválido: {mode}")

    ledger_path = os.getenv("GATEWAY_LEDGER_PATH")
    ledger = Ledger(ledger_path) if ledger_path else None
    reconciliation_token = os.getenv("RECONCILIATION_TOKEN")
    provider = tracer_for("gateway")
    if provider:
        setup_logging()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if provider:
            provider.shutdown()

    app = FastAPI(title="Gateway simulado", lifespan=lifespan)
    app.state.resultados = {}
    app.state.tentativas = {}
    app.state.processamentos = {}
    lock = asyncio.Lock()

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": mode}

    @app.post("/processar")
    async def processar(
        dados: PagamentoInput,
        idempotency_key: str = Header(..., min_length=1, max_length=255),
    ):
        payload = dados.model_dump(mode="json")

        async with lock:
            anterior = ledger.find(idempotency_key) if ledger else app.state.resultados.get(idempotency_key)

            if anterior:
                if anterior["payload"] != payload:
                    raise HTTPException(409, "Chave já usada com outros dados")
                return anterior["resposta"]

            tentativa = app.state.tentativas.get(idempotency_key, 0) + 1
            app.state.tentativas[idempotency_key] = tentativa

            if mode == "always_fail" or (
                mode == "fail_once" and tentativa == 1
            ):
                raise HTTPException(503, "Falha temporária simulada")

            if mode != "timeout":
                codigo = hashlib.sha256(
                    idempotency_key.encode()
                ).hexdigest()[:16]

                resposta = {
                    "aprovado": True,
                    "codigo_autorizacao": f"AUTH-{codigo}",
                }

                if ledger:
                    ledger.save(idempotency_key, payload, resposta)
                    app.state.tentativas.pop(idempotency_key, None)
                else:
                    app.state.resultados[idempotency_key] = {
                        "payload": payload,
                        "resposta": resposta,
                    }
                    app.state.processamentos[idempotency_key] = 1
                return resposta

        await asyncio.sleep(timeout_delay)
        raise HTTPException(504, "Timeout simulado")

    if ledger and reconciliation_token:
        @app.get("/internal/ledger", include_in_schema=False)
        async def ledger_window(start: datetime, end: datetime, authorization: str = Header(default="")):
            expected = f"Bearer {reconciliation_token}".encode()
            if not secrets.compare_digest(authorization.encode(), expected):
                raise HTTPException(401, "Credencial de conciliação inválida")
            if start.tzinfo is None or end.tzinfo is None or start >= end:
                raise HTTPException(422, "Janela inválida")
            return ledger.window(
                start.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                end.astimezone(timezone.utc).isoformat(timespec="microseconds"),
            )

    configure_http(app, "gateway", provider)
    return app


app = create_app()