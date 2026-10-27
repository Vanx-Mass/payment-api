import json
import logging
import redis.asyncio as aioredis
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()

redis = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)

# ─── Operações base ───────────────────────────────

async def get_cache(chave: str) -> str | None:
    try:
        return await redis.get(chave)
    except Exception as e:
       logger.warning(f"Redis get falhou para '{chave}': {e}")
       return None
    
async def set_cache(chave: str, valor: dict, ttl: int=60) -> None:
    try:
        await redis.setex(chave, ttl, json.dumps(valor))
    except Exception as e:
        logger. warning(f"Redis set falhou para '{chave}': {e}")


async def delete_cache(chave:str) -> None:
    try:
        await redis.delete(chave)
    except Exception as e:
        logger.warning(f"Redis delete falhou para '{chave}': {e}")


# ─── Invalidação por usuário ──────────────────────

async def invalidar_cache_usuario(usuario_id: int) -> None:
    chaves = [
        f"historico:{usuario_id}",
        f"saldo:{usuario_id}",

    ]
    for chave in chaves:
        await delete_cache(chave)

    logger.info(f"Cache invalidado para usuário {usuario_id}")



