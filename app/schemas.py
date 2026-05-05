from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator
import logging

logger = logging.getLogger(__name__)

class Database:
    def connect(self):
        logger.info("Conectando ao banco...")

        
# app/schemas.py
from datetime import datetime
from pydantic import BaseModel, EmailStr, field_validator
from app.models import StatusPagamento


# ─── Auth ─────────────────────────────────────────

class RegistroInput(BaseModel):
    nome:  str
    email: EmailStr
    senha: str

    @field_validator("senha")
    @classmethod
    def senha_minima(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Senha deve ter no mínimo 6 caracteres")
        return v

    @field_validator("nome")
    @classmethod
    def nome_minimo(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Nome deve ter no mínimo 2 caracteres")
        return v.strip()


class LoginInput(BaseModel):
    email: EmailStr
    senha: str


class AuthResponse(BaseModel):
    token: str
    nome:  str


# ─── Pagamentos ───────────────────────────────────

class PagamentoInput(BaseModel):
    valor:    float
    descricao: str

    @field_validator("valor")
    @classmethod
    def valor_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Valor deve ser maior que zero")
        return round(v, 2)  

    @field_validator("descricao")
    @classmethod
    def descricao_minima(cls, v: str) -> str:
        if len(v.strip()) < 3:
            raise ValueError("Descrição deve ter no mínimo 3 caracteres")
        return v.strip()


class PagamentoResponse(BaseModel):
    id:        int
    valor:     float
    descricao: str
    status:    StatusPagamento
    criado_em: datetime

    model_config = {"from_attributes": True}
  


class HistoricoResponse(BaseModel):
    total:     int
    pagamentos: list[PagamentoResponse]


# ─── Saldo ────────────────────────────────────────

class SaldoResponse(BaseModel):
    saldo_total:   float
    total_aprovado: int
    total_recusado: int
    total_estornado: int