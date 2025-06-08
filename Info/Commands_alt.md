# RZR Bot Commands (Alternative Style)

## 🟢 Setup & Registration

/start\_match – Session эхлүүлнэ, баг/тоглогчийн тоог тохируулна (Бүгд — initiator авна)
/addme – Тоглогч өөрийгөө бүртгүүлнэ (Бүгд)
/remove – Бүртгэлээ цуцална (Бүгд)
/remove\_user – Админ тоглогчийн бүртгэлийг цуцална (Admin)

## 👀 Team Assignment

/show\_added\_players – Бүртгүүлсэн тоглогчдыг харуулна (Бүгд)
/go\_bot – Онооны дагуу баг хуваарилна (Зөвхөн initiator)
/go\_gpt – GPT API ашиглан баг хуваарилна (Зөвхөн initiator)
/set\_match – Админ гараар баг бүрдүүлнэ (Admin — initiator авна)
/clear\_match – Баг бүртгэлийг цэвэрлэнэ (Admin)

## ✍️ Match Result бүртгэл

/set\_match\_result – Match бүртгэнэ, +1/-1 оноо, tier өөрчлөлттэй (Зөвхөн initiator)
/set\_match\_result\_fountain – +2/-2 оноотой тусгай бүртгэл (Зөвхөн initiator)
/undo\_last\_match – Сүүлийн match-ийн оноог буцаана (Зөвхөн initiator)

## 📊 Оноо, Tier, Статистик

/my\_score – Өөрийн оноо, tier-ийг харуулна (Бүгд)
/user\_score @user – Хэн нэгний оноо, tier (Бүгд)
/players\_stats – Win/Loss статистик (Бүгд)
/set\_tier – Tier-г админ шууд өгнө (Admin)
/add\_score – + оноо нэмнэ (Admin)

## 💎 File & Backup

/backup\_now – JSON файлуудыг GitHub руу commit хийнэ (Admin)

## 💖 Donator систем

/add\_donators – Donator бүртгэнэ (Admin)
/donator\_list – Donator жагсаалт emoji/shield-тай (Бүгд)

## ℹ️ Тусламж

/help\_info – Ботын товч танилцуулга (Бүгд) (readme.md)
/help\_commands – Коммандуудын тайлбар жагсаалт (Бүгд) (commands.md)

## 📜 Бусад

/match\_history – Сүүлийн 5 тоглолтын үр дүнг харуулна (Бүгд)
/ping – Ботын latency-г шалгана (Бүгд)
/whois – Mention хийсэн хэрэглэгчийн нэрийг харуулна (Бүгд)
/debug\_id – Таны Discord ID-г харуулна (Бүгд)
