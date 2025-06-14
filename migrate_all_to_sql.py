# 📂 migrate_all_to_sql.py

import json, psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://postgres:imTvuBaFtWGKRyswpGAKVYZEgHzJnliV@switchback.proxy.rlwy.net:35783/railway"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def migrate_scores(cur):
    VALID_TIERS = [
        "4-3", "4-2", "4-1",
        "3-3", "3-2", "3-1",
        "2-3", "2-2", "2-1",
        "1-3", "1-2", "1-1"
    ]

    def valid_tier(t):
        return t if t in VALID_TIERS else "4-1"

    scores = load_json("./data/scores.json")
    for uid, d in scores.items():
        username = d.get("username", "unknown")
        score = d.get("score", 0)
        tier = valid_tier(d.get("tier"))
        updated_at = d.get("updated_at", datetime.utcnow().isoformat())

        cur.execute("""
            INSERT INTO scores (uid, username, score, tier, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO UPDATE
            SET username = EXCLUDED.username,
                score = EXCLUDED.score,
                tier = EXCLUDED.tier,
                updated_at = EXCLUDED.updated_at;
        """, (int(uid), username, score, tier, updated_at))

    print("✅ scores.json → scores (tier шалгаж орсон)")

def migrate_donators(cur):
    data = load_json("./data/donators.json")
    for uid, d in data.items():
        last = d.get("last_donated")
        last_dt = datetime.fromisoformat(last) if last else None
        cur.execute("""
            INSERT INTO donators (uid, total_mnt, last_donated)
            VALUES (%s, %s, %s)
            ON CONFLICT (uid) DO UPDATE
            SET total_mnt = EXCLUDED.total_mnt,
                last_donated = EXCLUDED.last_donated;
        """, (int(uid), d.get("total_mnt", 0), last_dt))
    print("✅ donators.json → donators")

def migrate_last_match(cur):
    data = load_json("./data/last_match.json")
    cur.execute("DELETE FROM last_match;")  # 1ш л хадгалах учраас always replace
    cur.execute("""
        INSERT INTO last_match (winners, losers)
        VALUES (%s, %s);
    """, (json.dumps(data.get("winners", [])), json.dumps(data.get("losers", []))))
    print("✅ last_match.json → last_match")

def migrate_player_stats(cur):
    data = load_json("./data/player_stats.json")
    for uid, d in data.items():
        cur.execute("""
            INSERT INTO player_stats (uid, wins, losses)
            VALUES (%s, %s, %s)
            ON CONFLICT (uid) DO UPDATE
            SET wins = EXCLUDED.wins,
                losses = EXCLUDED.losses;
        """, (int(uid), d.get("wins", 0), d.get("losses", 0)))
    print("✅ player_stats.json → player_stats")

def migrate_session(cur):
    data = load_json("./data/session.json")
    cur.execute("DELETE FROM session_state;")
    cur.execute("""
        INSERT INTO session_state (
            active, start_time, last_win_time, initiator_id,
            team_count, players_per_team, player_ids, teams, strategy
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        data.get("active", False),
        data.get("start_time"), data.get("last_win_time"), data.get("initiator_id"),
        data.get("team_count", 2), data.get("players_per_team", 5),
        json.dumps(data.get("player_ids", [])), json.dumps(data.get("teams", [])),
        data.get("strategy", "")
    ))
    print("✅ session.json → session_state")



import json, psycopg2

DATABASE_URL = "postgresql://postgres:imTvuBaFtWGKRyswpGAKVYZEgHzJnliV@switchback.proxy.rlwy.net:35783/railway"

def run_all():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    migrate_scores(cur)
    migrate_donators(cur)
    migrate_last_match(cur)
    migrate_player_stats(cur)
    migrate_session(cur)
    conn.commit()
    cur.close()
    conn.close()
    print("🎉 Бүх JSON → SQL шилжүүлэлт амжилттай!")

if __name__ == "__main__":
    run_all()
