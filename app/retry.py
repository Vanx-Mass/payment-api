import asyncio
import logging

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


class ErroTemporario(Exception):
    pass


class ErroPermanente(Exception):
    pass


class ErroTimeout(ErroTemporario):
    pass


class Settings(BaseSettings):
    processor_base_url: str = "http://gateway:8080"
    model_config = {"env_file": ".env", "extra": "ignore"}


class ResultadoProcessador(BaseModel):
    aprovado: bool = Field(strict=True)
    codigo_autorizacao: str | None = None


settings = Settings()

TIMEOUT_HTTP = httpx.Timeout(
    connect=3.0,
    read=5.0,
    write=3.0,
    pool=2.0,
)


def criar_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_HTTP)


def retry_padrao(func):
    return retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type(ErroTemporario),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )(func)


async def com_timeout(
    coroutine,
    segundos: float,
    operacao: str = "Operação",
):
    try:
        return await asyncio.wait_for(coroutine, timeout=segundos)

    except (asyncio.TimeoutError, ErroTimeout):
        logger.warning("Timeout em %s", operacao)
        raise HTTPException(
            status_code=504,
            detail=f"{operacao} demorou demais. Tente novamente.",
        )

    except ErroTemporario as exc:
        logger.warning("%s indisponível: %s", operacao, exc)
        raise HTTPException(
            status_code=503,
            detail=f"{operacao} indisponível. Tente novamente.",
        ) from exc

    except ErroPermanente as exc:
        logger.warning("Falha permanente em %s: %s", operacao, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Falha em {operacao}.",
        ) from exc


@retry_padrao
async def processar_pagamento_externo(
    valor: float,
    descricao: str,
    idempotency_key: str,
) -> dict:
    try:
        async with criar_http_client() as client:
            resposta = await client.post(
                f"{settings.processor_base_url.rstrip('/')}/processar",
                json={"valor": valor, "descricao": descricao},
                headers={"Idempotency-Key": idempotency_key},
            )
    except httpx.TimeoutException as exc:
        raise ErroTimeout("Timeout no gateway") from exc
    except httpx.TransportError as exc:
        raise ErroTemporario("Falha de conexão com o gateway") from exc

    if resposta.status_code == 504:
        raise ErroTimeout("Gateway retornou timeout")

    if resposta.status_code >= 500 or resposta.status_code == 429:
        raise ErroTemporario(
            f"Gateway retornou {resposta.status_code}"
        )

    if not resposta.is_success:
        raise ErroPermanente(
            f"Gateway retornou {resposta.status_code}"
        )

    try:
        return ResultadoProcessador.model_validate(
            resposta.json()
        ).model_dump()
    except ValueError as exc:
        raise ErroPermanente("Resposta inválida do gateway") from exc