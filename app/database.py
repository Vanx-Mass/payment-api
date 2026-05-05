# app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pydantic_settings import BaseSettings
import logging

logger = logging.getLogger(__name__)

class Database:
    def connect(self):
        logger.info("Conectando ao banco...")

class Settings(BaseSettings):
    database_url: str
    model_config = {"env_file": ".env", "extra": "ignore"}



settings = Settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,          
    max_overflow=20,       
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def criar_tabelas():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)