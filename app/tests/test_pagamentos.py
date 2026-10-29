import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import jwt

from app import auth, cache, rate_limiter, services
from app.logging_config import setup_logging


async def test_payment_lookup_and_cache(environment, monkeypatch):
    env = environment
    first = await env.client.get('/pagamentos/1', headers=env.headers[1])
    assert first.status_code == 200, first.text
    assert first.json()['id'] == 1
    assert json.loads(env.redis.values['pagamento:1:1']) == first.json()
    lookup = AsyncMock(side_effect=AssertionError('Consulta repetida no banco'))
    monkeypatch.setattr(services, 'buscar_pagamento', lookup)
    cached = await env.client.get('/pagamentos/1', headers=env.headers[1])
    assert cached.status_code == 200
    assert cached.json() == first.json()
    lookup.assert_not_awaited()


async def test_payment_owner_is_checked_even_after_cache(environment):
    env = environment
    assert (await env.client.get('/pagamentos/1', headers=env.headers[1])).status_code == 200
    assert (await env.client.get('/pagamentos/1', headers=env.headers[2])).status_code == 404
    assert (await env.client.get('/pagamentos/999', headers=env.headers[1])).status_code == 404


async def test_history_cache(environment, monkeypatch):
    env = environment
    first = await env.client.get('/pagamentos', headers=env.headers[1])
    assert first.status_code == 200
    assert first.json()['total'] == 4
    assert json.loads(env.redis.values['historico:1']) == first.json()
    lookup = AsyncMock(side_effect=AssertionError('Consulta repetida no banco'))
    monkeypatch.setattr(services, 'listar_pagamentos', lookup)
    cached = await env.client.get('/pagamentos', headers=env.headers[1])
    assert cached.json() == first.json()
    lookup.assert_not_awaited()


async def test_balance_uses_only_approved_payments(environment):
    env = environment
    response = await env.client.get('/saldo', headers=env.headers[1])
    assert response.status_code == 200
    assert response.json() == {'saldo_total': 12.34, 'total_aprovado': 1,
                               'total_recusado': 1, 'total_estornado': 1}


async def test_create_invalidates_only_owners_history_and_balance(environment):
    env = environment
    for user_id in (1, 2):
        for path in ('/pagamentos', '/saldo'):
            assert (await env.client.get(path, headers=env.headers[user_id])).status_code == 200
    response = await env.client.post('/pagamentos',
                                     headers={**env.headers[1], 'Idempotency-Key': 'new'},
                                     json={'valor': 25, 'descricao': 'Novo pagamento'})
    assert response.status_code == 201, response.text
    assert 'historico:1' not in env.redis.values and 'saldo:1' not in env.redis.values
    assert 'historico:2' in env.redis.values and 'saldo:2' in env.redis.values
    assert (await env.client.get('/pagamentos', headers=env.headers[1])).json()['total'] == 5
    assert (await env.client.get('/saldo', headers=env.headers[1])).json()['saldo_total'] == 37.34


async def test_user_rate_limit_is_enforced(environment, monkeypatch):
    env = environment

    async def check(chave, limite, janela_segundos):
        blocked = chave.startswith('usuario:')
        return {'bloqueado': blocked, 'limite': limite, 'restantes': 0,
                'resetar_em': 20, 'contagem': limite + 1 if blocked else 1}

    monkeypatch.setattr(rate_limiter, 'checar_limite', check)
    response = await env.client.get('/pagamentos', headers=env.headers[1])
    assert response.status_code == 429
    assert response.headers['retry-after'] == '20'


@pytest.mark.parametrize('value', [0, -1, 0.001, 'NaN', 'Infinity'])
async def test_invalid_amount_returns_422(environment, value):
    env = environment
    response = await env.client.post('/pagamentos',
                                     headers={**env.headers[1], 'Idempotency-Key': 'invalid'},
                                     json={'valor': value, 'descricao': 'Compra teste'})
    assert response.status_code == 422, response.text
    env.processor.assert_not_awaited()


@pytest.mark.parametrize('payload', [
    {'nome': '  ', 'senha': '123456'},
    {'nome': 'x' * 101, 'senha': '123456'},
    {'nome': 'Teste', 'senha': 'á' * 40},
])
async def test_invalid_registration_returns_422(environment, payload):
    response = await environment.client.post('/auth/registro',
                                              json={**payload, 'email': 'novo@example.com'})
    assert response.status_code == 422


@pytest.mark.parametrize('subject', ['abc', '-1', '0'])
async def test_invalid_token_subject_returns_401(environment, subject):
    token = jwt.encode({'sub': subject, 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, auth.settings.secret_key, algorithm='HS256')
    response = await environment.client.get('/pagamentos',
                                             headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 401, response.text


def test_redis_plain_connections_construct_without_tls_arguments():
    for module in (cache, rate_limiter):
        connection = module.redis.connection_pool.make_connection()
        assert connection.host == 'localhost'


def test_logging_setup_does_not_duplicate_handlers():
    setup_logging()
    setup_logging()
    assert sum(handler.name == 'payment-api' for handler in logging.getLogger().handlers) == 1


async def test_register_login_and_duplicate_email(environment):
    env = environment
    details = {'nome': '  Novo usuario  ', 'email': 'novo@example.com', 'senha': 'senha123'}
    created = await env.client.post('/auth/registro', json=details)
    assert created.status_code == 201, created.text
    assert created.json()['nome'] == 'Novo usuario'
    login = await env.client.post('/auth/login',
                                   json={'email': details['email'], 'senha': details['senha']})
    assert login.status_code == 200, login.text
    assert 'token' in login.json()
    duplicate = await env.client.post('/auth/registro', json=details)
    assert duplicate.status_code == 400
    wrong = await env.client.post('/auth/login',
                                   json={'email': details['email'], 'senha': 'errada'})
    assert wrong.status_code == 401


async def test_refused_payment_is_not_marked_approved(environment):
    env = environment
    env.processor.return_value = {'aprovado': False}
    payment = await env.client.post('/pagamentos',
                                    headers={**env.headers[1], 'Idempotency-Key': 'refused'},
                                    json={'valor': 20, 'descricao': 'Pagamento recusado'})
    assert payment.status_code == 201
    assert payment.json()['status'] == 'recusado'
    balance = await env.client.get('/saldo', headers=env.headers[1])
    assert balance.json()['saldo_total'] == 12.34
