# 💳 Payment API

> API de pagamentos com autenticação JWT, idempotência, cache Redis, rate limiting e deploy no Render.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-latest-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue)
![Redis](https://img.shields.io/badge/Redis-7-red)
![Docker](https://img.shields.io/badge/Docker-ready-blue)
![Deploy](https://img.shields.io/badge/deploy-render-purple)

---

## 📌 Sobre

API REST de pagamentos construída com FastAPI, PostgreSQL e Redis. O projeto aplica padrões usados em APIs financeiras de produção: idempotência para evitar cobranças duplicadas, retry com backoff exponencial para chamadas externas, timeout em todas as operações e rate limiting para proteção contra abuso.

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
- [x] Deploy público no Render

---

## 🛠️ Tecnologias

- **Python 3.11**
- **FastAPI** — framework web
- **PostgreSQL** — persistência dos dados financeiros
- **Redis** — cache, idempotência e rate limiting
- **SQLAlchemy** — ORM assíncrono
- **Docker + Docker Compose** — containerização
- **Render** — deploy

---

## 🏗️ Decisões Técnicas

**PostgreSQL** — dados financeiros exigem consistência. Usuários e pagamentos precisam existir para sempre com garantia ACID.

**Redis com três responsabilidades distintas:**
- Cache do histórico e saldo (TTL 30-60s) — evita queries repetidas ao banco
- Idempotency keys (TTL 24h) — evita cobrança dupla em retentativas
- Rate limiting (janela de 60s) — protege contra força bruta e abuso

**Idempotência obrigatória no POST /pagamentos** — o cliente é forçado a enviar um `Idempotency-Key` único por operação. Requisições repetidas com a mesma chave retornam o resultado original sem reprocessar.

**Retry com backoff exponencial** — chamadas ao processador de pagamento são retentadas até 4 vezes com espera crescente (1s → 2s → 4s → 8s) e jitter para evitar thundering herd.

---

## ▶️ Como Rodar Localmente

### Pré-requisitos
- Docker e Docker Compose instalados

### Passo a passo

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/payment-api.git
cd payment-api

# 2. Crie o .env baseado no exemplo
cp .env.example .env

# 3. Suba tudo
docker-compose up -d

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

O endpoint `POST /pagamentos` exige o header `Idempotency-Key`:

```bash
# Primeira requisição — processa e salva
curl -X POST http://localhost:8000/pagamentos \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pedido-unico-001" \
  -d '{"valor": 100.00, "descricao": "Pedido #1"}'

# Mesma chave — retorna resultado anterior sem reprocessar
curl -X POST http://localhost:8000/pagamentos \
  -H "Authorization: Bearer SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: pedido-unico-001" \
  -d '{"valor": 100.00, "descricao": "Pedido #1"}'
```

---

## 🐳 Docker

```bash
# Subir tudo (API + PostgreSQL + Redis)
docker-compose up -d

# Ver logs
docker-compose logs -f api

# Parar
docker-compose down
```

---

## 🌐 URL Pública

API disponível em: **https://payment-api.onrender.com**

Documentação interativa: **https://payment-api.onrender.com/docs**