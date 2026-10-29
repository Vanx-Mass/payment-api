# Dia 3 — verificacao local antes do PR

Revisao concluida em 29/10/2026 na branch `codex/dia3-seguranca-entrega`.

## Resultado observado

- 63 testes aprovados no Windows/Python 3.12 e na imagem Docker/Linux/Python 3.11.
- Cobertura de app: 86,54%, acima do minimo de 80%.
- Bandit aprovado pela politica de severidade/confianca medias ou altas.
- Auditoria das dependencias propostas e das dependencias realmente instaladas
  nas imagens da API e do gateway: sem avisos conhecidos na consulta desta data.
- Gitleaks: historico aprovado e arquivos candidatos ao commit aprovados.
  As excecoes historicas limitam-se a dois exemplos SEU_TOKEN do README.
  Os exemplos atuais usam variaveis de shell em vez de tokens literais.
- Workflows conferidos com actionlint 1.7.12; actions fixadas por commit.
- API, gateway, PostgreSQL e Redis saudaveis no projeto Compose payment-api.
- Logs da inicializacao atual sem traceback e sem respostas HTTP 500.
- Pagamento ficticio aprovado e repeticao com a mesma chave sem duplicacao.
- DAST ativo autenticado aprovado nas tres consultas protegidas: zero alertas
  de risco baixo, medio ou alto; dois registros informativos.

Relatorio DAST local: `reports/dast/payment-dast-615e075997/zap.html`.
Resumo e logs: `summary.json`, `auth-proof.json`, `zap.log` e `docker.log`
na mesma pasta. Relatorios ficam fora do Git.

## Correcoes realizadas na revisao

- Hook ZAP usa `core.access_url`, valida a lista de mensagens e exige HTTP 200.
- IDs de pagamento fora do intervalo do Integer do PostgreSQL retornam HTTP 422
  antes da consulta; o caso reproduzido antes da correcao gerava HTTP 500.
- Respostas incluem nosniff, Cross-Origin-Resource-Policy same-origin e
  Cache-Control no-store, corrigindo os avisos de cabecalhos do scanner.
- DAST preserva logs, resumo e evidencia de autenticacao; a stack descartavel
  e encerrada sem interferir no volume do ambiente local.
- Timeout/falha no registro remoto de deploy nao interrompe a recuperacao local.
- Recuperacao automatica usa os digests previamente aprovados no cache local;
  nao depende de uma nova consulta ao registry para restaurar a versao anterior.
- Testes de regressao cobrem as correcoes de ZAP, validacao de IDs e recuperacao.

## Proximos passos do roteiro

A publicacao no GHCR, assinatura OIDC e deploy de staging dependem das etapas
seguintes ao PR e ainda nao foram executados nesta revisao.

O environment staging deve exigir revisor, aceitar somente main e aplicar a
protecao tambem a administradores. O laboratorio individual permite que o
proprio usuario aprove sua execucao.

Entrega assinada reexecuta o CI, aguarda aprovacao, publica/audita as imagens,
gera SBOM, assina os digests e disponibiliza release-staging. A publicacao usa
`deployment: false`; o deploy real e iniciado localmente por scripts/staging.py.

Staging usa porta 8001, projeto Compose e banco separados. Credenciais e estado
ficam em .staging/, excluido do Git e da imagem. O rollback preserva os dados;
mudancas de esquema precisam de uma estrategia propria de migracao.
