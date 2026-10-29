import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from security import zap_hooks


def test_zap_comprova_resposta_autenticada_pela_api_real_do_cliente(tmp_path, monkeypatch):
    proof = tmp_path / 'auth-proof.json'
    monkeypatch.setattr(zap_hooks, 'Path', lambda _: proof)
    access_url = Mock(return_value=[{'responseHeader': 'HTTP/1.1 200 OK\r\n'}])
    zap = SimpleNamespace(core=SimpleNamespace(access_url=access_url))
    zap_hooks.zap_started(zap, '/zap/wrk/openapi.json')
    access_url.assert_called_once_with('http://api:8000/saldo', followredirects=False)
    assert json.loads(proof.read_text())['authenticated_request_status'] == 200


@pytest.mark.parametrize('messages', [
    [{'responseHeader': 'HTTP/1.1 401 Unauthorized\r\n'}],
    [{'responseHeader': 'HTTP/1.1 429 Too Many Requests\r\n'}],
    [],
    {'responseHeader': 'HTTP/1.1 200 OK\r\n'},
])
def test_zap_nao_aceita_erro_ou_formato_invalido_como_prova_de_autenticacao(
    tmp_path, monkeypatch, messages
):
    proof = tmp_path / 'auth-proof.json'
    monkeypatch.setattr(zap_hooks, 'Path', lambda _: proof)
    zap = SimpleNamespace(core=SimpleNamespace(access_url=Mock(return_value=messages)))
    with pytest.raises(RuntimeError):
        zap_hooks.zap_started(zap, '/zap/wrk/openapi.json')
    assert not proof.exists()
