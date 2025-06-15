📄 General Information : RZR Bot v6.1 (SQL хувилбар)

RZR Bot нь Discord сервер дээр тоглогчдыг оноо болон tier-р бүртгэж, багийн хуваарилалт хийж, match-ийн лог хөтөлдөг олон үйлдэлт бот юм. v6.1 хувилбар нь PostgreSQL дата баазаар бүрэн ажилладаг.

🎯 Гол зорилго:

* Session бүрийг системтэй удирдах (PostgreSQL дээр хадгалах)
* Оноо, tier дээр үндэслэн тэнцвэртэй баг үүсгэх
* +5/-5 зарчмаар tier ахиулах, бууруулах
* Match бүртгэл, undo, донат, статистик зэргийг SQL дээр бүртгэж, тоглоомын менежментийг автоматжуулах
* Railway, GitHub, OpenAI, UptimeRobot зэрэг платформтой интеграцчлагдсан

🧠 Гол боломжууд:

🎮 Session Management: `/start_match` → `/set_match_result` (SQL дээр хадгална)

🙋 Player Registration: `/addme`, `/remove`, `/show_added_players`

⚖️ Tier System: Win/Loss оноо нэмэх → +5 дээр Tier ахина, -5 дээр буурна (Tier: 1-1 → 5-5)

🤖 Team Assignment:

* `/go_bot` — Snake/Greedy аргаар автоматаар хуваарилна
* `/go_gpt` — GPT API ашиглан онооны дагуу баг хуваарилна

📅 Manual Assignment: `/set_match` — Гараар баг оноох

🕛 Timeout: Session автоматаар 24 цагийн дараа хаагдана (эсвэл дахин `/start_match` хийвэл)

🔄 Undo Match: `/undo_last_match` — Match-ийн үр дүнг буцаана

📊 Statistics:

* `/my_score`, `/user_score` — Tier, оноо
* `/player_stats`, `/player_stats_users` — Win/Loss, winrate
* `/leaderboard` — Топ 10 жагсаалт

🛡 Donator System:

* `/add_donator`, `/donator_list` — Emoji, Shield, Nickname update

📦 GitHub Backup:

* Автомат: 60 мин тутам `data/*.json` commit хийдэг
* Гар аргаар: `/backup_now`

📜 Match Log: `/match_history` — Сүүлийн тоглолтын бүртгэл

🌐 Ашиглаж буй платформууд:

🛠️ Discord Slash Commands

☁️ Railway (PostgreSQL + Volume хадгалалт)

🔁 UptimeRobot (Monitoring)

📀 GitHub (Код ба JSON нөөц)

🤖 OpenAI GPT-4o (Team assignment)