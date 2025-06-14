# database.py
import asyncpg
import os
from datetime import datetime
from dotenv import load_dotenv
import json

DB_URL = os.getenv("DATABASE_URL")

async def connect():
    return await asyncpg.connect(DB_URL)

# database.py файлд дараах функцуудыг нэм:

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

pool = None

async def init_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(DATABASE_URL)

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
    if not username:
        existing = await get_score(uid)
        username = existing.get("username", "Unknown") if existing else "Unknown"

    conn = await connect()
    await conn.execute("""
        INSERT INTO scores (uid, score, tier, username, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (uid) DO UPDATE
        SET score = $2, tier = $3, username = $4, updated_at = NOW()
    """, uid, score, tier, username)
    await conn.close()

from datetime import datetime

# 🧾 Онооны өөрчлөлт бүрийг score_log руу хадгалах
async def log_score_transaction(uid: int, delta: int, total: int, tier: str, reason: str):
    conn = await connect()
    await conn.execute("""
        INSERT INTO score_log (timestamp, uid, delta, total, tier, reason)
        VALUES (NOW(), $1, $2, $3, $4, $5)
    """, uid, delta, total, tier, reason)
    await conn.close()

# 🏆 Match бүртгэх
async def insert_match(mode: str, teams: list, winner_team: list, initiator_id: int):
    conn = await connect()
    await conn.execute("""
        INSERT INTO matches (timestamp, mode, teams, winner_team, initiator_id)
        VALUES (NOW(), $1, $2, $3, $4)
    """, mode, teams, winner_team, initiator_id)
    await conn.close()

# 🧠 Сүүлийн match хадгалах
async def save_last_match(winners, losers):
    conn = await connect()
    await conn.execute(
        "INSERT INTO last_match (timestamp, winners, losers) VALUES ($1, $2, $3)",
        datetime.now(), winners, losers
    )
    await conn.close()

async def get_last_match():
    conn = await connect()
    row = await conn.fetchrow("SELECT * FROM last_match ORDER BY timestamp DESC LIMIT 1")
    await conn.close()
    if row:
        return {
            "winners": row["winners"],
            "losers": row["losers"],
        }
    return None

async def clear_last_match():
    conn = await connect()
    await conn.execute("DELETE FROM last_match")
    await conn.close()

# 📊 Player stats
async def update_player_stats(uid: int, is_win: bool, undo: bool = False):
    conn = await connect()
    if is_win:
        field = "wins"
    else:
        field = "losses"

    increment = -1 if undo else 1

    await conn.execute(f"""
        INSERT INTO player_stats (uid, wins, losses)
        VALUES ($1, $2, $3)
        ON CONFLICT (uid) DO UPDATE
        SET {field} = GREATEST(0, player_stats.{field} + $4)
    """, uid, 1 if is_win else 0, 0 if is_win else 1, increment)
    await conn.close()

# 💖 Donator info
async def get_all_donators():
    conn = await connect()
    rows = await conn.fetch("SELECT * FROM donators")
    await conn.close()
    return {str(row["uid"]): dict(row) for row in rows}

async def upsert_donator(uid: int, mnt: int):
    conn = await connect()
    await conn.execute("""
        INSERT INTO donators (uid, total_mnt, last_donated)
        VALUES ($1, $2, NOW())
        ON CONFLICT (uid) DO UPDATE
        SET total_mnt = donators.total_mnt + $2, last_donated = NOW()
    """, uid, mnt)
    await conn.close()

# 🛡 Donate Shields
async def get_shields():
    conn = await connect()
    rows = await conn.fetch("SELECT * FROM shields")
    await conn.close()
    return {str(row["uid"]): row["shields"] for row in rows}

async def upsert_shield(uid: int, shields: int):
    conn = await connect()
    await conn.execute("""
        INSERT INTO shields (uid, shields)
        VALUES ($1, $2)
        ON CONFLICT (uid) DO UPDATE
        SET shields = $2
    """, uid, shields)
    await conn.close()

# 🧠 Session state
async def save_session_state(data: dict, allow_empty=False):
    print("🧠 save_session_state дуудаж байна:", data)

    if not data.get("player_ids") and not allow_empty:
        print("⚠️ player_ids байхгүй тул хадгалахгүй.")
        raise ValueError("⚠️ Session-д player_ids байхгүй тул хадгалахгүй.")

    conn = await connect()
    await conn.execute("""
        INSERT INTO session_state (
            active, start_time, last_win_time, initiator_id,
            team_count, players_per_team, player_ids,
            teams, changed_players, strategy, timestamp
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, $7,
            $8, $9, $10, $11
        )
    """,
        data.get("active", False),
        data.get("start_time"),
        data.get("last_win_time"),
        data.get("initiator_id"),
        data.get("team_count", 0),
        data.get("players_per_team", 0),
        json.dumps(data.get("player_ids", [])),
        json.dumps(data.get("teams", [])),
        json.dumps(data.get("changed_players", [])),
        data.get("strategy", "unknown"),
        datetime.now()
    )
    await conn.close()
    print("✅ session_state хадгалагдлаа.")

async def load_session_state():
    try:
        conn = await connect()
        row = await conn.fetchrow("SELECT data FROM session_state ORDER BY timestamp DESC LIMIT 1")
        await conn.close()
        if row and "data" in row:
            print("📥 session_state loaded:", row["data"])
            return row["data"]
        else:
            print("⚠️ session_state хоосон байна")
            return None
    except Exception as e:
        print("❌ load_session_state алдаа:", e)
        return None

async def clear_session_state():
    try:
        conn = await connect()
        await conn.execute("DELETE FROM session_state")
        await conn.close()
        print("🧼 session_state DB цэвэрлэгдлээ")
    except Exception as e:
        print("❌ clear_session_state алдаа:", e)

async def get_player_stats(uid_list: list[int]):
    if not uid_list:
        return []
    conn = await connect()
    rows = await conn.fetch(
        "SELECT uid, wins, losses FROM player_stats WHERE uid = ANY($1)",
        uid_list
    )
    await conn.close()
    return rows

async def get_player_stats(uid_list: list[int]):
    if not uid_list:
        return []
    conn = await connect()
    rows = await conn.fetch(
        "SELECT uid, wins, losses FROM player_stats WHERE uid = ANY($1)",
        uid_list
    )
    await conn.close()
    return rows

# 🧩 Tier system functions (async биш)
# 🧱 Tier config
TIER_ORDER = [
    "1-1", "1-2", "1-3", "1-4", "1-5",
    "2-1", "2-2", "2-3", "2-4", "2-5",
    "3-1", "3-2", "3-3", "3-4", "3-5",
    "4-1", "4-2", "4-3", "4-4", "4-5",
    "5-1", "5-2", "5-3", "5-4", "5-5"
]

# 🎯 Default tier
def get_default_tier():
    return {"score": 0, "tier": "4-1"}

# ⬆️ Tier ахиулах
def promote_tier(tier: str) -> str:
    idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else TIER_ORDER.index("4-1")
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]

# ⬇️ Tier бууруулах
def demote_tier(tier: str) -> str:
    idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else TIER_ORDER.index("4-1")
    return TIER_ORDER[max(idx - 1, 0)]