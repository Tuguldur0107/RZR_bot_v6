# database.py
import asyncpg
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import json


DB_URL = os.getenv("DATABASE_URL")

now = datetime.now(timezone.utc)

async def connect():
    return await asyncpg.connect(DB_URL)

# database.py файлд дараах функцуудыг нэм:

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

pool = None

async def init_pool():
    global pool
    if pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        pool = await asyncpg.create_pool(DATABASE_URL)

async def connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return await asyncpg.connect(DATABASE_URL)

async def ensure_pool() -> bool:
    try:
        await init_pool()
        return pool is not None
    except Exception as e:
        print(f"⚠️ ensure_pool error: {e}")
        return False
    
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

async def connect():
    # fallback single connection
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return await asyncpg.connect(DATABASE_URL)

# ── Score result logger (win/loss) ────────────────────────────────────────────
async def log_score_result(uid: int, result: str):
    """
    score_log(uid BIGINT, result TEXT CHECK (result IN ('win','loss')), timestamp TIMESTAMPTZ)
    """
    SQL = """
        INSERT INTO score_log (uid, result, timestamp)
        VALUES ($1, $2, NOW() AT TIME ZONE 'UTC')
    """
    try:
        if await ensure_pool():
            async with pool.acquire() as conn:
                await conn.execute(SQL, uid, result)
        else:
            conn = await connect()
            try:
                await conn.execute(SQL, uid, result)
            finally:
                await conn.close()
    except Exception as e:
        print(f"❌ log_score_result алдаа: {uid}, {result} {e}")

async def log_score_audit(uid: int, delta: int, total: int, tier: str, reason: str):
    """
    score_audit(timestamp TIMESTAMPTZ, uid BIGINT, delta INT, total INT, tier TEXT, reason TEXT)
    """
    SQL = """
        INSERT INTO score_audit (timestamp, uid, delta, total, tier, reason)
        VALUES (NOW() AT TIME ZONE 'UTC', $1, $2, $3, $4, $5)
    """
    conn = None
    try:
        if await ensure_pool():
            async with pool.acquire() as c:
                await c.execute(SQL, uid, delta, total, tier, reason)
        else:
            conn = await connect()
            await conn.execute(SQL, uid, delta, total, tier, reason)
    except Exception as e:
        print(f"⚠️ score_audit insert failed — uid={uid}: {e}")
    finally:
        if conn:
            await conn.close()
            
# 🧾 Онооны өөрчлөлт бүрийг score_log руу хадгалах
async def log_score_transaction(uid: int, delta: int, total: int, tier: str, reason: str):
    try:
        conn = await connect()
        await conn.execute("""
            INSERT INTO score_log (timestamp, uid, delta, total, tier, reason)
            VALUES (NOW() AT TIME ZONE 'UTC', $1, $2, $3, $4, $5)
        """, uid, delta, total, tier, reason)
    except Exception as e:
        print(f"⚠️ score_log insert failed — uid={uid}: {e}")
    finally:
        if conn:
            await conn.close()


# 🏆 Match бүртгэх
async def insert_match(
    initiator_id,
    team_count,
    players_per_team,
    winners,
    losers,
    mode,
    strategy,
    notes=""
):
    conn = await connect()
    now = datetime.now(timezone.utc)  # ✅ энд дотор нь оруул
    await conn.execute("""
        INSERT INTO matches (
            timestamp, initiator_id, team_count, players_per_team,
            winners, losers, mode, strategy, notes
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """,
        now,
        initiator_id,
        team_count,
        players_per_team,
        json.dumps(winners or []),
        json.dumps(losers or []),
        mode,
        strategy,
        notes
    )
    await conn.close()



# 🧠 Сүүлийн match хадгалах
async def save_last_match(winner_details, loser_details):
    conn = await connect()
    await conn.execute("""
        INSERT INTO last_match (timestamp, winners, losers, winner_details, loser_details)
        VALUES ($1, $2, $3, $4, $5)
    """,
        datetime.now(timezone.utc),  # ✅ timezone бүхий datetime
        json.dumps([p["uid"] for p in winner_details]),
        json.dumps([p["uid"] for p in loser_details]),
        json.dumps(winner_details or []),
        json.dumps(loser_details or [])
    )
    await conn.close()
    print("✅ Winner Details:", winner_details)


