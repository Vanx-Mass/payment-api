from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from app.database import get_db
from app.models import Usuario


bearer = HTTPBearer()


class Settings(BaseSettings):
    secret_key: str
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()

pwd = CryptContext(schemes=["bcrypt"])

TOKEN_EXPIRACAO_HORAS = 24
ALGORITMO = "HS256"

# ─── Senha ────────────────────────────────────────

def hash_senha(senha: str) -> str:
    return pwd.hash(senha)

def verificar_senha(senha: str, hash: str) -> bool:
    return pwd.verify(senha, hash)

# ─── Token ────────────────────────────────────────

def criar_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRACAO_HORAS)

    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def decodificar_token(token: str) -> int | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITMO],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
        return user_id if user_id > 0 else None
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
    
# ─── Dependency ───────────────────────────────────

async def usuario_logado(
        creds: HTTPAuthorizationCredentials = Depends(bearer),
        db: AsyncSession = Depends(get_db)
) -> Usuario:
    user_id = decodificar_token(creds.credentials)

    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")
    
    usuario = await db.get(Usuario, user_id)

    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    
    return usuario
