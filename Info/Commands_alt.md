# 📒 RZR Bot — Коммандууд

Бүх команд Slash (/) хэлбэртэй.

## 🟢 Session
/ping — Latency шалгах
/start_match — Session эхлүүлэх
/addme — Өөрийгөө бүртгэх
/remove — Өөрийгөө хасах
/remove_user <@user> — Тоглогч хасах
/show_added_players — Бүртгэлтэй тоглогчид
/set_match <team> <mentions> — Гараар оноох
/clear_match — Session цэвэрлэх

## ⚖️ Баг
/go_bot <teams> <size> — Алгоритмаар хуваах
/go_gpt <teams> <size> — GPT хуваах
/current_match — Одоогийн бүрэлдэхүүн
/change_player <from> <to> — Тоглогч солих
/matchups [seed] — хоорондоо тоглох баг

## 🏆 Үр дүн
/set_match_result <winners> <losers> — Match бүртгэх
/set_match_result_fountain <winners> <losers> — Fountain төрөл
/undo_last_match — Сүүлийн match буцаах
/match_history — Сүүлийн 5 match

## 📊 Оноо / Tier
/my_score — Миний tier, score
/user_score <@user> — Тоглогчийн tier, score
/player_stats — Миний статистик
/leaderboard [limit] — Топ жагсаалт
/set_tier <@user> <tier> [score] — Tier/score тохируулах
/add_score <@mentions> [pts] — Оноо нэмэх/хасах

## 💖 Donator
/add_donator <@user> <mnt> — Donator нэмэх
/donator_list — Donator жагсаалт

## ℹ️ Тусламж
/help_info — Танилцуулга
/help_commands — Коммандууд
/diag — Оношилгоо

## 🛠 Бусад
/resync — Комманд sync
/whois <@user> — Хэрэглэгчийн мэдээлэл
/debug_id — Миний ID
/kick <@user> — Vote-kick санал
/kick_review [@user] — Vote-kick жагсаалт