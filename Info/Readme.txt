📄 General Information : RZR Bot v6.0

RZR Bot нь Discord сервер дээр тоглогчдыг онооны системээр бүртгэж, багуудыг тэнцвэртэйгээр хуваарилдаг, тоглолтын түүхийг автоматаар хадгалдаг олон үйлдэлт бот юм.



🎯 Гол зорилго:

Session бүрийг системтэй удирдах

Тэнцвэртэй баг үүсгэх (оноо, tier дээр үндэслэн)

Tier болон онооны систем ашиглан тоглогчийн түвшин ахиулах

Match лог, undo, донат зэрэг нэмэлт боломжууд ашиглан тоглоомын менежментийг автоматжуулах

Render, GitHub, OpenAI, UptimeRobot зэрэг платформтой бүрэн интеграц хийсэн байдлаар ажиллах



🧠 Core Features:

🎮 Session management: /make_team → /set_match_result — хүртэл session хадгалах

🙋 Player registration: /addme — тоглогчид session эхэлсний дараа өөрийгөө бүртгүүлнэ

🧮 Tier system: Win/Loss оноо нэмэх → +5 дээр Tier ахих, -5 дээр буурах

🤝 Team assignment: make_team_go, gpt_go — баг бүрдүүлэлт

🔄 Undo match: /undo_last_match - сүүлд хийсэн оноог буцаах

📈 Auto GitHub sync: JSON файлуудыг 60 мин тутам commit хийх

🛡 Donator system: Emoji, Shield, Special perks

⏲ Timeout: Session автоматаар 24 цагийн дараа эсвэл дахин make_team хийх үед хаагдаж шинээр үүснэ

🧾 Match log: /match_history сүүлийн тоглолтуудыг харуулна



Platforms :

🛠 Work on: Discord

☁️ Server: Render

🔁 Server checker: UptimeRobot

💻 Code: GitHub

🤖 Supporter: OpenAI



🔐 TOKENS (Environment Variables) :

| Token Name       | Purpose                                             |
| ---------------- | --------------------------------------------------- |
| `DISCORD_TOKEN`  | Bot-г ажиллуулах Discord API token                  |
| `OPENAI_API_KEY` | GPT ашиглаж тэнцвэртэй баг үүсгэхэд ашиглана        |
| `GITHUB_TOKEN`   | JSON файлуудыг GitHub руу автоматаар commit хийхэд  |
| `GITHUB_REPO`    | GitHub repo-ийн нэр (e.g. `chipmo-team/RZR_bot_v6`) |



📦 Storage (Persistent JSON Files):
| File Name           | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| `scores.json`       | Тоглогчдын оноо, tier хадгалдаг                             |
| `score_log.jsonl`   | Онооны өөрчлөлтийн log бичдэг                               |
| `match_log.json`    | Match бүрийн дэлгэрэнгүй бүртгэл                            |
| `donators.json`     | Хандив өгөгчдийн мэдээлэл                                   |
| `player_stats.json` | Тоглогч бүрийн ялалт, ялагдал, тоглолтын статистик хадгална |

