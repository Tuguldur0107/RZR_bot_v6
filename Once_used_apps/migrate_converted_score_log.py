import json, psycopg2

DATABASE_URL = "postgresql://postgres:imTvuBaFtWGKRyswpGAKVYZEgHzJnliV@switchback.proxy.rlwy.net:35783/railway"

def migrate_score_log():
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
    print(f"✅ {inserted} мөр score_log table-д амжилттай орлоо!")

if __name__ == "__main__":
    migrate_score_log()
