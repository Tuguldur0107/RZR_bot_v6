
# 🧾 RZR Bot v6.0 - Command Implementation Checklist

| №  | Command нэр                   | Status | Үүрэг                                                  | File ашиглах                                        | Хэрэглэгчийн түвшин      |
|----|-------------------------------|--------|--------------------------------------------------------|----------------------------------------------------|--------------------------|
| 1  | /start_match                  | Done   | Session эхлүүлнэ, баг/тоглогчийн тоог тохируулна       | -                                                  | Бүгд (initiator авна)    |
| 2  | /addme                        | Done   | Тоглогч өөрийгөө бүртгүүлнэ                             | TEAM_SETUP                                         | Бүгд                     |
| 3  | /remove                       | Done   | Тоглогч бүртгэлээ цуцална                                | TEAM_SETUP                                         | Бүгд                     |
| 4  | /remove_user                  | Done   | Админ тоглогчийн бүртгэлийг цуцална                      | TEAM_SETUP                                         | Admin                    |
| 5  | /show_added_players           | Done   | Бүртгүүлсэн тоглогчдыг харуулна                          | TEAM_SETUP                                         | Бүгд                     |
| 6  | /go_bot                       | Done   | Онооны дагуу баг хуваарилна                             | match_log.json                                     | Зөвхөн initiator         |
| 7  | /go_gpt                       | Done   | GPT API-гаар баг хуваарилна                             | match_log.json                                     | Зөвхөн initiator         |
| 8  | /set_match                    | Done   | Админ гараар баг бүрдүүлнэ                              | TEAM_SETUP                                         | Admin (initiator авна)   |
| 9  | /clear_match                  | Done   | Баг бүртгэлийг цэвэрлэнэ                                | TEAM_SETUP                                         | Admin                    |
| 10 | /set_match_result            | Done   | Match бүртгэнэ, +1/-1 оноо, tier өөрчлөнө               | scores.json, score_log.jsonl, player_stats.json, match_log.json | Зөвхөн initiator         |
| 11 | /set_match_result_fountain   | Done   | +2/-2 Fountain Match бүртгэнэ                            | scores.json, score_log.jsonl, player_stats.json, match_log.json | Зөвхөн initiator         |
| 12 | /undo_last_match             | Done   | Сүүлийн Match оноог буцаана                             | scores.json, score_log.jsonl, player_stats.json, match_log.json | Зөвхөн initiator         |
| 13 | /my_score                    | Done   | Өөрийн оноо, tier-ийг харуулна                          | scores.json                                        | Бүгд                     |
| 14 | /user_score                  | Done   | Үзэгсдийн оноо, tier-ийг харуулна                       | scores.json                                        | Бүгд                     |
| 15 | /players_stats               | Done   | Win/Loss статистик                                     | player_stats.json                                  | Бүгд                     |
| 16 | /backup_now                  | Done   | JSON файлуудыг GitHub руу commit хийнэ                  | JSON бүх файл                                      | Admin                    |
| 17 | /set_score                   | Done   | Tier + оноо өгнө                                        | scores.json                                        | Admin                    |
| 18 | /add_score                   | Done   | + оноо нэмнэ                                           | scores.json                                        | Admin                    |
| 19 | /add_donators                | Done   | Donator бүртгэнэ                                       | donators.json                                      | Admin                    |
| 20 | /donator_list                | Done   | Donator жагсаалтыг харуулна                             | donators.json                                      | Бүгд                     |
| 21 | /help_info                   | Done   | Ботын тухай танилцуулга                                | readme.md                                          | Бүгд                     |
| 22 | /help_commands               | Done   | Коммандуудын тайлбар жагсаалт                           | commands.md                                        | Бүгд                     |
| 23 | /match_history               | Done   | Сүүлийн 5 тоглолтын үр дүн харуулна                     | match_log.json                                     | Бүгд                     |
| 24 | /ping                        | Done   | Ботын latency-г шалгана                                 | -                                                  | Бүгд                     |
| 25 | /whois                       | Done   | Mention хийгсэн хэрэглэгчийн нэрийг харуулна            | -                                                  | Бүгд                     |
| 26 | /debug_id                    | Done   | Таны Discord ID-г харуулна                              | -                                                  | Бүгд                     |
