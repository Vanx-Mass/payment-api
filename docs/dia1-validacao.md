# Evidências do Dia 1

Validação realizada em 27/10/2026, no projeto local `payment-api`.

## Testes automatizados

Comando executado pelo script `scripts/validar_dia1.ps1`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=80
```

- Resultado: 44 testes aprovados, sem falhas.
- Cobertura total da aplicação: 86,26%, com mínimo exigido de 80%.
- O próprio código de testes fica fora da medição de cobertura.
- Testes locais executados no Python 3.12.10.
- Banco SQLite em memória e Redis simulado nos testes isolados.
- Integração HTTP em memória com o gateway e simulação explícita de timeout de rede.

## Stack real

- Build das imagens da API e do gateway concluído com base Python 3.11.
- API, PostgreSQL 15, Redis 7 e gateway iniciados pelo Compose do projeto.
- Quatro serviços em estado `healthy` ao final.
- API disponível em `http://localhost:8000/docs`.
- Arquivo `/app/.env` ausente da imagem da API, conforme `.dockerignore`.

## Cenários por HTTP real

Executados por `scripts/validar_pagamento.py`, com um usuário e uma chave
fictícios exclusivos em cada cenário:

- `success`: HTTP 201; repetir a chave devolveu o mesmo pagamento.
- `fail_once`: HTTP 201 após retry; repetir a chave devolveu o mesmo pagamento.
- `always_fail`: HTTP 503.
- `timeout`: HTTP 504, dentro do limite global da operação.

Nesta rodada, os dois cenários de sucesso produziram dois pagamentos e dois
registros de idempotência no PostgreSQL. As repetições não criaram novos pagamentos.
A consulta de contagem ao final retornou `2|2`.

## Estado final e reprodução

O gateway foi restaurado em `success`. Os quatro contêineres e o volume local
do PostgreSQL foram mantidos para continuar os próximos dias.

```powershell
.\scripts\validar_dia1.ps1
```

O script verifica código de saída de cada comando e restaura o modo saudável
mesmo quando uma validação falha após o início da stack. Os dados fictícios de
teste ficam no banco local; nenhuma infraestrutura externa de pagamentos é usada.

## Limite do simulador

O gateway mantém sua idempotência em memória: reiniciar seu contêiner limpa
esse estado. A API mantém os resultados concluídos no PostgreSQL. Uma integração
real exigiria persistência da idempotência também no processador externo para
cobrir interrupções entre aprovação externa e commit da API.

As funcionalidades dos Dias 2 a 7 estão descritas em `plano-projeto.md` e ainda
não fazem parte da entrega técnica do Dia 1.
