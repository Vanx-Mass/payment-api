import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///:memory:'
os.environ['SECRET_KEY'] = 'isolated-test-secret-without-production-access'
os.environ['REDIS_URL'] = 'redis://localhost:6379'

import httpx
import pytest_asyncio
from redis.exceptions import ConnectionError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import cache, idempotency, rate_limiter, services
from app.auth import criar_token
from app.database import Base, get_db
from app.main import app
from app.models import Pagamento, StatusPagamento, Usuario


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}
        self.unavailable = False
        self.fail_result_writes = False

    def check(self):
        if self.unavailable:
            raise ConnectionError('Redis indisponível no teste')

    async def get(self, key):
        self.check()
        return self.values.get(key)

    async def set(self, key, value, nx=False, ex=None):
        self.check()
        if nx and key in self.values:
            return None
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def setex(self, key, ttl, value):
        self.check()
        if self.fail_result_writes and key.startswith('idempotency:'):
            raise ConnectionError('Falha ao salvar resultado no teste')
        self.values[key] = value
        self.ttls[key] = ttl

    async def delete(self, key):
        self.check()
        self.ttls.pop(key, None)
        return int(self.values.pop(key, None) is not None)

    async def eval(self, script, key_count, key, owner):
        self.check()
        if self.values.get(key) == owner:
            return await self.delete(key)
        return 0

    async def incr(self, key):
        self.check()
        self.values[key] = int(self.values.get(key, 0)) + 1
        return self.values[key]

    async def expire(self, key, ttl):
        self.check()
        self.ttls[key] = ttl


@pytest_asyncio.fixture
async def environment(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        db.add_all([
            Usuario(id=1, nome='Usuario Um', email='um@example.com', senha_hash='unused'),
            Usuario(id=2, nome='Usuario Dois', email='dois@example.com', senha_hash='unused'),
            Pagamento(id=1, usuario_id=1, valor=12.34, descricao='Compra um',
                      status=StatusPagamento.APROVADO, criado_em=datetime(2026, 1, 1)),
            Pagamento(id=2, usuario_id=2, valor=77, descricao='Compra dois',
                      status=StatusPagamento.APROVADO, criado_em=datetime(2026, 1, 1)),
            Pagamento(id=3, usuario_id=1, valor=8, descricao='Compra recusada',
                      status=StatusPagamento.RECUSADO, criado_em=datetime(2026, 1, 1)),
            Pagamento(id=4, usuario_id=1, valor=5, descricao='Compra pendente',
                      status=StatusPagamento.PENDENTE, criado_em=datetime(2026, 1, 1)),
            Pagamento(id=5, usuario_id=1, valor=3, descricao='Compra estornada',
                      status=StatusPagamento.ESTORNADO, criado_em=datetime(2026, 1, 1)),
        ])
        await db.commit()

    async def isolated_db():
        async with sessions() as db:
            yield db

    fake_redis = FakeRedis()
    for module in (cache, idempotency, rate_limiter):
        monkeypatch.setattr(module, 'redis', fake_redis)
    processor = AsyncMock(return_value={'aprovado': True})
    monkeypatch.setattr(services, 'processar_pagamento_externo', processor)
    app.dependency_overrides[get_db] = isolated_db
    headers = {user_id: {'Authorization': 'Bearer ' + criar_token(user_id)}
               for user_id in (1, 2)}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url='http://test') as client:
            yield SimpleNamespace(client=client, redis=fake_redis, headers=headers,
                                  processor=processor, sessions=sessions)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
