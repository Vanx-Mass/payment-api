# Roteiro do projeto — aplicação do Mês 8

Objetivo: aplicar à payment-api os conceitos do material
"Mês 8 - DevOps + CI_CD + Observabilidade", usando entregas verificáveis.
O Dia 1 prepara a aplicação; os próximos dias implementam a automação,
segurança, observabilidade e orquestração.

O roteiro anterior de cinco dias deixava Airflow/DAGs, DAST e a etapa de entrega
e deploy incompletos. Para incluir os conceitos pedidos, o roteiro passa a sete
etapas de trabalho. As etapas futuras abaixo são planejamento, não funcionalidades
já implementadas.

## Dia 1 — Base e gateway HTTP

- API com autenticação, cache, autorização, limite por usuário e saldo por status.
- Idempotência por usuário, reserva de chamadas simultâneas e registro no banco.
- Retry, timeout e gateway HTTP separado em quatro modos.
- Testes isolados e verificação real da stack com PostgreSQL e Redis.
- Documentação, evidências, commit e envio da branch de trabalho.

## Dia 2 — GitHub Actions e integração contínua

- Gatilhos `push`, `pull_request`, `workflow_dispatch` e `schedule`.
- Workflow reutilizável com `workflow_call` e composite action para passos comuns.
- Matrix Python 3.11/3.12, cache de dependências, pytest e cobertura mínima.
- Build das imagens da API e do gateway, artefatos de testes e permissões mínimas.
- Proteção da branch principal e comparação entre runners hospedados e próprios.
- Critério: um PR quebrado falha e fica impedido de seguir para entrega.

## Dia 3 — Segurança e entrega/deploy

- SAST com Bandit; dependency scanning/SCA com pip-audit; secrets scanning com Gitleaks.
- Verificação agendada de dependências, pois novos avisos surgem sem novo commit.
- DAST com ZAP contra uma stack descartável da própria API, incluindo autenticação.
- Relatórios de segurança, SBOM e assinatura/verificação da imagem.
- Publicação das imagens no GHCR; environments e secrets para staging/produção.
- Deploy de staging, checagem de saúde, gate de aprovação e caminho de rollback.
- O destino de deploy e as credenciais serão configurados nessa etapa; publicar
  uma imagem, sozinho, não comprova que o deploy aconteceu.
- Critério: falhas bloqueiam promoção e existe evidência de entrega e deploy.

## Dia 4 — Prometheus e Grafana

- `/metrics`, taxa de requisições, 5xx, latência e métricas de pagamentos/gateway.
- PromQL e dashboard provisionado, com filtros e alertas testados.
- Labels com cardinalidade controlada, sem IDs de usuário ou pagamento.
- Critério: tráfego e falhas aparecem nos painéis e acionam o alerta esperado.

## Dia 5 — OpenTelemetry e correlação

- Instrumentação de API e HTTPX; propagação de contexto até o gateway.
- Collector e backend de traces, como Tempo; logs JSON com `trace_id`/`span_id`.
- Loki e integração no Grafana entre métrica, trace e log.
- Exemplars para ligação com traces, sem usar `trace_id` como label da métrica.
- Critério: partir de um erro no gráfico e chegar à chamada e ao log correspondentes.

## Dia 6 — Airflow e DAG de conciliação/relatório

- Subir Airflow como serviço separado, com uma DAG de processo em lote.
- Etapas: verificar disponibilidade dos dados, extrair pagamentos de uma janela,
  comparar com registros do gateway e produzir o relatório da execução.
- Implementar a origem dos registros do gateway e dados de teste necessários;
  essa interface de conciliação ainda não existe no Dia 1.
- Aplicar tarefas, dependências, sensor, XCom para metadados pequenos, retries,
  timeout, execução por data e reexecução/backfill sem duplicação de resultados.
- Versionar e validar a DAG no CI, com trace iniciando na tarefa do orquestrador.
- Comparar o modelo com Prefect, também estudado, sem exigir dois orquestradores
  simultâneos para realizar o mesmo processo.
- Critério: executar uma janela, provocar falha, reexecutar e demonstrar o resultado
  consistente no relatório e na observabilidade.

## Dia 7 — Capstone, rollback e evidências

- Incidente provocado, geração de tráfego, alerta, trace e logs correlacionados.
- Demonstração de deploy progressivo em laboratório e rollback por falha de saúde.
- Postmortem, diagrama, comandos reproduzíveis e evidências no README.
- AWS CLI e autenticação temporária por OIDC entram no deploy se houver conta e
  ambiente de laboratório disponíveis; sem eles, registrar essa parte como pendente,
  sem apresentar a simulação local como deploy na AWS.
- Critério: apresentar o caminho do commit ao deploy, e da falha à recuperação.

## Papel de cada ferramenta

GitHub Actions coordena teste, análise, build, publicação e deploy do software.
Airflow executa a DAG de um processo de dados recorrente do projeto.
Prometheus coleta métricas; Grafana consulta e visualiza os dados e avalia alertas.
OpenTelemetry instrumenta e propaga a telemetria para os backends configurados.
SAST analisa código; SCA examina dependências; DAST verifica a aplicação rodando.

## Referências

- [Airflow e workflows](https://airflow.apache.org/docs/apache-airflow/stable/index.html)
- [DAGs no Airflow](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)
- [OpenTelemetry](https://opentelemetry.io/docs/what-is-opentelemetry/)
- [ZAP API scan](https://www.zaproxy.org/docs/docker/api-scan/)
- [Publicação de imagens no GitHub Actions](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
- [Environments de deploy no GitHub](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments)
