# database.py (RZR stable pool edition)
import os
import asyncio
import asyncpg
import json
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

pool: Optional[asyncpg.Pool] = None

# ──────────────────────────────────────────────────────────────────────────────
# ENV / DSN
# ──────────────────────────────────────────────────────────────────────────────
DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("DB_URL") or "").strip()

def _mask_dsn(dsn: str) -> str:
    try:
        if "://" in dsn and "@" in dsn:
            proto, rest = dsn.split("://", 1)
            userpass, host = rest.split("@", 1)
            user = userpass.split(":", 1)[0]
            return f"{proto}://{user}:****@{host}"
    except Exception:
        pass
    return dsn

def _with_ssl_require(dsn: str) -> str:
    if "sslmode=" in dsn:
        return dsn
    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}sslmode=require"

# ──────────────────────────────────────────────────────────────────────────────
# Pool (global)
# ──────────────────────────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()

POOL_MIN = 1
POOL_MAX = 5
TIMEOUT = 10
MAX_INACTIVE = 60

async def get_pool() -> asyncpg.Pool:
    """Stable accessor: pool объектын албан ёсны гарц."""
    await ensure_pool()
    assert _pool is not None
    return _pool

async def init_pool() -> None:
    """Create pool with fallback to sslmode=require."""
    global _pool
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    async with _pool_lock:
        if _pool and not _pool._closed:
            return

        last_exc = None
        for idx, dsn in enumerate((DATABASE_URL, _with_ssl_require(DATABASE_URL)), start=1):
            masked = _mask_dsn(dsn)
            print(f"[POOL INIT] attempt {idx}/2 DSN={masked}")
            try:
                _pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=POOL_MIN,
                    max_size=POOL_MAX,
                    timeout=TIMEOUT,
                    command_timeout=TIMEOUT,
                    max_inactive_connection_lifetime=MAX_INACTIVE,
                )
                # ⬇️ public alias-аа синкдэж өгнө
                globals()["pool"] = _pool
                print(f"[POOL READY] DSN={masked} min={POOL_MIN} max={POOL_MAX} timeout={TIMEOUT}s")
                return
            except Exception as e:
                last_exc = e
                print(f"[POOL INIT FAIL] DSN={masked} err={e!r}")

        raise RuntimeError(f"Failed to init pool: {last_exc!r}")

async def ensure_pool() -> None:
    global _pool, pool
    if _pool is None or _pool._closed:
        await init_pool()
    # alias үргэлж sync байг
    pool = _pool

# ──────────────────────────────────────────────────────────────────────────────
# Acquire wrapper + helpers (тайм-аут, логтой)
# ──────────────────────────────────────────────────────────────────────────────
async def _with_conn(tag: str, fn: Callable[[asyncpg.Connection], Awaitable[Any]]) -> Any:
    await ensure_pool()
    assert _pool is not None

    t0 = time.perf_counter()
    print(f"[ACQUIRE start] {tag}")
    async with _pool.acquire() as conn:
        print(f"[ACQUIRE ok] {tag} in={(time.perf_counter()-t0)*1000:.1f}ms")
        q0 = time.perf_counter()
        try:
            res = await asyncio.wait_for(fn(conn), timeout=TIMEOUT)
            print(f"[QUERY ok] {tag} in={(time.perf_counter()-q0)*1000:.1f}ms")
            return res
        except asyncio.TimeoutError:
            print(f"[QUERY timeout] {tag} after={(time.perf_counter()-q0)*1000:.1f}ms")
            raise
        except Exception as e:
            print(f"[QUERY error] {tag} err={e!r}")
            raise
    # async with гарантиягаар release болно
    print(f"[RELEASE ok] {tag}")

async def fetch(q: str, *args: Any, tag: str = "fetch"):
    return await _with_conn(tag, lambda c: c.fetch(q, *args))

async def fetchrow(q: str, *args: Any, tag: str = "fetchrow"):
    return await _with_conn(tag, lambda c: c.fetchrow(q, *args))

async def fetchval(q: str, *args: Any, tag: str = "fetchval"):
    return await _with_conn(tag, lambda c: c.fetchval(q, *args))

async def execute(q: str, *args: Any, tag: str = "execute"):
    return await _with_conn(tag, lambda c: c.execute(q, *args))

# ──────────────────────────────────────────────────────────────────────────────
# Public API (таны командуудад хэрэглэгддэг функцууд)
# ──────────────────────────────────────────────────────────────────────────────

# Scores
async def get_all_scores():
    rows = await fetch("SELECT * FROM scores", tag="scores.all")
    return {str(r["uid"]): dict(r) for r in rows}

async def get_score(uid: int):
    row = await fetchrow("SELECT * FROM scores WHERE uid = $1", uid, tag="scores.one")
    return dict(row) if row else None

async def upsert_score(uid: int, score: int, tier: str, username: str):
    if not username:
        existing = await get_score(uid)
        username = (existing or {}).get("username", "Unknown")
    await execute(
        """
        INSERT INTO scores (uid, score, tier, username, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (uid) DO UPDATE
        SET score=$2, tier=$3, username=$4, updated_at=NOW()
        """,
        uid, score, tier, username,
        tag="scores.upsert",
    )

# Score logs / audit
async def log_score_result(uid: int, result: str):
    try:
        await execute(
            "INSERT INTO score_log (uid, result, timestamp) VALUES ($1, $2, NOW() AT TIME ZONE 'UTC')",
            uid, result,
            tag="score_log.insert",
        )
    except Exception as e:
        print(f"❌ log_score_result: uid={uid} err={e!r}")

