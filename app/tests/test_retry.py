import asyncio

import pytest
from fastapi import HTTPException
from tenacity import wait_none

from app.retry import ErroPermanente, ErroTemporario, com_timeout, retry_padrao


async def test_two_transient_failures_then_success():
    calls = 0

    @retry_padrao
    async def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ErroTemporario('offline')
        return {'aprovado': True}

    result = await operation.retry_with(wait=wait_none())()
    assert result == {'aprovado': True}
    assert calls == 3


async def test_exhausted_retry_returns_503_after_four_attempts():
    calls = 0

    @retry_padrao
    async def operation():
        nonlocal calls
        calls += 1
        raise ErroTemporario('offline')

    with pytest.raises(HTTPException) as error:
        await com_timeout(operation.retry_with(wait=wait_none())(), segundos=2)
    assert error.value.status_code == 503
    assert calls == 4


async def test_permanent_failure_is_not_retried_and_returns_502():
    calls = 0

    @retry_padrao
    async def operation():
        nonlocal calls
        calls += 1
        raise ErroPermanente('recusado')

    with pytest.raises(HTTPException) as error:
        await com_timeout(operation.retry_with(wait=wait_none())(), segundos=2)
    assert error.value.status_code == 502
    assert calls == 1


async def test_operation_timeout_returns_504():
    with pytest.raises(HTTPException) as error:
        await com_timeout(asyncio.sleep(1), segundos=0.001)
    assert error.value.status_code == 504
