# 📒 RZR Bot — Коммандууд (товч гарын авлага)

Бүх команд **Slash (`/`)** хэлбэртэй.

---

## 🟢 Session ба бүртгэл
- `/ping` — Bot-ийн latency-г шалгана.  
- `/start_match` — Шинэ session эхлүүлнэ *(admin эсвэл эхлүүлэгч)*.  
- `/addme` — Өөрийгөө session-д бүртгэнэ *(бүгд)*.  
- `/remove` — Өөрийгөө бүртгэлээс хасна *(бүгд)*.  
- `/remove_user <@user>` — Тоглогчийг бүртгэлээс админ хасна.  
- `/show_added_players` — Бүртгэгдсэн тоглогчдыг жагсаана *(бүгд)*.  
- `/set_match <team_number> <mentions>` — Админ гараар тоглогчдыг багт онооно.  
- `/clear_match` — Session болон багийн бүртгэлийг бүрэн цэвэрлэнэ *(admin)*.  

---

## ⚖️ Багийн хуваарилалт
- `/go_bot <team_count> <players_per_team>` — Snake / Greedy / Reflector алгоритмаар оноо+tier-д суурилан хамгийн бага зөрүүтэй багууд үүсгэнэ.  
- `/go_gpt <team_count> <players_per_team>` — GPT + локал сайжруулалтаар баг хуваарилна.  
- `/current_match` — Одоогийн багийн бүрэлдэхүүн болон нийт оноог харуулна.  
- `/change_player <from> <to>` — Тоглогчдыг баг дотор солих *(admin эсвэл эхлүүлэгч)*.  
- `/matchups [seed]` — Багуудыг санамсаргүйгээр хослуулж харуулна. Зөвхөн Team Leader-уудыг mention хийнэ. DotA-style: 💀 Scourge vs 🌿 Sentinel.  

---

## 🏆 Match-ийн үр дүн
- `/set_match_result <winners> <losers>` — Match бүртгэнэ, +1/−1 оноо өгнө, tier өөрчлөгдөнө.  
- `/set_match_result_fountain <winners> <losers>` — Fountain төрөл, +2/−2 оноо өгнө, tier өөрчлөгдөнө.  
- `/undo_last_match` — Сүүлийн match-ийн оноо болон tier өөрчлөлтийг буцаана.  
- `/match_history` — Сүүлийн 5 match-ийн товч мэдээллийг харуулна.  

---

## 📊 Оноо, Tier, статистик
- `/my_score` — Миний tier, score, weight.  
- `/user_score <@user>` — Сонгосон тоглогчийн tier, score, weight.  
- `/player_stats` — Миний win/loss статистик болон win rate.  
- `/leaderboard [limit]` — Топ тоглогчдын жагсаалт (tier, score, wins/losses, winrate).  
- `/set_tier <@user> <tier> [score]` — Админ хэрэглэгчийн tier болон score-г гараар тохируулна.  
- `/add_score <@mentions> [points]` — Оноо нэмэх/хасах *(admin)*.  

---

## 💖 Donator
- `/add_donator <@user> <mnt>` — Donator болгож мөнгө нэмнэ, nickname-д donor emoji орно.  
- `/donator_list` — Donator жагсаалт (Top 3 + бусад).  

---

## ℹ️ Тусламж ба онош
- `/help_info` — Танилцуулга (`Readme.md`).  
- `/help_commands` — Бүх командын жагсаалт (энэ файл).  
- `/diag` — DB, OpenAI болон Discord permissions оношилгоо.  

---

## 🛠 Бусад
- `/resync` — Slash командуудыг дахин sync хийнэ *(admin)*.  
- `/whois <@user>` — Хэрэглэгчийн ID, нэр, mention мэдээлэл.  
- `/debug_id` — Миний Discord ID-г харуулна.  
- `/kick <@user>` — Vote-kick санал өгнө (10 санал хүрвэл kick хийнэ).  
- `/kick_review [@user]` — Vote-kick саналын жагсаалтыг админ харах.  
