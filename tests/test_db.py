# tests/test_db.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv
import os
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT 1"))
        print("DB test ->", r.scalar())

    await engine.dispose()

asyncio.run(main())