async def get_last_match():
    conn = await connect()
    row = await conn.fetchrow("SELECT * FROM last_match ORDER BY timestamp DESC LIMIT 1")
    await conn.close()
    if row:
        return {
            "timestamp": row["timestamp"],
            "winners": row["winners"],
            "losers": row["losers"],
            "winner_details": row["winner_details"],
            "loser_details": row["loser_details"],
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
    rows = await conn.fetch("SELECT uid, total_mnt, last_donated FROM donators ORDER BY pk ASC")
    await conn.close()
    # ❌ print log байх ёсгүй!
    return {
        str(row["uid"]): {
            "uid": row["uid"],
            "total_mnt": row["total_mnt"],
            "last_donated": row["last_donated"]
        }
        for row in rows
    }

# async def upsert_donator(uid: int, mnt: int):
#     conn = await connect()
#     await conn.execute("""
#         INSERT INTO donators (uid, total_mnt, last_donated)
#         VALUES ($1, $2, NOW())
#         ON CONFLICT (uid) DO UPDATE
#         SET total_mnt = donators.total_mnt + $2, last_donated = NOW()
#     """, uid, mnt)
#     await conn.close()


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
    #print("🧠 save_session_state дуудаж байна:", data)

    if not data.get("player_ids") and not allow_empty:
        #print("⚠️ player_ids байхгүй тул хадгалахгүй.")
        raise ValueError("⚠️ Session-д player_ids байхгүй тул хадгалахгүй.")

    # 🕒 datetime string бол datetime болгоно
    start_time = data.get("start_time")
    last_win_time = data.get("last_win_time")

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(last_win_time, str):
        last_win_time = datetime.fromisoformat(last_win_time)

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
        start_time,
        last_win_time,
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
    #print("✅ session_state хадгалагдлаа.")

async def load_session_state():
    try:
        conn = await connect()
        row = await conn.fetchrow("SELECT * FROM session_state ORDER BY timestamp DESC LIMIT 1")
        await conn.close()

        if not row:
            #print("ℹ️ session_state хоосон байна.")
            return None

        session = {
            "active": row["active"],
            "start_time": row["start_time"].isoformat() if row["start_time"] else None,
            "last_win_time": row["last_win_time"].isoformat() if row["last_win_time"] else None,
            "initiator_id": row["initiator_id"],
            "team_count": row["team_count"],
            "players_per_team": row["players_per_team"],
            "player_ids": json.loads(row["player_ids"] or "[]"),
            "teams": json.loads(row["teams"] or "[]"),
            "changed_players": json.loads(row["changed_players"] or "[]"),
            "strategy": row["strategy"],
        }
        return session

    except Exception as e:
        #print("❌ load_session_state алдаа:", e)
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


# database.py (жишээ — өөрийн хүснэгт/талбарын нэртэй тааруул)
def get_current_teams(session_id: int):
    """
    Идэвхтэй session-ийн багуудыг авчирна.
    Хариу формат:
    [
      {"team_no": 1, "members": ["NickA", "NickB", ...]},
      {"team_no": 2, "members": ["NickC", "NickD", ...]},
      ...
    ]
    """
    with pool.connection() as conn, conn.cursor() as cur:
        # Доорх SQL-ийг өөрийн schema-д нийцүүлж тохируул:
        # Та playermap / match_players / teams гэх мэт хүснэгттэй бол түүнд тааруулж GROUP BY хийнэ.
        cur.execute(
            """
            SELECT team_no,
                   array_agg(player_nick ORDER BY player_nick) AS members
            FROM match_players
            WHERE session_id = %s
            GROUP BY team_no
            ORDER BY team_no;
            """,
            (session_id,)
        )
        rows = cur.fetchall()
        return [{"team_no": r[0], "members": list(r[1] or [])} for r in rows]


