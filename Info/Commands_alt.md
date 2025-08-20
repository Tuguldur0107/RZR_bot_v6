# 📘 RZR Bot — Коммандуудын жагсаалт (DB хувилбар)

RZR Bot нь PostgreSQL дата бааз дээр ажиллаж, оноо, tier, win/loss бүртгэл болон багийн автомат хуваарилалт хийдэг Discord bot юм. Доорх бүх коммандууд Slash (`/`) хэлбэрээр ажиллана.

---

## 🟢 1. Session эхлүүлэлт ба бүртгэл

/start_match — Шинэ session эхлүүлнэ *(admin эсвэл эхлүүлэгч)*  
/addme — Өөрийгөө session-д бүртгүүлнэ *(бүгд)*  
/remove — Өөрийгөө бүртгэлээс хасна *(бүгд)*  
/show_added_players — Бүртгэгдсэн тоглогчдыг жагсаана *(бүгд)*  
/remove_user — Тоглогчийг бүртгэлээс хасна *(admin)*  
/clear_match — Session болон багийн бүртгэлийг цэвэрлэнэ *(admin)*  

---

## 👀 2. Багийн хуваарилалт

/go_bot — Оноо, tier-ийн дагуу автомат баг хуваарилна *(admin эсвэл эхлүүлэгч)*  
/go_gpt — GPT ашиглан багийг тэнцвэртэй хуваарилна *(admin эсвэл эхлүүлэгч)*  
/set_match — Гараар баг бүрдүүлнэ *(admin)*  
/current_match — Session-д бүртгэгдсэн одоогийн багуудыг харуулна *(бүгд)*  
/change_player — Багийн гишүүдийг сольж оруулна *(admin эсвэл эхлүүлэгч)*  

---

## ✍️ 3. Match-ийн үр дүн бүртгэх

/set_match_result — Match бүртгэнэ (+1/-1 оноо, tier өөрчлөгдөнө)  
/set_match_result_fountain — “Fountain” төрөл: оноо +2/-2 тооцно  
/undo_last_match — Сүүлд хийсэн match-ийн үр дүнг буцаана  

---

## 📊 4. Оноо, түвшин, статистик

/my_score — Өөрийн оноо болон tier-г харуулна *(бүгд)*  
/user_score @mention — Сонгосон тоглогчийн оноо, tier-г харуулна *(бүгд)*  
/player_stats — Өөрийн win/loss статистик *(бүгд)*  
/leaderboard — Топ 10 тоглогчийн tier, score, winrate *(бүгд)*  
/set_tier — Тоглогчийн tier болон оноог гараар тохируулна *(admin)*  
/add_score — Оноо нэмэх/хасах *(admin)*  

---

## 💖 5. Donator систем

/add_donator — Хэрэглэгчийг Donator болгон, хандив нэмнэ *(admin)*  
/donator_list — Donator жагсаалтыг (Top 3 ба бусад) харуулна *(admin)*  

---

## ℹ️ 6. Тусламж, мэдээлэл

/help_info — RZR Bot-ын танилцуулга (`Readme.md`)  
/help_commands — Бүх командын тайлбар жагсаалт (`Commands_alt.md`)  

---

## 🔧 7. Админ тохиргоо

/resync — Slash командуудыг дахин sync хийнэ *(admin)*  

---

## 🧪 8. Бусад

/match_history — Сүүлийн 5 match-ийн бүртгэл  
/ping — Bot-ын latency-г шалгана  
/whois — Mention хийсэн хэрэглэгчийн нэр, ID-г харуулна  
/debug_id — Таны Discord ID-г харуулна  
