# 📄 General Information : RZR Bot v6.1 (SQL хувилбар)

RZR Bot нь Discord сервер дээр тоглогчдыг оноо болон түвшингээр бүртгэж, тэнцвэртэй баг хуваарилж, тоглолтын үр дүнг бүртгэдэг олон үйлдэлт bot юм. 6.1 хувилбарт PostgreSQL ашиглаж, JSON хадгалалтаас бүрэн салсан.

## 🎯 Гол зорилго:

* Session бүрийг системтэй удирдах (PostgreSQL дээр бүртгэнэ)
* Оноо болон tier дээр үндэслэн багийг хамгийн тэнцвэртэй хуваарилах
* Tier болон онооны system ашиглан тоглогчийн түвшинг динамикаар ахиулах / бууруулах
* Match бүртгэл, undo, донат, статистик зэрэг нэмэлт функцүүдээр автоматжуулсан менежмент хийх
* Railway, GitHub, OpenAI GPT зэрэг системүүдтэй бүрэн интеграцтай ажиллах

## 🧠 Гол боломжууд:

🎮 Session Management: `/start_match` → `/set_match_result` → SQL дээр хадгалагдана

🙋 Player Registration: `/addme`, `/remove`, `/show_added_players`

⚖️ Tier System: `+5` → tier ахина, `–5` → tier буурна (Tier: 1-1 → 5-5)

🤖 Team Assignment:

* `/go_bot` – Онооны дагуу автоматаар snake/greedy аргаар хуваарилна
* `/go_gpt` – GPT ашиглан илүү тэнцвэртэй хуваарилалт

📝 Manual Assignment: `/set_match` — гараар баг бүрдүүлж болно

⏳ Timeout Logic: Session 24 цаг өнгөрөх эсвэл `/start_match` дахин хийгдэх үед хаагдана

↩️ Undo Match: `/undo_last_match` – сүүлийн match-ийн оноог буцаах

📊 Statistics:

* `/player_stats`, `/player_stats_users` – Win/Loss
* `/my_score`, `/user_score` – Tier болон оноо
* `/leaderboard` – Нийт тоглогчдын жагсаалт

🛡 Donator System:

* `/add_donator`, `/donator_list` — Emoji, Shield, Nickname update

📦 GitHub Sync:

* Автоматаар 60 мин тутам `data/*.json` GitHub дээр commit хийнэ
* `/backup_now` коммандаар гараар commit хийх боломжтой

## 🌐 Ашиглаж буй платформууд:

🛠 Ажилладаг орчин: Discord Slash Commands

☁️ Сервер: Railway (PostgreSQL + Volume хадгалалт)

🔁 Хянагч: UptimeRobot

💾 Дата хадгалалт: PostgreSQL + JSON GitHub backup

💻 Код хадгалалт: GitHub

🤖 Интеграц: OpenAI GPT (GPT-3.5 / GPT-4o)
