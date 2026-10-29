"""DAST ativo, limitado a consultas autenticadas de uma stack descartavel."""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
ZAP_IMAGE = 'ghcr.io/zaproxy/zaproxy:stable'


def main():
    project = 'payment-dast-' + uuid.uuid4().hex[:10]
    report = ROOT / 'reports' / 'dast' / project
    report.mkdir(parents=True)
    report.chmod(0o777)
    shutil.copyfile(ROOT / 'security/zap_hooks.py', report / 'zap_hooks.py')
    env = dict(os.environ, DAST_DB_PASSWORD=secrets.token_hex(24),
               DAST_SECRET_KEY=secrets.token_hex(32))
    compose = ['docker', 'compose', '-p', project, '-f', str(ROOT / 'deploy/compose.dast.yml')]
    try:
        subprocess.run(compose + ['up', '-d', '--build', '--wait', '--wait-timeout', '180'],
                       cwd=ROOT, env=env, check=True, timeout=900)
        with httpx.Client(base_url='http://127.0.0.1:18080', timeout=45) as client:
            registration = client.post('/auth/registro', json={
                'nome': 'Usuario DAST', 'email': f'{project}@example.com',
                'senha': secrets.token_urlsafe(24),
            })
            registration.raise_for_status()
            token = registration.json()['token']
            headers = {'Authorization': f'Bearer {token}', 'Idempotency-Key': project}
            payment = client.post('/pagamentos', headers=headers,
                                  json={'valor': 10, 'descricao': 'Pagamento ficticio DAST'})
            payment.raise_for_status()
            if client.get('/saldo').status_code not in (401, 403):
                raise RuntimeError('Uma consulta protegida aceitou acesso sem token.')
            for endpoint in ('/saldo', '/pagamentos'):
                client.get(endpoint, headers=headers).raise_for_status()
            spec_response = client.get('/openapi.json')
            spec_response.raise_for_status()
            spec = spec_response.json()
            spec['servers'] = [{'url': 'http://api:8000'}]
            spec['paths'] = {
                path: {'get': item['get']} for path, item in spec['paths'].items()
                if path in ('/saldo', '/pagamentos', '/pagamentos/{pagamento_id}')
            }
            if len(spec['paths']) != 3:
                raise RuntimeError('Escopo OpenAPI inesperado.')
            for parameter in spec['paths']['/pagamentos/{pagamento_id}']['get'].get('parameters', []):
                if parameter['name'] == 'pagamento_id':
                    parameter['example'] = payment.json()['id']
            (report / 'openapi.json').write_text(json.dumps(spec), encoding='utf-8')
        scan_env = dict(env, ZAP_AUTH_HEADER_VALUE=f'Bearer {token}',
                        ZAP_AUTH_HEADER='Authorization', ZAP_AUTH_HEADER_SITE='api')
        command = [
            'docker', 'run', '--rm', '--network', project + '_default',
            '--mount', f'type=bind,source={report},target=/zap/wrk',
            '-e', 'ZAP_AUTH_HEADER_VALUE', '-e', 'ZAP_AUTH_HEADER', '-e', 'ZAP_AUTH_HEADER_SITE',
            ZAP_IMAGE, 'zap-api-scan.py', '-t', '/zap/wrk/openapi.json', '-f', 'openapi',
            '--hook', '/zap/wrk/zap_hooks.py', '-J', 'zap.json', '-r', 'zap.html',
            '-T', '10', '-z', '-config ascan.maxRuleDurationInMins=2 -config ascan.maxScanDurationInMins=10',
        ]
        print(f'ZAP em execucao. Log: {report / "zap.log"}', flush=True)
        with (report / 'zap.log').open('w', encoding='utf-8') as output:
            result = subprocess.run(command, env=scan_env, cwd=ROOT, timeout=1200,
                                    stdout=output, stderr=subprocess.STDOUT)
        if result.returncode not in (0, 1, 2):
            raise RuntimeError(f'Falha operacional do ZAP: {result.returncode}; consulte {report / "zap.log"}')
        if not (report / 'auth-proof.json').is_file():
            raise RuntimeError('Sem evidencia de consulta autenticada feita pelo ZAP.')
        data = json.loads((report / 'zap.json').read_text(encoding='utf-8-sig'))
        sites = data.get('site', [])
        if not sites:
            raise RuntimeError('O ZAP nao registrou nenhum alvo.')
        alerts = [alert for site in sites for alert in site.get('alerts', [])]
        blocked = [a for a in alerts if int(a.get('riskcode', -1)) >= 2]
        unknown = [a for a in alerts if str(a.get('riskcode')) not in ('0', '1', '2', '3')]
        if unknown:
            raise RuntimeError('Relatorio ZAP com classificacao desconhecida.')
        (report / 'summary.json').write_text(json.dumps({
            'authenticated_request_status': 200,
            'scoped_paths': list(spec['paths']),
            'alerts_by_risk': {str(risk): sum(str(a.get('riskcode')) == str(risk) for a in alerts)
                               for risk in range(4)},
            'passed': not blocked,
        }, indent=2), encoding='utf-8')
        print(f'Relatorio: {report / "zap.html"}')
        for alert in alerts:
            print(f'Risco {alert["riskcode"]}: {alert.get("name", alert.get("alert"))}')
        if blocked:
            raise RuntimeError(f'DAST bloqueou {len(blocked)} alerta(s) de risco medio/alto.')
        print('DAST aprovado: autenticacao comprovada; nenhum alerta medio/alto.')
    finally:
        try:
            with (report / 'docker.log').open('w', encoding='utf-8') as output:
                subprocess.run(compose + ['logs', '--no-color', '--tail', '200'], cwd=ROOT,
                               env=env, stdout=output, stderr=subprocess.STDOUT, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            print('Nao foi possivel coletar os logs dos servicos descartaveis.', flush=True)
        # Este nome foi criado acima para esta execucao; nunca e o projeto do Dia 1.
        cleanup = subprocess.run(compose + ['down', '--volumes', '--remove-orphans'],
                                 cwd=ROOT, env=env, timeout=120)
        if cleanup.returncode:
            raise RuntimeError(f'Falha ao encerrar o laboratorio descartavel {project}.')


if __name__ == '__main__':
    main()
