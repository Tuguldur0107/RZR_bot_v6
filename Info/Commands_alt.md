# 📒 RZR Bot — Коммандууд (товч гарын авлага)

Бүх команд **Slash (`/`)** хэлбэртэй.

---

## 🟢 Session ба бүртгэл
- `/start_match` — Шинэ session эхлүүлнэ *(admin эсвэл эхлүүлэгч)*  
- `/addme` — Өөрийгөө session-д бүртгэнэ *(бүгд)*  
- `/remove` — Өөрийгөө бүртгэлээс хасна *(бүгд)*  
- `/show_added_players` — Бүртгэгдсэн тоглогчдыг жагсаана *(бүгд)*  
- `/clear_match` — Session болон багийн бүртгэлийг цэвэрлэнэ *(admin)*

---

## ⚖️ Багийн хуваарилалт
- `/go_bot <team_count> <players_per_team>` — Snake / Greedy / Reflector алгоритмаар 
  хамгийн бага зөрүүтэй хувиарлалт хийнэ.  
- `/go_gpt <team_count> <players_per_team>` — GPT + локал сайжруулалтаар баг хуваарилна.  
- `/set_match <team_number> <mentions>` — Админ гараар баг үүсгэнэ.  
- `/current_match` — Одоогийн багийн бүрэлдэхүүн ба оноог харуулна.  
- `/change_player <from> <to>` — Тоглогч солих (admin эсвэл эхлүүлэгч).  

---

## 🏆 Match-ийн үр дүн
- `/set_match_result <winners> <losers>` — +1/−1 оноо, tier өөрчлөлттэй.  
- `/set_match_result_fountain` — Fountain төрөл (+2/−2).  
- `/undo_last_match` — Сүүлийн match-ийг буцаана.  
- `/match_history` — Сүүлийн 5 match-ийн товч мэдээлэл.  

---

## 📊 Оноо, Tier, статистик
- `/my_score` — Миний tier, score.  
- `/user_score <@user>` — Сонгосон хүний tier, score.  
- `/player_stats` — Миний win/loss статистик.  
- `/leaderboard` — Top 10 тоглогчийн жагсаалт.  
- `/set_tier <@user> <tier> [score]` — Админ гараар тохируулна.  
- `/add_score <@mentions> [points]` — Оноо нэмэх/хасах (admin).  

---

## 💖 Donator
- `/add_donator <@user> <mnt>` — Donator болгож мөнгө нэмнэ.  
- `/donator_list` — Donator жагсаалт (Top 3 + бусад).  

---

## ℹ️ Тусламж ба онош
- `/help_info` — Танилцуулга (`Readme.md`).  
- `/help_commands` — Энэ жагсаалт.  
- `/diag` — DB / OpenAI / permission онош.  
- `/diag_dryrun` — DRY-RUN (TEMP TABLE, mock balance).  

---

## 🛠 Бусад
- `/resync` — Slash командуудыг дахин sync (admin).  
- `/whois <@user>` — ID, нэр, mention.  
- `/debug_id` — Миний Discord ID.  
- `/ping` — Bot latency.  
