# Commands

| №   | Command нэр                  | Үүрэг                                                        | File ашиглах                                                           | Хэрэглэгчийн түвшин  |
|-----|------------------------------|--------------------------------------------------------------|------------------------------------------------------------------------|-----------------------|
| 1   | `/make_team`                 | Session эхлүүлнэ, багийн тоо ба тоглогчийн тоог тохируулна   | -                                                                      | Бүгд                  |
| 2   | `/addme`                     | Тоглогч өөрийгөө бүртгүүлнэ                                  | TEAM_SETUP                                                             | Бүгд                  |
| 3   | `/remove`                    | Тоглогч бүртгэлээ цуцална                                    | TEAM_SETUP                                                             | Бүгд                  |
| 4   | `/make_team_go`              | Онооны дагуу баг автоматаар хуваарилна                       | `scores.json`                                                          | Зөвхөн initiator      |
| 5   | `/gpt_go`                    | GPT API ашиглаж багыг тэнцвэртэй хуваарилна                  | `scores.json`                                                          | Зөвхөн initiator      |
| 6   | `/set_team`                  | Админ гараар баг үүсгэнэ                                     | TEAM_SETUP                                                             | Admin                 |
| 7   | `/set_match_result`          | Match бүртгэнэ, +1/-1 оноо, tier өөрчилнө                    | `scores.json`, `score_log.jsonl`, `player_stats.json`, `match_log.json` | Зөвхөн initiator      |
| 8   | `/set_match_result_fountain` | Match бүртгэнэ, +2/-2 оноо, tier өөрчилнө                    | `scores.json`, `score_log.jsonl`, `player_stats.json`, `match_log.json` | Зөвхөн initiator      |
| 9   | `/set_match_result_manual`   | Гараар баг бүрдүүлээд match бүртгэнэ                         | `scores.json`, `score_log.jsonl`, `player_stats.json`, `match_log.json` | Admin                 |
| 10  | `/undo_last_match`           | Сүүлд хийсэн match-ийн оноог буцаах                          | `scores.json`, `score_log.jsonl`, `player_stats.json`, `match_log.json` | Зөвхөн initiator      |
| 11  | `/my_score`                  | Өөрийн оноо болон tier-ийг харуулна                          | `scores.json`                                                          | Бүгд                  |
| 12  | `/user_score`                | Тоглогчийн оноо болон tier-ийг харуулна                      | `scores.json`                                                          | Бүгд                  |
| 13  | `/players_stats`             | Тоглогчийн ялалт/ялагдал/нийт тоглолтын статистик            | `player_stats.json`                                                    | Бүгд                  |
| 14  | `/backup_now`                | JSON файлуудыг GitHub руу commit хийнэ                       | JSON бүх файл                                                          | Admin                 |
| 15  | `/set_tier`                  | Админ тоглогчид tier-г шууд өгнө                             | `scores.json`                                                          | Admin                 |
| 16  | `/add_score`                 | Админ 1+ тоглогчид +- оноо өгнө                              | `scores.json`                                                          | Admin                 |
| 17  | `/add_donators`              | Donator бүртгэнэ                                             | `donators.json`                                                        | Admin                 |
| 18  | `/donators`                  | Donator жагсаалт emoji/shield-тай харуулна                   | `donators.json`                                                        | Бүгд                  |
| 19  | `/help_info`                 | Ботны товч танилцуулга                                       | `readme.md`                                                            | Бүгд                  |
| 20  | `/help_commands`             | Коммандуудын тайлбар жагсаалт                                | `commands.md`                                                          | Бүгд                  |
| 21  | `/match_history`             | Сүүлийн 5 тоглолтын үр дүнг харуулна                         | `match_log.json`                                                       | Бүгд                  |
