import json
import re
from pathlib import Path


def zap_started(zap, target):
    messages = zap.core.access_url('http://api:8000/saldo', followredirects=False)
    if not isinstance(messages, list) or len(messages) != 1:
        raise RuntimeError('ZAP nao retornou uma unica resposta HTTP para /saldo.')
    response = messages[0]
    if not isinstance(response, dict) or not re.match(
        r'HTTP/\S+\s+200\b', response.get('responseHeader', '')
    ):
        raise RuntimeError('ZAP nao conseguiu acessar /saldo com autenticacao.')
    Path('/zap/wrk/auth-proof.json').write_text(
        json.dumps({'authenticated_request_status': 200}), encoding='utf-8'
    )


def zap_tuned(zap):
    zap.ascan.set_option_thread_per_host(2)
