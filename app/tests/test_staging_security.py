import json
import subprocess
import sys
from unittest.mock import Mock

import pytest

from scripts import staging

deployment_event_real = staging.deployment_event


def release(run_id):
    return {'repository': staging.REPO, 'sha': str(run_id) * 40, 'run_id': str(run_id),
            'api': 'ghcr.io/vanx-mass/payment-api@sha256:' + str(run_id) * 64,
            'gateway': 'ghcr.io/vanx-mass/payment-api-gateway@sha256:' + str(run_id) * 64}


@pytest.fixture
def local_deploy(tmp_path, monkeypatch):
    monkeypatch.setattr(staging, 'STATE', tmp_path)
    (tmp_path / 'runtime.env').write_text('# ambiente de teste')
    monkeypatch.setattr(sys, 'argv', ['staging.py', 'deploy', '2'])
    monkeypatch.setattr(staging, 'approved_release', lambda _: release(2))
    monkeypatch.setattr(staging, 'verify_images', Mock())
    monkeypatch.setattr(staging, 'deployment_event', Mock(return_value=123))
    monkeypatch.setattr(staging, 'compose', Mock())
    monkeypatch.setattr(staging, 'command', Mock(return_value=''))
    return tmp_path


def test_imagem_sem_assinatura_valida_nao_altera_staging(local_deploy, monkeypatch):
    staging.verify_images.side_effect = RuntimeError('assinatura invalida')
    apply = Mock()
    monkeypatch.setattr(staging, 'apply', apply)
    with pytest.raises(RuntimeError, match='assinatura invalida'):
        staging.main()
    apply.assert_not_called()
    staging.deployment_event.assert_not_called()
    assert not (local_deploy / 'current.json').exists()


def test_falha_de_saude_restaura_versao_anterior_e_mantem_deploy_reprovado(local_deploy, monkeypatch):
    old = release(1)
    (local_deploy / 'current.json').write_text(json.dumps(old))
    attempts = []

    def apply(data, **kwargs):
        attempts.append(data['run_id'])
        if data['run_id'] == '2':
            raise subprocess.CalledProcessError(1, ['docker', 'compose', 'up'])

    monkeypatch.setattr(staging, 'apply', apply)
    with pytest.raises(subprocess.CalledProcessError):
        staging.main()
    assert attempts == ['2', '1']
    staging.verify_images.assert_called_once()
    assert json.loads((local_deploy / 'current.json').read_text()) == old
    evidence = json.loads((local_deploy / 'deployments.jsonl').read_text())
    assert evidence['action'] == 'rollback-automatico'
    assert evidence['run_id'] == '1'


def test_primeiro_deploy_reprovado_preserva_banco_e_nao_registra_sucesso(local_deploy, monkeypatch):
    monkeypatch.setattr(staging, 'apply', Mock(side_effect=subprocess.CalledProcessError(1, ['docker'])))
    with pytest.raises(subprocess.CalledProcessError):
        staging.main()
    arguments = staging.compose.call_args.args
    assert arguments[1:] == ('stop', 'api', 'gateway')
    assert not (local_deploy / 'current.json').exists()
    assert not (local_deploy / 'deployments.jsonl').exists()


@pytest.mark.parametrize('error', [
    subprocess.TimeoutExpired(['gh'], 30),
    FileNotFoundError('gh indisponivel'),
])
def test_falha_do_registro_remoto_nao_interrompe_recuperacao_local(
    local_deploy, error
):
    staging.command.side_effect = error
    # Usa a funcao real; a fixture substitui somente a chamada externa.
    result = deployment_event_real(release(1), 'failure', 123)
    assert result == 123
