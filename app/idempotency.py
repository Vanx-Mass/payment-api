# app/idempotency.py
import json
import logging
import redis.asyncio as aioredis
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

redis = aioredis.from_url(settings.redis_url, decode_responses=True)

TTL = 60 * 60 * 24  # 24 horas


# ─── Operações base ───────────────────────────────

async def checar_idempotencia(chave: str) -> dict | None:
    try:
        resultado = await redis.get(f"idempotency:{chave}")
        if resultado:
            logger.info(f"Idempotency hit para chave '{chave}'")
            return json.loads(resultado)
        return None
    except Exception as e:
        logger.warning(f"Redis idempotency check falhou: {e}")
        return None


async def salvar_idempotencia(chave: str, resultado: dict) -> None:
    try:
        await redis.setex(
            f"idempotency:{chave}",
            TTL,
            json.dumps(resultado)
        )
        logger.info(f"Idempotency salvo para chave '{chave}'")
    except Exception as e:
        logger.warning(f"Redis idempotency save falhou: {e}")