async def log_score_audit(uid: int, delta: int, total: int, tier: str, reason: str):
    try:
        await execute(
            """
            INSERT INTO score_audit (timestamp, uid, delta, total, tier, reason)
            VALUES (NOW() AT TIME ZONE 'UTC', $1, $2, $3, $4, $5)
            """,
            uid, delta, total, tier, reason,
            tag="score_audit.insert",
        )
    except Exception as e:
        print(f"⚠️ score_audit failed uid={uid}: {e!r}")

async def log_score_transaction(uid: int, delta: int, total: int, tier: str, reason: str):
    try:
        await execute(
            """
            INSERT INTO score_log (timestamp, uid, delta, total, tier, reason)
            VALUES (NOW() AT TIME ZONE 'UTC', $1, $2, $3, $4, $5)
            """,
            uid, delta, total, tier, reason,
            tag="score_log.tx",
        )
    except Exception as e:
        print(f"⚠️ score_log tx failed uid={uid}: {e!r}")

# Matches
async def insert_match(
    initiator_id: int,
    team_count: int,
    players_per_team: int,
    winners,
    losers,
    mode,
    strategy,
    notes: str = "",
):
    now = datetime.now(timezone.utc)
    await execute(
        """
        INSERT INTO matches (
            timestamp, initiator_id, team_count, players_per_team,
            winners, losers, mode, strategy, notes
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
        now, initiator_id, team_count, players_per_team,
        json.dumps(winners or []), json.dumps(losers or []),
        mode, strategy, notes,
        tag="matches.insert",
    )

# Last match
async def save_last_match(winner_details, loser_details):
    await execute(
        """
        INSERT INTO last_match (timestamp, winners, losers, winner_details, loser_details)
        VALUES ($1, $2, $3, $4, $5)
        """,
        datetime.now(timezone.utc),
        json.dumps([p["uid"] for p in (winner_details or [])]),
        json.dumps([p["uid"] for p in (loser_details or [])]),
        json.dumps(winner_details or []),
        json.dumps(loser_details or []),
        tag="last_match.insert",
    )

async def get_last_match():
    row = await fetchrow(
        "SELECT * FROM last_match ORDER BY timestamp DESC LIMIT 1",
        tag="last_match.one",
    )
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
    await execute("DELETE FROM last_match", tag="last_match.clear")

# Player stats
async def update_player_stats(uid: int, is_win: bool, undo: bool = False):
    field = "wins" if is_win else "losses"
    inc = -1 if undo else 1
    await execute(
        f"""
        INSERT INTO player_stats (uid, wins, losses)
        VALUES ($1, $2, $3)
        ON CONFLICT (uid) DO UPDATE
        SET {field} = GREATEST(0, player_stats.{field} + $4)
        """,
        uid, 1 if is_win else 0, 0 if is_win else 1, inc,
        tag="player_stats.upd",
    )

# Donators
async def get_all_donators():
    rows = await fetch(
        "SELECT uid, total_mnt, last_donated FROM donators ORDER BY pk ASC",
        tag="donators.all",
    )
    return {
        str(r["uid"]): {
            "uid": r["uid"],
            "total_mnt": r["total_mnt"],
            "last_donated": r["last_donated"],
        }
        for r in rows
    }

async def upsert_donator(uid: int, mnt: int):
    await execute(
        """
        INSERT INTO donators (uid, total_mnt, last_donated)
        VALUES ($1, $2, NOW())
        ON CONFLICT (uid) DO UPDATE
        SET total_mnt = donators.total_mnt + $2, last_donated = NOW()
        """,
        uid, mnt,
        tag="donators.upsert",
    )

# Shields
async def get_shields():
    rows = await fetch("SELECT * FROM shields", tag="shields.all")
    return {str(r["uid"]): r["shields"] for r in rows}

async def upsert_shield(uid: int, shields: int):
    await execute(
        """
        INSERT INTO shields (uid, shields)
        VALUES ($1, $2)
        ON CONFLICT (uid) DO UPDATE
        SET shields = $2
        """,
        uid, shields,
        tag="shields.upsert",
    )

# Session state
async def save_session_state(data: dict, allow_empty: bool = False):
    if not data.get("player_ids") and not allow_empty:
        raise ValueError("⚠️ Session-д player_ids байхгүй.")

    start_time = data.get("start_time")
    last_win_time = data.get("last_win_time")

    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(last_win_time, str):
        last_win_time = datetime.fromisoformat(last_win_time)

    await execute(
        """
        INSERT INTO session_state (
            active, start_time, last_win_time, initiator_id,
            team_count, players_per_team, player_ids,
            teams, changed_players, strategy, timestamp
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
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
        datetime.now(timezone.utc),
        tag="session.save",
    )

async def load_session_state():
    try:
        row = await fetchrow(
            "SELECT * FROM session_state ORDER BY timestamp DESC LIMIT 1",
            tag="session.load",
        )
        if not row:
            return None
        return {
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
    except Exception as e:
        print(f"❌ load_session_state: {e!r}")
        return None

async def clear_session_state():
    try:
        await execute("DELETE FROM session_state", tag="session.clear")
        print("🧼 session_state DB цэвэрлэгдлээ")
    except Exception as e:
        print(f"❌ clear_session_state: {e!r}")

async def get_player_stats(uid_list: list[int]):
    if not uid_list:
        return []
    rows = await fetch(
        "SELECT uid, wins, losses FROM player_stats WHERE uid = ANY($1)",
        uid_list,
        tag="player_stats.list",
    )
    return rows


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

