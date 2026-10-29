# 💳 Payment API

> API de pagamentos com autenticação JWT, idempotência, cache Redis, rate limiting e gateway HTTP simulado.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-latest-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Redis](https://img.shields.io/badge/Redis-7-red)
![Docker](https://img.shields.io/badge/Docker-ready-blue)

---

## 📌 Sobre

API REST de pagamentos construída com FastAPI, PostgreSQL e Redis para aplicar
conceitos de CI/CD, segurança, observabilidade e orquestração. A base inclui
idempotência, retry com backoff exponencial, timeout no gateway e rate limiting.

---

## ✅ Funcionalidades

- [x] Registro e login com JWT
- [x] Criação de pagamentos com idempotência obrigatória
- [x] Histórico de pagamentos com cache Redis
- [x] Consulta de saldo com cache Redis
- [x] Retry com backoff exponencial no processador de pagamento
- [x] Timeout em chamadas externas
- [x] Rate limiting por IP e por usuário
- [x] Invalidação de cache após criação de pagamento
- [x] Dockerizado com Docker Compose
- [x] Gateway HTTP separado com quatro modos de falha/sucesso
- [x] Testes automatizados de API, idempotência, retry e integração HTTP

---

## 🛠️ Tecnologias

- **Python 3.11**
- **FastAPI** — framework web
- **PostgreSQL** — persistência dos dados financeiros
- **Redis** — cache, idempotência e rate limiting
- **SQLAlchemy** — ORM assíncrono
- **Docker + Docker Compose** — containerização
- **Gateway FastAPI** — processador simulado em serviço separado

---

## 🏗️ Decisões Técnicas

**PostgreSQL** — dados financeiros exigem consistência. Usuários e pagamentos precisam existir para sempre com garantia ACID.

**Redis com três responsabilidades distintas:**
- Cache do histórico e saldo (TTL 30-60s) — evita queries repetidas ao banco
- Idempotency keys (TTL 24h) — evita cobrança dupla em retentativas
- Rate limiting (janela de 60s) — protege contra força bruta e abuso

**Idempotência obrigatória no POST /pagamentos** — o cliente é forçado a enviar um `Idempotency-Key` único por operação. Requisições repetidas com a mesma chave retornam o resultado original sem reprocessar.

**Retry com backoff exponencial** — até quatro tentativas para falhas temporárias, com jitter e limite global de 30 segundos. Timeout retorna `504`, indisponibilidade retorna `503` e falha permanente do gateway retorna `502`.

---

## ▶️ Como Rodar Localmente

O gateway em `app/gateway/` é um serviço FastAPI independente. A API o chama
por HTTP usando `PROCESSOR_BASE_URL`, encaminhando a mesma chave de idempotência
em todas as tentativas. O Compose inicia API, PostgreSQL, Redis e gateway.

`GATEWAY_MODE` aceita `success`, `fail_once`, `always_fail` e `timeout`.
O estado do simulador é mantido em memória e reiniciado junto com o contêiner.

### Pré-requisitos
- Docker e Docker Compose instalados

### Passo a passo

```bash
# 1. Clone o repositório
git clone https://github.com/Vanx-Mass/payment-api.git
cd payment-api

# 2. Crie o .env baseado no exemplo
cp .env.example .env

# 3. Suba tudo
docker compose up -d --build --wait

# 4. Acesse a documentação
http://localhost:8000/docs
```

---

## 🔑 Variáveis de Ambiente

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | URL de conexão com o PostgreSQL |
| `REDIS_URL` | URL de conexão com o Redis |
| `SECRET_KEY` | Chave secreta para assinar os tokens JWT |

`PROCESSOR_BASE_URL` aponta para `http://gateway:8080` na rede do Compose.
`GATEWAY_MODE` define o cenário do simulador, com padrão `success`.

Gere uma `SECRET_KEY` segura:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## 📡 Endpoints

### Autenticação
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/auth/registro` | Cria nova conta |
| POST | `/auth/login` | Retorna token JWT |

### Pagamentos — requer token
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/pagamentos` | Cria pagamento (idempotência obrigatória) |
| GET | `/pagamentos` | Histórico do usuário (cache) |
| GET | `/pagamentos/{id}` | Detalhe de um pagamento (cache) |
| GET | `/saldo` | Saldo e estatísticas (cache) |

### Rate Limiting
| Endpoint | Limite |
|----------|--------|
| `POST /auth/login` | 10 req/min por IP |
| Demais endpoints | 60 req/min por usuário + 100 req/min por IP |

---

## 🔒 Idempotência

A chave é isolada por usuário. Repetir a chave com outros dados retorna `409`;
uma chamada simultânea com a mesma chave também retorna `409` enquanto a primeira
estiver em processamento. Se o Redis estiver indisponível, a API retorna `503`
antes de iniciar o processamento.

O pagamento e seu registro em `idempotencias_pagamento` são salvos na mesma
transação. Esse registro permite recuperar o resultado mesmo após a perda do
cache ou uma falha ao salvar a resposta no Redis. A nova tabela é criada na
inicialização pela rotina `criar_tabelas`, sem alterar colunas das tabelas atuais.
O cache dura 24 horas; o registro no banco permanece sem expiração automática.

O gateway recebe e respeita uma chave de idempotência estável durante sua
execução. Como o simulador mantém os resultados em memória, essa proteção no
gateway não sobrevive ao reinício do contêiner. Um processador real precisaria
persistir esse registro para cobrir quedas entre a aprovação externa e a
gravação no banco da API.

O endpoint `POST /pagamentos` exige o header `Idempotency-Key`:

```bash
# Primeira requisição — processa e salva
curl -X POST http://localhost:8000/pagamentos \
  -H "Authorization: Bearer ${TOKEN_USUARIO_1}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pedido-unico-001" \
  -d '{"valor": 100.00, "descricao": "Pedido #1"}'

# Mesma chave — retorna resultado anterior sem reprocessar
curl -X POST http://localhost:8000/pagamentos \
  -H "Authorization: Bearer ${TOKEN_USUARIO_2}" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pedido-unico-001" \
  -d '{"valor": 100.00, "descricao": "Pedido #1"}'
```

---

## 🐳 Docker

O `.dockerignore` exclui `.env`, metadados do Git e ambientes virtuais da imagem.

```bash
# Subir tudo (API + PostgreSQL + Redis + gateway)
docker compose up -d

# Ver logs
docker compose logs -f api

# Parar
docker compose down
```

---

## Dia 1 e próximos passos

Execute a verificação completa em PowerShell, na raiz do projeto:

```powershell
.\scripts\validar_dia1.ps1
```

O script executa os testes, verifica cobertura mínima de 80%, constrói a stack,
testa os quatro modos por HTTP real e restaura o gateway em `success`.
Cada cenário cria um usuário e uma chave fictícios exclusivos.

Consulte [TESTING.md](TESTING.md), [evidências do Dia 1](docs/dia1-validacao.md)
e o [roteiro do projeto](docs/plano-projeto.md).
