# 📘 RZR Bot — Коммандуудын жагсаалт (SQL хувилбар)

RZR Bot 6.1 нь PostgreSQL дата бааз дээр үндэслэсэн, оноо, tier, win/loss бүртгэлтэй, багийн автомат хуваарилалт хийдэг Discord bot юм. Доорх бүх коммандууд Slash (`/`) хэлбэрээр ажиллана.

## 🟢 1. Session эхлүүлэлт ба бүртгэл

/start\_match — Шинэ session эхлүүлж, баг болон тоглогчийн тоог заана *(admin эсвэл эхлүүлэгч)*

/addme — Өөрийгөө session-д бүртгүүлнэ *(бүгд)*

/remove — Өөрийгөө бүртгэлээс хасна *(бүгд)*

/show\_added\_players — Бүртгэгдсэн тоглогчдыг жагсаана *(бүгд)*

/remove\_user — Админ: Тоглогчийг бүртгэлээс хасна

/clear\_match — Session болон багийн бүртгэлийг цэвэрлэнэ *(admin)*

## 👀 2. Багийн хуваарилалт

/go\_bot — Онооны дагуу автомат баг хуваарилна *(admin эсвэл эхлүүлэгч)*

/go\_gpt — GPT ашиглан онооны дагуу баг хуваарилна *(admin эсвэл эхлүүлэгч)*

/set\_match — Гараар баг бүрдүүлнэ *(admin)*

/current\_match — Session бүртгэгдсэн одоогийн багуудыг харуулна *(бүгд)*

## ✍️ 3. Match-ийн үр дүн бүртгэх

/set\_match\_result — Ялагч, ялагдагч багуудыг зааж оноо/түйвшинг шинэчилнэ (+1/-1)

/set\_match\_result\_fountain — Fountain төрөл: оноо +2/-2 тооцно

/undo\_last\_match — Сүүлд хийсэн match-ийг буцаана

## 📊 4. Оноо, түвшин, статистик

/my\_score — Өөрийн оноо болон tier-г харуулна *(бүгд)*

/user\_score @mention — Хэн нэгний оноо, tier-г харуулна *(бүгд)*

/player\_stats — Win/Loss статистик *(бүгд)*

/player\_stats\_users — Хэд хэдэн тоглогчийн статистик *(admin)*

/leaderboard — Tier, score, winrate жагсаалт *(admin)*

## 💖 5. Donator систем

/add\_donator — Хандивлагч нэмнэ *(admin)*

/donator\_list — Donator жагсаалт emoji/shield-тэй харуулна *(admin)*

## ℹ️ 6. Тусламж, мэдээлэл

/help\_info — RZR Bot-ын танилцуулга (info.md)

/help\_commands — Коммандуудын тайлбартай жагсаалт (commands\_alt.md)

## 🔧 7. Админ тохиргоо

/set\_tier — Хэрэглэгчийн tier болон score-г гараар тохируулна

/add\_score — Оноо нэмэх/хасах

/backup\_now — GitHub руу гараар backup хийнэ

/resync — Slash командуудыг сервертэй дахин sync хийнэ

## 🧪 8. Бусад

/match\_history — Сүүлийн 5 match бүртгэл

/ping — Ботын хариу өгөх хурд (latency)

/whois — Mention хийсэн хэрэглэгчийн нэр/ID-г харуулна

/debug\_id — Таны Discord ID-г харуулна
