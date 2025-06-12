# 📂 migrate_all_to_sql.py

import json, psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://postgres:imTvuBaFtWGKRyswpGAKVYZEgHzJnliV@switchback.proxy.rlwy.net:35783/railway"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def migrate_scores(cur):
    scores = load_json("./data/scores.json")
    for uid, d in scores.items():
        cur.execute("""
            INSERT INTO scores (uid, username, score, tier, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO UPDATE
            SET username = EXCLUDED.username,
                score = EXCLUDED.score,
                tier = EXCLUDED.tier,
                updated_at = EXCLUDED.updated_at;
        """, (int(uid), d.get("username", "unknown"), d.get("score", 0),
              d.get("tier", "4-1"), d.get("updated_at", datetime.utcnow().isoformat())))
    print("✅ scores.json → scores")

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

def migrate_converted_score_log():
    with open("./data/score_log_converted.json", "r", encoding="utf-8") as f:
        logs = json.load(f)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    inserted = 0

    for log in logs:
        if "uid" not in log or log["uid"] is None:
            continue
        cur.execute("""
            INSERT INTO score_log (timestamp, uid, delta, total, tier, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            log["timestamp"],
            int(log["uid"]),
            log["delta"],
            log["total"],
            log["tier"],
            log["reason"]
        ))
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ {inserted} мөр score_log table-д орлоо")

if __name__ == "__main__":
    migrate_converted_score_log()



def migrate_matches(cur):
    data = load_json("./data/match_log.json")
    for m in data:
        cur.execute("""
            INSERT INTO matches (
                timestamp, mode, initiator_id, team_count,
                players_per_team, strategy, teams
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            m.get("timestamp"), m.get("mode"), m.get("initiator", None),
            m.get("team_count", 2), m.get("players_per_team", 5),
            m.get("strategy", ""), json.dumps(m.get("teams", []))
        ))
    print(f"✅ match_log.json → matches ({len(data)} rows)")

def run_all():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    migrate_scores(cur)
    migrate_donators(cur)
    migrate_last_match(cur)
    migrate_player_stats(cur)
    migrate_session(cur)
    migrate_score_log(cur)
    migrate_matches(cur)
    conn.commit()
    cur.close()
    conn.close()
    print("🎉 Бүх JSON → SQL шилжүүлэлт амжилттай!")

if __name__ == "__main__":
    run_all()
