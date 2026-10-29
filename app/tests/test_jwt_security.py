from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import auth


@pytest.mark.parametrize('payload', [
    {'sub': '1'},
    {'sub': '1', 'exp': datetime.now(timezone.utc) - timedelta(minutes=1)},
    {'exp': datetime.now(timezone.utc) + timedelta(minutes=1)},
])
def test_rejeita_token_sem_claims_obrigatorias_ou_expirado(payload):
    token = jwt.encode(payload, auth.settings.secret_key, algorithm='HS256')
    assert auth.decodificar_token(token) is None


def test_rejeita_token_assinado_com_outra_chave():
    payload = {'sub': '1', 'exp': datetime.now(timezone.utc) + timedelta(minutes=1)}
    token = jwt.encode(payload, 'chave-de-teste-diferente-com-mais-de-32-bytes', algorithm='HS256')
    assert auth.decodificar_token(token) is None


def test_token_emitido_pela_api_preserva_usuario():
    assert auth.decodificar_token(auth.criar_token(7)) == 7
