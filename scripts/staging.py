"""Deploy local de releases aprovadas; nunca executa um runner no computador."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.staging'
REPO = 'Vanx-Mass/payment-api'
COSIGN = 'ghcr.io/sigstore/cosign/cosign:v3.1.4'


def command(*args, capture=False, data=None, timeout=300):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, check=True, text=True,
                            input=data, capture_output=capture, timeout=timeout)
    return result.stdout.strip() if capture else None


def gh_json(*args):
    return json.loads(command('gh', *args, capture=True))


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def validate_release(data):
    if data.get('repository', '').lower() != REPO.lower():
        raise RuntimeError('Repositorio inesperado no manifesto.')
    if not re.fullmatch(r'[0-9a-f]{40}', data.get('sha', '')):
        raise RuntimeError('Commit invalido no manifesto.')
    if not str(data.get('run_id', '')).isdigit():
        raise RuntimeError('Execucao invalida no manifesto.')
    for key, suffix in (('api', ''), ('gateway', '-gateway')):
        pattern = re.escape('ghcr.io/' + REPO.lower() + suffix) + r'@sha256:[0-9a-f]{64}'
        if not re.fullmatch(pattern, data.get(key, '')):
            raise RuntimeError(f'Referencia de imagem invalida: {key}')


def approved_release(run_id):
    info = gh_json('run', 'view', str(run_id), '-R', REPO, '--json',
                   'status,conclusion,headSha,headBranch,workflowName,event')
    if (info['status'], info['conclusion'], info['headBranch'], info['workflowName'], info['event']) != (
        'completed', 'success', 'main', 'Entrega assinada', 'workflow_dispatch'
    ):
        raise RuntimeError('Use uma execucao concluida e aprovada de Entrega assinada na main.')
    folder = STATE / 'releases' / (str(run_id) + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    command('gh', 'run', 'download', str(run_id), '-R', REPO, '-n', 'release-staging', '-D', folder)
    data = json.loads((folder / 'release.json').read_text(encoding='utf-8'))
    validate_release(data)
    if data['sha'] != info['headSha'] or str(data['run_id']) != str(run_id):
        raise RuntimeError('Manifesto nao corresponde a execucao selecionada.')
    return data


def verify_images(data):
    validate_release(data)
    identity = f'https://github.com/{REPO}/.github/workflows/release.yml@refs/heads/main'
    for image in (data['api'], data['gateway']):
        command('docker', 'run', '--rm', COSIGN, 'verify', '--certificate-identity', identity,
                '--certificate-oidc-issuer', 'https://token.actions.githubusercontent.com', image)
        command('docker', 'pull', image)


def compose(data, *args, simulate_failure=False):
    image_env = STATE / 'images.env'
    image_env.write_text(f'API_IMAGE={data["api"]}\nGATEWAY_IMAGE={data["gateway"]}\n', encoding='utf-8')
    invocation = ['docker', 'compose', '-p', 'payment-staging',
                  '--env-file', str(STATE / 'runtime.env'), '--env-file', str(image_env),
                  '-f', str(ROOT / 'deploy/compose.staging.yml')]
    if simulate_failure:
        invocation += ['-f', str(ROOT / 'deploy/compose.staging-failure.yml')]
    env = dict(os.environ)
    for name in ('API_IMAGE', 'GATEWAY_IMAGE', 'POSTGRES_PASSWORD', 'SECRET_KEY'):
        env.pop(name, None)
    subprocess.run(invocation + list(args), cwd=ROOT, env=env, check=True, timeout=300)


def apply(data, simulate_failure=False):
    compose(data, 'up', '-d', '--wait', '--wait-timeout', '120', '--force-recreate',
            simulate_failure=simulate_failure)
    # Exercita autenticacao, banco, Redis, gateway e idempotencia com dados ficticios.
    env = dict(os.environ, BASE_URL='http://127.0.0.1:8001')
    subprocess.run([str(ROOT / '.venv/Scripts/python.exe') if os.name == 'nt' else 'python',
                    str(ROOT / 'scripts/validar_pagamento.py'), '201'],
                   env=env, cwd=ROOT, check=True, timeout=90)
    with httpx.Client(timeout=10) as client:
        client.get('http://127.0.0.1:8001/openapi.json').raise_for_status()


def log(action, data):
    record = {'at': datetime.now(timezone.utc).isoformat(), 'action': action, **data}
    with (STATE / 'deployments.jsonl').open('a', encoding='utf-8') as file:
        file.write(json.dumps(record) + '\n')


def deployment_event(data, state, deployment_id=None):
    # Falha em registrar evidencia no GitHub nao desfaz uma recuperacao local.
    try:
        if deployment_id is None:
            body = {'ref': data['sha'], 'environment': 'staging', 'auto_merge': False,
                    'required_contexts': [], 'production_environment': False,
                    'description': 'Staging local no Docker Desktop'}
            response = json.loads(command('gh', 'api', '--method', 'POST',
                f'repos/{REPO}/deployments', '--input', '-', data=json.dumps(body), capture=True, timeout=30))
            deployment_id = response['id']
        body = {'state': state, 'environment_url': 'http://localhost:8001/docs',
                'log_url': f'https://github.com/{REPO}/actions/runs/{data["run_id"]}'}
        command('gh', 'api', '--method', 'POST',
                f'repos/{REPO}/deployments/{deployment_id}/statuses', '--input', '-',
                data=json.dumps(body), capture=True, timeout=30)
        return deployment_id
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, KeyError, ValueError):
        print('Aviso: evidencia remota indisponivel; consulte .staging/deployments.jsonl.')
        return deployment_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'deploy', 'rollback'])
    parser.add_argument('run_id', type=int, nargs='?')
    parser.add_argument('--simulate-health-failure', action='store_true')
    args = parser.parse_args()
    STATE.mkdir(exist_ok=True)
    if args.action == 'init':
        config = STATE / 'runtime.env'
        if config.exists():
            print('Configuracao existente preservada.')
            return
        config.write_text(f'POSTGRES_PASSWORD={secrets.token_hex(24)}\n'
                          f'SECRET_KEY={secrets.token_hex(32)}\n', encoding='utf-8')
        print('Credenciais locais criadas em .staging/runtime.env.')
        return
    if not (STATE / 'runtime.env').is_file():
        parser.error('Execute primeiro: python scripts/staging.py init')
    if args.simulate_health_failure and args.action != 'deploy':
        parser.error('A simulacao pertence somente ao comando deploy.')
    if args.action == 'deploy':
        if args.run_id is None:
            parser.error('Informe o ID da execucao de Entrega assinada.')
        candidate = approved_release(args.run_id)
    else:
        previous_file = STATE / 'previous.json'
        if not previous_file.is_file():
            parser.error('Ainda nao existe uma versao anterior para rollback.')
        candidate = approved_release(int(json.loads(previous_file.read_text())['run_id']))
    current_file = STATE / 'current.json'
    current = json.loads(current_file.read_text()) if current_file.exists() else None
    if args.simulate_health_failure and current is None:
        parser.error('Realize um deploy saudavel antes de simular a falha.')
    # As duas imagens sao verificadas antes de alterar os servicos locais.
    verify_images(candidate)
    deployment_id = deployment_event(candidate, 'in_progress')
    try:
        apply(candidate, simulate_failure=args.simulate_health_failure)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, httpx.HTTPError, OSError):
        deployment_event(candidate, 'failure', deployment_id)
        if current:
            print('Deploy falhou. Restaurando as imagens anteriores...')
            # Estes digests foram verificados antes de se tornarem a release atual.
            # O rollback usa o cache local, inclusive se o registry estiver indisponivel.
            validate_release(current)
            for image in (current['api'], current['gateway']):
                command('docker', 'image', 'inspect', image, capture=True)
            apply(current)
            deployment_event(current, 'success')
            log('rollback-automatico', current)
            print('Rollback concluido; o deploy solicitado continua reprovado.')
        else:
            compose(candidate, 'stop', 'api', 'gateway')
        raise
    if current and current != candidate:
        save(STATE / 'previous.json', current)
    save(current_file, candidate)
    deployment_event(candidate, 'success', deployment_id)
    log('deploy' if args.action == 'deploy' else 'rollback-manual', candidate)
    print('Staging saudavel: http://localhost:8001/docs')


if __name__ == '__main__':
    STATE.mkdir(exist_ok=True)
    lock = STATE / 'deploy.lock'
    try:
        descriptor = lock.open('x', encoding='utf-8')
    except FileExistsError:
        raise SystemExit('Existe outro comando de staging em andamento (.staging/deploy.lock).')
    try:
        with descriptor:
            descriptor.write(str(os.getpid()))
            descriptor.flush()
            main()
    finally:
        lock.unlink()
