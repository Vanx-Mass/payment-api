# app/models.py
from datetime import datetime
from enum import Enum
from sqlalchemy import String, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import logging

logger = logging.getLogger(__name__)

class Database:
    def connect(self):
        logger.info("Conectando ao banco...")

class StatusPagamento(str, Enum):
    PENDENTE   = "pendente"
    APROVADO   = "aprovado"
    RECUSADO   = "recusado"
    ESTORNADO  = "estornado"


class Usuario(Base):
    __tablename__ = "usuarios"

    id:         Mapped[int]      = mapped_column(primary_key=True)
    nome:       Mapped[str]      = mapped_column(String(100))
    email:      Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str]      = mapped_column(String(255))
    criado_em:  Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="usuario")


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id:          Mapped[int]             = mapped_column(primary_key=True)
    usuario_id:  Mapped[int]             = mapped_column(ForeignKey("usuarios.id"), index=True)
    valor:       Mapped[float]           = mapped_column(Float)
    descricao:   Mapped[str]             = mapped_column(String(255))
    status:      Mapped[StatusPagamento] = mapped_column(SAEnum(StatusPagamento), default=StatusPagamento.PENDENTE)
    criado_em:   Mapped[datetime]        = mapped_column(DateTime, default=datetime.utcnow)

    usuario: Mapped["Usuario"] = relationship(back_populates="pagamentos")