# 📘 RZR Bot v6.1 — Танилцуулга (SQL)

RZR Bot нь Discord дээр тоглогчдыг оноо ба tier-ээр удирдаж, тэнцвэртэй баг хуваарилдаг бөгөөд тоглолтын үр дүнг найдвартай хадгалж, хиймэл оюун ухаантай уялдан ажилладаг.

---

## 🚀 Гол боломжууд
- **Session**: `/start_match` → бүртгэл → баг хуваарилалт → үр дүн SQL дээр хадгалах (24 цагийн дараа хаагдана)  
- **Багийн тэнцвэржилт**  
  - `/go_bot` — snake / greedy / reflector алгоритм  
  - `/go_gpt` — GPT + локал сайжруулалт  
- **Оноо, Tier**: +5 → дэвшинэ, −5 → буурна; nickname дээр tier + донат + гүйцэтгэлийн эмоджи  
- **Match бүртгэл**: энгийн ба Fountain төрөл (+2/−2), undo боломжтой  
- **Donator**: донат нэмэх, жагсаалт гаргах  

---

## 🧩 Эхлэх алхам (5)
1. `/start_match` — шинэ session эхлүүл  
2. Тоглогчид `/addme` — бүртгүүл  
3. `/go_bot 2 5` эсвэл `/go_gpt 2 5` — баг хуваарил  
4. `/matchups` - аар аль баг хоорондоо тоглохоо үзээрэй
5. Тоглолтын дараа `/set_match_result` эсвэл `/set_match_result_fountain`  
6. `/leaderboard`, `/player_stats`, `/my_score` — шалга  

> **Ranked** тоглолт: баг ≥ 2, нэг баг 4 эсвэл 5 хүнтэй байх шаардлагатай.  

---

## 🧠 Жин тооцох
`weight = TIER_WEIGHT[tier] + score`  
Tier 1-1 хамгийн өндөр, 5-5 хамгийн бага.  

---

## 🔐 Админ хэрэгслүүд
- `/set_tier`, `/set_match`, `/clear_match`  
- `/add_donator`, `/donator_list`  
- `/resync`, `/diag`, `/diag_dryrun`  

---

## 🛠 Ашигласан технологи
- Discord Slash Commands  
- Railway  
- PostgreSQL  
- OpenAI GPT-5o mini