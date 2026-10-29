from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from app.database import criar_tabelas
from app.routes import router
from app.rate_limiter import rate_limit_middleware
from app.logging_config import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await criar_tabelas()
    print("✅ Tabelas criadas")
    yield
    print("✅ API encerrada")

app = FastAPI(
    title="Payment API",
    description="API de pagamentos com autenticação JWT, cache Redis e rate limiting",
    version="1.0.0",
    lifespan=lifespan
)

app.middleware("http")(rate_limit_middleware)


@app.middleware("http")
async def adicionar_cabecalhos_seguranca(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(router)
