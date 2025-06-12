# database.py
import asyncpg
import os

DB_URL = os.getenv("DATABASE_URL")

async def connect():
    return await asyncpg.connect(DB_URL)

# database.py файлд дараах функцуудыг нэм:

async def get_all_scores():
    conn = await connect()
    rows = await conn.fetch("SELECT * FROM scores")
    await conn.close()
    return {str(row["uid"]): dict(row) for row in rows}

async def get_score(uid: int):
    conn = await connect()
    row = await conn.fetchrow("SELECT * FROM scores WHERE uid = $1", uid)
    await conn.close()
    return dict(row) if row else None

async def upsert_score(uid: int, score: int, tier: str, username: str):
    conn = await connect()
    await conn.execute("""
        INSERT INTO scores (uid, score, tier, username, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (uid) DO UPDATE
        SET score = $2, tier = $3, username = $4, updated_at = NOW()
    """, uid, score, tier, username)
    await conn.close()
