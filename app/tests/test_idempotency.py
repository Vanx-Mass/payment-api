import asyncio

from app import idempotency, services
from app.retry import ErroTemporario

PAYMENT = {'valor': 10, 'descricao': 'Compra teste'}


async def send(env, key='order-1', user=1, payload=None):
    headers = {**env.headers[user]}
    if key is not None:
        headers['Idempotency-Key'] = key
    return await env.client.post('/pagamentos', headers=headers,
                                 json=payload if payload is not None else PAYMENT)


async def test_header_is_required(environment):
    for key in (None, '', '   '):
        response = await send(environment, key=key)
        assert response.status_code == 400, response.text
    environment.processor.assert_not_awaited()


async def test_repeated_key_returns_same_payment_and_calls_processor_once(environment):
    first = await send(environment)
    second = await send(environment)
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    environment.processor.assert_awaited_once()


async def test_same_key_is_independent_between_users(environment):
    first = await send(environment, user=1)
    second = await send(environment, user=2)
    assert first.status_code == second.status_code == 201
    assert first.json()['id'] != second.json()['id']
    assert environment.processor.await_count == 2


async def test_reusing_key_with_other_body_returns_409(environment):
    assert (await send(environment)).status_code == 201
    response = await send(environment, payload={**PAYMENT, 'valor': 20})
    assert response.status_code == 409, response.text
    environment.processor.assert_awaited_once()


async def test_simultaneous_same_key_does_not_process_twice(environment, monkeypatch):
    env = environment
    entered, release = asyncio.Event(), asyncio.Event()

    async def processor(*args):
        entered.set()
        await release.wait()
        return {'aprovado': True}

    monkeypatch.setattr(services, 'processar_pagamento_externo', processor)
    first_task = asyncio.create_task(send(env))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        second = await send(env)
        assert second.status_code == 409
    finally:
        release.set()
        first = await first_task
    assert first.status_code == 201
    replay = await send(env)
    assert replay.json() == first.json()


async def test_redis_unavailable_prevents_processing(environment):
    environment.redis.unavailable = True
    response = await send(environment)
    assert response.status_code == 503, response.text
    environment.processor.assert_not_awaited()


async def test_lock_is_released_after_processor_failure(environment):
    env = environment
    env.processor.side_effect = ErroTemporario('offline')
    response = await send(env)
    assert response.status_code == 503, response.text
    assert not any(key.endswith(':lock') for key in env.redis.values)
    env.processor.side_effect = None
    assert (await send(env)).status_code == 201


async def test_lock_does_not_delete_another_owners_reservation(environment):
    env = environment
    lock_key = idempotency.chave_idempotencia(1, 'owner') + ':lock'
    async with idempotency.proteger_idempotencia(1, 'owner'):
        env.redis.values[lock_key] = 'replacement-owner'
    assert env.redis.values[lock_key] == 'replacement-owner'


async def test_replay_survives_lost_redis_result(environment):
    env = environment
    first = await send(env)
    await env.redis.delete(idempotency.chave_idempotencia(1, 'order-1'))
    second = await send(env)
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    env.processor.assert_awaited_once()


async def test_database_replay_rejects_different_body(environment):
    env = environment
    assert (await send(env)).status_code == 201
    await env.redis.delete(idempotency.chave_idempotencia(1, 'order-1'))
    changed = await send(env, payload={**PAYMENT, 'valor': 20})
    assert changed.status_code == 409
    env.processor.assert_awaited_once()


async def test_result_write_failure_does_not_create_another_payment(environment):
    env = environment
    env.redis.fail_result_writes = True
    assert (await send(env)).status_code == 503
    assert (await send(env)).status_code == 503
    env.redis.fail_result_writes = False
    recovered = await send(env)
    assert recovered.status_code == 201
    env.processor.assert_awaited_once()
    history = await env.client.get('/pagamentos', headers=env.headers[1])
    assert history.json()['total'] == 5
