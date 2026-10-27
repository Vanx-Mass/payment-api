import hashlib
import json
import logging
import secrets
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import HTTPException
from pydantic_settings import BaseSettings
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
redis = aioredis.from_url(
    settings.redis_url, decode_responses=True,
    socket_connect_timeout=2, socket_timeout=2,
)

TTL = 60 * 60 * 24
TTL_LOCK = 120
LIBERAR_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def chave_idempotencia(usuario_id: int, chave: str) -> str:
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()
    return f"idempotency:{usuario_id}:{digest}"


def hash_requisicao(requisicao: dict) -> str:
    dados = json.dumps(requisicao, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(dados.encode("utf-8")).hexdigest()


def indisponivel() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Não foi possível garantir a idempotência. Tente novamente.",
    )


@asynccontextmanager
async def proteger_idempotencia(usuario_id: int, chave: str):
    chave_lock = f"{chave_idempotencia(usuario_id, chave)}:lock"
    dono = secrets.token_hex(16)
    try:
        adquirido = await redis.set(chave_lock, dono, nx=True, ex=TTL_LOCK)
    except RedisError as exc:
        logger.warning("Redis indisponível ao reservar idempotência: %s", exc)
        raise indisponivel() from exc
    if not adquirido:
        raise HTTPException(
            status_code=409,
            detail="Pagamento com esta chave já está em processamento.",
        )
    try:
        yield
    finally:
        try:
            await redis.eval(LIBERAR_LOCK, 1, chave_lock, dono)
        except RedisError as exc:
            logger.warning("Falha ao liberar reserva de idempotência: %s", exc)


async def checar_idempotencia(
    usuario_id: int, chave: str, requisicao: dict
) -> dict | None:
    try:
        anterior = await redis.get(chave_idempotencia(usuario_id, chave))
        if anterior is None:
            return None
        registro = json.loads(anterior)
        if registro["requisicao"] != requisicao:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key já utilizada com outros dados.",
            )
        return registro["resultado"]
    except (RedisError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Falha ao consultar idempotência: %s", exc)
        raise indisponivel() from exc


async def salvar_idempotencia(
    usuario_id: int, chave: str, requisicao: dict, resultado: dict
) -> None:
    try:
        await redis.setex(
            chave_idempotencia(usuario_id, chave),
            TTL,
            json.dumps({"requisicao": requisicao, "resultado": resultado}),
        )
    except RedisError as exc:
        logger.warning("Falha ao salvar idempotência: %s", exc)
        raise indisponivel() from exc
