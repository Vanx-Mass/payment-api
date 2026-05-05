from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import Usuario, Pagamento, StatusPagamento
from app.schemas import RegistroInput, PagamentoInput
from app.auth import hash_senha, verificar_senha, criar_token
from app.cache import invalidar_cache_usuario
import logging
from app.retry import processar_pagamento_externo, com_timeout

logger = logging.getLogger(__name__)

class Database:
    def connect(self):
        logger.info("Conectando ao banco...")

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException
from app.models import Usuario, Pagamento, StatusPagamento
from app.schemas import RegistroInput, PagamentoInput
from app.auth import hash_senha, verificar_senha, criar_token
from app.cache import invalidar_cache_usuario


# ─── Auth ─────────────────────────────────────────

async def registrar_usuario(dados: RegistroInput, db: AsyncSession) -> dict:
    existe = await db.execute(
        select(Usuario).where(Usuario.email == dados.email)
    )
    if existe.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email já cadastrado")

    usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha_hash=hash_senha(dados.senha)
    )
    db.add(usuario)
    await db.commit()
    await db.refresh(usuario)

    return {"token": criar_token(usuario.id), "nome": usuario.nome}


async def autenticar_usuario(email: str, senha: str, db: AsyncSession) -> dict:
    resultado = await db.execute(
        select(Usuario).where(Usuario.email == email)
    )
    usuario = resultado.scalar_one_or_none()

    if not usuario or not verificar_senha(senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    return {"token": criar_token(usuario.id), "nome": usuario.nome}


# ─── Pagamentos ───────────────────────────────────

async def criar_pagamento(
    dados: PagamentoInput,
    usuario_id: int,
    db: AsyncSession
) -> Pagamento:
    
    await com_timeout(
        processar_pagamento_externo(dados.valor, dados.descricao),
        segundos=30.0,
        operacao="Processador de pagamento"
    )

    pagamento = Pagamento(
        usuario_id=usuario_id,
        valor=dados.valor,
        descricao=dados.descricao,
        status=StatusPagamento.APROVADO 
    )
    db.add(pagamento)
    await db.commit()
    await db.refresh(pagamento)

    await invalidar_cache_usuario(usuario_id)

    return pagamento


async def listar_pagamentos(usuario_id: int, db: AsyncSession) -> list[Pagamento]:
    resultado = await db.execute(
        select(Pagamento)
        .where(Pagamento.usuario_id == usuario_id)
        .order_by(Pagamento.criado_em.desc())
    )
    return resultado.scalars().all()


async def buscar_pagamento(
    pagamento_id: int,
    usuario_id: int,
    db: AsyncSession
) -> Pagamento:
    pagamento = await db.execute(
        select(Pagamento).where(
            Pagamento.id == pagamento_id,
            Pagamento.usuario_id == usuario_id
        )
    )
    pagamento = pagamento.scalar_one_or_none()

    if not pagamento:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")

    return pagamento


# ─── Saldo ────────────────────────────────────────

async def calcular_saldo(usuario_id: int, db: AsyncSession) -> dict:
    resultado = await db.execute(
        select(
            func.coalesce(func.sum(Pagamento.valor), 0).label("total"),
            func.count(Pagamento.id).filter(
                Pagamento.status == StatusPagamento.APROVADO
            ).label("aprovados"),
            func.count(Pagamento.id).filter(
                Pagamento.status == StatusPagamento.RECUSADO
            ).label("recusados"),
            func.count(Pagamento.id).filter(
                Pagamento.status == StatusPagamento.ESTORNADO
            ).label("estornados"),
        ).where(Pagamento.usuario_id == usuario_id)
    )
    row = resultado.one()

    return {
        "saldo_total":    round(float(row.total), 2),
        "total_aprovado": row.aprovados,
        "total_recusado": row.recusados,
        "total_estornado": row.estornados,
    }

