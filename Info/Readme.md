# 📘 RZR Bot v6.1 — Танилцуулга (SQL хувилбар)

RZR Bot нь Discord сервер дээр тоглогчдыг оноо + tier‑ээр удирдаж, **тэнцвэртэй баг** хуваарилж, тоглолтын үр дүнг **PostgreSQL** дээр бүртгэдэг бот юм. v6.1‑д JSON‑оос бүрэн салж, SQL руу шилжсэн.:contentReference[oaicite:0]{index=0}

---

## 🚀 Юу хийдэг вэ?

- **Session удирдлага**: `/start_match` → тоглогчид бүртгүүлэх → баг хуваарилах → үр дүнг SQL дээр хадгална. 24 цаг өнгөрөхөд автоматаар хаагдана.:contentReference[oaicite:1]{index=1}:contentReference[oaicite:2]{index=2}
- **Багийн тэнцвэржилт**:
  - `/go_bot` — snake / greedy / reflector алгоритмаар жин тэнцүүлнэ.:contentReference[oaicite:3]{index=3}
  - `/go_gpt` — GPT‑ийн санал + локал сайжруулалт (swap refine) ашиглаж илүү ойр онооны баг үүсгэнэ.:contentReference[oaicite:4]{index=4}
- **Оноо, Tier**: +5 хүрвэл дэвшинэ, −5 хүрвэл буурна; nickname‑д tier + донат + сүүлийн гүйцэтгэлийн эмоджи харагдана.:contentReference[oaicite:5]{index=5}
- **Match бүртгэл**: энгийн ба Fountain (+2/−2) үр дүнг log‑лож, хүсвэл undo хийж буцаана.:contentReference[oaicite:6]{index=6}
- **Donator**: донат нэмэх, жагсаалт гаргах (Top 3 + бусад).:contentReference[oaicite:7]{index=7}

---

## 🧩 Хэрхэн эхлэх вэ? (5 алхам)

1. `/start_match` — шинэ session эхлүүл.:contentReference[oaicite:8]{index=8}
2. Тоглогчид `/addme` — өөрсдийгөө бүртгүүлнэ.:contentReference[oaicite:9]{index=9}
3. `/go_bot 2 5` эсвэл `/go_gpt 2 5` — 2 баг, баг бүр 5 хүнтэй хуваарил.:contentReference[oaicite:10]{index=10}
4. Тоглолтын дараа `/set_match_result "1" "2"` — 1‑р баг ялж 2‑р баг ялагдсан бол бүртгэ. Fountain төрөл бол `/set_match_result_fountain`.:contentReference[oaicite:11]{index=11}
5. `/leaderboard`, `/player_stats`, `/my_score` — шалгана.:contentReference[oaicite:12]{index=12}

> Жишээ: **Ranked** тоглолт байхын тулд баг ≥ 2, нэг багийн хүн 4 эсвэл 5 байх шаардлагатай.:contentReference[oaicite:13]{index=13}

---

## 🧠 Жин тооцох логик

Тоглогч бүрт `weight = TIER_WEIGHT[tier] + score`. Tier‑ийн жин код дээр тогтоосон (1‑1 хамгийн өндөр, 5‑5 хамгийн бага).:contentReference[oaicite:14]{index=14}

---

## 🔐 Админд зориулсан хэрэгслүүд

- `/set_tier` — тоглогчийн tier/оноог гар аргаар тохируулна.:contentReference[oaicite:15]{index=15}
- `/set_match` — гараар баг үүсгэнэ.:contentReference[oaicite:16]{index=16}
- `/clear_match` — идэвхтэй session‑г цэвэрлэнэ.:contentReference[oaicite:17]{index=17}
- `/add_donator`, `/donator_list` — Donator менежмент.:contentReference[oaicite:18]{index=18}
- `/resync` — slash командуудыг дахин sync хийнэ.:contentReference[oaicite:19]{index=19}
- `/diag` — DB/OpenAI/permission онош. `/diag_dryrun` — хадгалалт хийдэггүй хиймэл тест.:contentReference[oaicite:20]{index=20}

---

## ❓Түгээмэл асуулт

**Q: GPT заримдаа удааширвал яах вэ?**  
A: `/go_gpt` нь GPT‑ийн гаралтыг шалгаж (sanitize) локал сайжруулалт хийдэг; шаардлагатай үед `/go_bot`‑ын алгоритмууд руу fallback хийж болно.:contentReference[oaicite:21]{index=21}

**Q: Match түүхийг яаж хардаг вэ?**  
A: `/match_history` — сүүлийн 5 тоглолтын огноо, стратеги, ялсан/ялагдсан багуудыг харуулна.:contentReference[oaicite:22]{index=22}

**Q: Никнэйм яагаад өөрчлөгдөөд байна?**  
A: Donator эмоджи + Tier + (сүүлийн 12 цагийн ✅/❌) гүйцэтгэлийг автоматаар оруулдаг. Хэт урт бол 32 тэмдэгтэд тааруулж тайрна.:contentReference[oaicite:23]{index=23}

---

## 🛠 Ашиглаж буй зүйлс

- Discord Slash Commands, Railway, PostgreSQL  
- OpenAI GPT (gpt‑4o) — багийн тэнцвэржилтийн туслах хөдөлгүүр:contentReference[oaicite:24]{index=24}

