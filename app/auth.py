from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic_settings import BaseSettings
from app.database import get_db
from app.models import Usuario

import logging

bearer = HTTPBearer()


logger = logging.getLogger(__name__)

class Database:
    def connect(self):
        logger.info("Conectando ao banco...")

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
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRACAO_HORAS)

    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO)


def decodificar_token(token: str) -> int |None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITMO])
        return int(payload["sub"])
    except JWTError:
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