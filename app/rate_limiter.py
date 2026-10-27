import time
import logging
import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings
from app.auth import usuario_logado
from app.models import Usuario

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

# ─── Operação base ────────────────────────────────

async def checar_limite(chave: str, limite: int, janela_segundos: int) -> dict:
    try:
        agora = int(time.time())
        chave_redis = f"rate_limit:{chave}:{agora // janela_segundos}"

        contagem = await redis.incr(chave_redis)

        if contagem ==1:
            await redis.expire(chave_redis, janela_segundos)

        restantes = max(0, limite - contagem)
        resetar_em = (agora // janela_segundos + 1) * janela_segundos - agora

        return {
            "contagem":  contagem,
            "limite":    limite,
            "restantes": restantes,
            "resetar_em": resetar_em,
            "bloqueado": contagem > limite
        }
    except Exception as e:
        logger.warning(f"Rate limiter falhou: {e}")
        return {
            "contagem": 0, "limite": limite,
            "restantes": limite, "resetar_em": 60,
            "bloqueado": False
        }
    
# ─── Middleware — por IP ──────────────────────────

async def rate_limit_middleware(request: Request, call_next):
    ip = request.client.host if request.client else "desconhecido"

    info = await checar_limite(
        chave=f"ip:{ip}",
        limite=100,
        janela_segundos=60
    ) 
    
    if info["bloqueado"]:
        logger.warning(f"Rate limit por IP: {ip}")
        return JSONResponse(
            status_code=429,
            headers={
                "X-RateLimit-Limit":     str(info["limite"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset":     str(info["resetar_em"]),
                "Retry-After":           str(info["resetar_em"])
            },
            content={"detail": f"Muitas requisições. Tente em {info['resetar_em']}s."}
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"]     = str(info["limite"])
    response.headers["X-RateLimit-Remaining"] = str(info["restantes"])
    response.headers["X-RateLimit-Reset"]     = str(info["resetar_em"])

    return response

# ─── Dependency — por usuário logado ─────────────

def limite_por_usuario(limite: int = 60, janela_segundos: int = 60):
    async def checar(usuario: Usuario = Depends(usuario_logado)):
        info = await checar_limite(
            chave=f"usuario:{usuario.id}",
            limite=limite,
            janela_segundos=janela_segundos
        )

        if info["bloqueado"]:
            logger.warning(f"Rate limit por usuário id={usuario.id}")
            raise HTTPException(
                status_code=429,
                headers={"Retry-After": str(info["resetar_em"])},
                detail=f"Limite de {limite} requests/{janela_segundos}s atingido."
            )

        return info

    return checar


# ─── Dependency — por IP (para login/registro) ───

def limite_por_ip(limite: int = 10, janela_segundos: int = 60):
    async def checar(request: Request):
        ip = request.client.host if request.client else "desconhecido"

        info = await checar_limite(
            chave=f"login:{ip}",
            limite=limite,
            janela_segundos=janela_segundos
        )

        if info["bloqueado"]:
            logger.warning(f"Rate limit de login por IP: {ip}")
            raise HTTPException(
                status_code=429,
                headers={"Retry-After": str(info["resetar_em"])},
                detail=f"Muitas tentativas. Tente em {info['resetar_em']}s."
            )

    return checar
