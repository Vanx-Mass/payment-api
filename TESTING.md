# Testes locais

Execute na raiz do projeto, em PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing
```

Os testes usam SQLite em memória, Redis simulado e credenciais exclusivas de
teste. Não precisam de `.env`, Docker, PostgreSQL ou Redis de desenvolvimento.
Os arquivos ficam em `app/tests/`, descobertos pelo `pytest.ini`. A cobertura
exclui o próprio código de testes por meio de `.coveragerc`.

A suíte cobre consultas e cache, autorização, saldo por status, validação,
limite por usuário, idempotência e as regras de retry e timeout.
`test_gateway.py` integra a API e o gateway com transporte HTTP em memória,
validando `success`, `fail_once`, `always_fail` e `timeout`. Também verifica
timeout de rede, resposta inválida, erro permanente e reuso de chave no gateway.

## Validação completa com Docker

Com Docker Desktop em execução e `.env` configurado:

```powershell
.\scripts\validar_dia1.ps1
```

O script executa pytest com cobertura mínima de 80%, constrói e inicia os quatro
serviços, testa os cenários por HTTP real e restaura o gateway em `success`.
Os serviços e o volume local do PostgreSQL ficam disponíveis após a execução.
Os dados criados por essa validação são fictícios e permanecem no banco local.
O script restringe o destino dos testes a `http://localhost:8000`.

Para repetir apenas os cenários Docker, sem repetir pytest nem o build:

```powershell
.\scripts\validar_dia1.ps1 -SkipTests -SkipBuild
```

Para uma checagem individual do modo atualmente ativo:

```powershell
.\.venv\Scripts\python.exe .\scripts\validar_pagamento.py 201
```

Troque o argumento por `503` em `always_fail` ou `504` em `timeout`.
Cada execução usa uma chave nova. Nos modos de sucesso, a mesma requisição é
repetida e deve devolver exatamente o mesmo pagamento.
