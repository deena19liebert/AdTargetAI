# app/db/session.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from app.db.base import Base

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var not set. e.g. postgresql+asyncpg://user:pwd@localhost:5432/dbname")

# async engine using asyncpg
engine = create_async_engine(DATABASE_URL, future=True, echo=False)

# async session maker
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

# Dependency for FastAPI: use get_async_session in endpoints with Depends(...)
async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session
