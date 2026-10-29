from fastapi import APIRouter, Depends, Header, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.schemas import (
    RegistroInput, LoginInput, AuthResponse,
    PagamentoInput, PagamentoResponse, HistoricoResponse, SaldoResponse
)
from app.auth import usuario_logado
from app.models import Usuario
from app.cache import get_cache, set_cache
from app.idempotency import (
    chave_idempotencia, checar_idempotencia, hash_requisicao,
    proteger_idempotencia, salvar_idempotencia,
)
from app.rate_limiter import limite_por_usuario, limite_por_ip
from app import services

import json


router = APIRouter()

# ─── Auth ─────────────────────────────────────────
@router.post("/auth/registro", response_model=AuthResponse, status_code=201)
async def registro(
    dados: RegistroInput,
    db: AsyncSession = Depends(get_db)
):
    return await services.registrar_usuario(dados, db)

@router.post("/auth/login", response_model=AuthResponse)
async def login(
    dados: LoginInput,
    db: AsyncSession = Depends(get_db),
    _rl= Depends(limite_por_ip(limite=10, janela_segundos=60))
):
    return await services.autenticar_usuario(dados.email, dados.senha, db)

# ─── Pagamentos ───────────────────────────────────
@router.post("/pagamentos", response_model=PagamentoResponse, status_code=201)
async def criar_pagamento(
    dados: PagamentoInput,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(usuario_logado),
    _rl= Depends(limite_por_usuario(limite=60)),
    idempotency_key: Optional[str] = Header(None, max_length=255)
):
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=400,
            detail="Header Idempotency-Key obrigatório"
        )
    
    requisicao = dados.model_dump(mode="json")
    chave_banco = chave_idempotencia(usuario.id, idempotency_key)
    requisicao_hash = hash_requisicao(requisicao)
    async with proteger_idempotencia(usuario.id, idempotency_key):
        resultado_anterior = await checar_idempotencia(
            usuario.id, idempotency_key, requisicao
        )
        if resultado_anterior is not None:
            return resultado_anterior

        pagamento = await services.buscar_pagamento_idempotente(
            usuario.id, chave_banco, requisicao_hash, db
        )
        if pagamento is None:
            pagamento = await services.criar_pagamento(
                dados, usuario.id, db,
                chave_idempotencia=chave_banco, requisicao_hash=requisicao_hash,
            )
        resultado = PagamentoResponse.model_validate(pagamento).model_dump(mode="json")
        await salvar_idempotencia(
            usuario.id, idempotency_key, requisicao, resultado
        )
        return resultado

@router.get("/pagamentos", response_model=HistoricoResponse)
async def listar_pagamentos(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(usuario_logado),
    _rl = Depends(limite_por_usuario(limite=60))
):
    chave_cache = f"historico:{usuario.id}"

    cache = await get_cache(chave_cache)
    if cache:
        return json.loads(cache)
    
    pagamentos = await services.listar_pagamentos(usuario.id, db)
    resposta = HistoricoResponse(
        total=len(pagamentos),
        pagamentos=pagamentos
    )
    await set_cache(chave_cache, resposta.model_dump(mode="json"), ttl=60)
    return resposta
    
@router.get("/pagamentos/{pagamento_id}", response_model=PagamentoResponse)
async def buscar_pagamento(
    pagamento_id: int = Path(ge=1, le=2_147_483_647),
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(usuario_logado),
    _rl= Depends(limite_por_usuario(limite=60))
):
    chave_cache = f"pagamento:{pagamento_id}:{usuario.id}"

    cache = await get_cache(chave_cache)
    if cache:
        return json.loads(cache)
    
    pagamento = await services.buscar_pagamento(pagamento_id, usuario.id, db)
    resultado = PagamentoResponse.model_validate(pagamento).model_dump(mode="json")
    await set_cache(chave_cache, resultado, ttl=60)

    return resultado

# ─── Saldo ────────────────────────────────────────
@router.get("/saldo", response_model=SaldoResponse)
async def saldo(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(usuario_logado),
    _rl = Depends(limite_por_usuario(limite=60))
):
    chave_cache = f"saldo:{usuario.id}"

    cache = await get_cache(chave_cache)
    if cache:
        return json.loads(cache)
    
    resultado = await services.calcular_saldo(usuario.id, db)
    await set_cache(chave_cache, resultado, ttl=30)

    return resultado
