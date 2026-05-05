import asyncio
import logging
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log
)
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ─── Exceções ─────────────────────────────────────

class ErroTemporario(Exception):
    pass

class ErroPermanente(Exception):
    pass

# ─── Timeout HTTP ─────────────────────────────────

TIMEOUT_HTTP = httpx.Timeout(
    connect=3.0,
    read=5.0,
    write=3.0,
    pool=2.0
)


def criar_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_HTTP)


# ─── Decorator de retry ───────────────────────────

def retry_padrao(func):
    return retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(ErroTemporario),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )(func)


# ─── Timeout de operação ──────────────────────────

async def com_timeout(coroutine, segundos: float, operacao: str = "Operação"):
    try:
        return await asyncio.wait_for(coroutine, timeout=segundos)
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout em '{operacao}' após {segundos}s")
        raise HTTPException(
            status_code=504,
            detail=f"{operacao} demorou demais. Tente novamente."
        )


# ─── Simulação de processador de pagamento ────────

@retry_padrao
async def processar_pagamento_externo(valor: float, descricao: str) -> dict:
    try:
        async with criar_http_client() as client:
            await asyncio.sleep(0.1)

            return {
                "aprovado": True,
                "codigo_autorizacao": "AUTH-12345",
                "valor": valor,
                "descricao": descricao
            }

    except httpx.TimeoutException:
        raise ErroTemporario("Timeout no processador de pagamento")

    except httpx.ConnectError:
        raise ErroTemporario("Processador de pagamento indisponível")