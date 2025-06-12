import json

with open("./data/score_log.jsonl", "r", encoding="utf-8") as f:
    match_logs = json.load(f)

converted = []

for entry in match_logs:
    ts = entry.get("timestamp")
    for uid in entry.get("winners", []):
        converted.append({
            "timestamp": ts,
            "uid": str(uid),
            "delta": 1,
            "total": 0,
            "tier": "?",
            "reason": "set_match_result"
        })
    for uid in entry.get("losers", []):
        converted.append({
            "timestamp": ts,
            "uid": str(uid),
            "delta": -1,
            "total": 0,
            "tier": "?",
            "reason": "set_match_result"
        })

with open("./data/score_log_converted.json", "w", encoding="utf-8") as f:
    json.dump(converted, f, indent=2, ensure_ascii=False)

print(f"✅ Хөрвүүлэлт амжилттай! {len(converted)} мөр score_log_converted.json-д бичигдлээ")
