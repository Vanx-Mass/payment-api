from unittest.mock import AsyncMock

import pytest

from app import services


@pytest.mark.parametrize('payment_id', [-1, 0, 2_147_483_648, 9_223_372_036_854_775_808])
async def test_id_fora_da_faixa_do_banco_e_rejeitado_antes_da_consulta(
    environment, monkeypatch, payment_id
):
    lookup = AsyncMock(side_effect=AssertionError('ID invalido chegou ao banco'))
    monkeypatch.setattr(services, 'buscar_pagamento', lookup)
    response = await environment.client.get(
        f'/pagamentos/{payment_id}', headers=environment.headers[1]
    )
    assert response.status_code == 422
    lookup.assert_not_awaited()
