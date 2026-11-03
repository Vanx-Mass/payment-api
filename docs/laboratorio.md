# Do commit ao incidente

O laboratório roda no Docker Desktop e usa dados fictícios. O projeto Compose
`payment-lab` tem banco, Redis e livro do gateway próprios. A API fica na porta
8002, o Prometheus na 9090, o Grafana na 3000 e o Airflow na 8082. As portas
publicadas são locais. O laboratório tem credenciais descartáveis e acesso
local simplificado. Staging usa outro projeto Compose e a porta 8001.

## Subir e verificar

Use PowerShell na raiz do checkout, com as dependências do projeto no Python.

```powershell
$lab = @('-p','payment-lab','-f','docker-compose.yml','-f','deploy/compose.lab.yml','-f','deploy/compose.observability.yml','-f','deploy/compose.airflow.yml')
docker compose @lab up -d --build --wait --wait-timeout 180
python scripts/lab_incident.py
python scripts/lab_reconciliation.py
docker compose @lab ps
```

- Dashboard [Payment API · laboratório](http://127.0.0.1:3000/d/payment-lab).
- [Prometheus Alerts](http://127.0.0.1:9090/alerts).
- [Airflow](http://127.0.0.1:8082), DAG `payment_reconciliation`.
- [Swagger da API](http://127.0.0.1:8002/docs).

`docker compose @lab down` encerra os containers e preserva os volumes.
O CI usa um runner descartável e guarda os JSONs de validação como artefato.

## Como as peças se conectam

1. **GitHub Actions e CI.** Um evento como abrir um PR inicia o workflow.
   O workflow tem jobs. Cada job tem steps. Um step pode rodar um comando
   ou reutilizar uma action. A matrix repete os testes em Python 3.11 e 3.12.
   Cache, workflows reutilizáveis e a composite action reduzem repetição.
   O check `CI obrigatorio` reúne testes, segurança, imagens e laboratório.
2. **Segurança.** Bandit analisa o código Python parado (SAST), pip-audit
   compara dependências com avisos conhecidos (SCA), Gitleaks procura segredos
   no histórico e ZAP faz chamadas a uma API rodando com autenticação (DAST).
3. **Entrega e deploy.** O workflow manual publica imagens no GHCR após
   passar pelo ambiente `staging`. SBOM inventaria componentes. Cosign usa
   a identidade temporária OIDC do GitHub para assinar os digests. O script
   de staging verifica as assinaturas, testa o candidato num ambiente
   descartável (porta 8003) e só então promove para 8001. Se a saúde ou o
   teste funcional falhar após a troca, o script tenta restaurar a versão
   anterior. Esse modelo de promoção usa duas stacks e troca a stack ativa
   inteira. O laboratório não divide tráfego por porcentagem.
4. **Métricas.** Prometheus lê `/metrics/` a cada cinco segundos. PromQL
   calcula volume, 5xx e p95. Grafana apresenta as séries e permite filtrar
   por serviço. As rotas usam modelos como `/pagamentos/{pagamento_id}`.
   IDs e URLs brutas não viram labels. Um contador separado mede pagamentos
   efetivamente gravados.
5. **Traces e logs.** A API propaga `traceparent` na chamada HTTPX. O gateway
   continua o trace. OpenTelemetry Collector envia os spans para Tempo e os
   logs JSON para Loki. O histograma guarda exemplars com o `trace_id`.
   No painel de latência, um exemplar abre o trace. O trace leva aos logs
   do mesmo pedido. O ID está no exemplar e no log estruturado.
6. **Airflow.** A DAG roda em lote a cada dia UTC. O sensor aguarda as fontes,
   a extração lê PostgreSQL e o livro persistente do gateway, e a conciliação
   compara chaves e valores e grava um relatório atômico por janela.
   XCom guarda caminhos e metadados pequenos. Retry repete tarefas com falha
   transitória. Uma janela inválida falha sem retry. Uma janela passada
   pode ser reprocessada pelo Airflow. A mesma janela substitui o mesmo
   relatório. Cada tarefa de extração e comparação inicia seu próprio span.
   Prefect modelaria as mesmas etapas como um flow e tasks. Aqui o scheduler,
   sensor e backfill são do Airflow.
7. **Capstone.** `lab_incident.py` muda somente o gateway do laboratório para
   `always_fail`, confirma HTTP 503, espera o alerta e procura as duas pontas
   da chamada em Tempo e Loki. Restaura o gateway mesmo se o teste falhar
   e verifica um novo pagamento. O script de conciliação usa o pagamento
   recuperado como dado de teste.

## Interpretar a conciliação

A janela usa início inclusivo e fim exclusivo. Use dias UTC completos para
execução normal. O relatório identifica chaves ausentes em cada origem e
valores divergentes. As chaves correspondem ao identificador interno usado
na comunicação API–gateway. A conciliação se aplica aos pagamentos gravados
com idempotência na stack do laboratório. A API e o gateway registram
horários independentes. Uma operação atravessando a fronteira da janela
pode ser apontada para investigação no relatório.

Para uma execução manual, use **Trigger** no Airflow e informe os dois
horários no JSON de configuração, por exemplo:

```json
{"start":"2026-11-03T00:00:00Z","end":"2026-11-04T00:00:00Z"}
```

Para múltiplas datas, use o backfill da interface na DAG diária. Aplique o
intervalo das datas passadas e escolha a política de reprocessamento. As
tarefas recebem a janela daquela execução pelo intervalo de dados.

## Postmortem do exercício

- **Causa injetada:** gateway retorna 503 em todas as tentativas.
- **Impacto esperado:** novos pagamentos falham após retries. A chamada
  sem resposta de aprovação não grava um pagamento aprovado no PostgreSQL.
- **Detecção:** `PagamentoComFalhas` e crescimento dos 5xx. O exemplar aponta
  para os spans de cada tentativa e os logs mostram os 503 correlacionados.
- **Recuperação:** restaurar o gateway saudável, confirmar novo 201 e conciliar
  a janela que contém o pagamento. O artefato registra o resultado observado.
- **Deploy:** promoção e rollback são exercícios separados. O fluxo local
  pode demonstrar falha de saúde no staging. O deploy na AWS exigiria conta,
  ambiente e permissões próprios. O OIDC aplicado aqui é para assinatura.

## Referências

- [Documentação de DAGs do Airflow](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/dags.html)
- [Exemplars no Grafana](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/)
- [Logs OpenTelemetry no Loki](https://grafana.com/docs/loki/latest/send-data/otel/)
