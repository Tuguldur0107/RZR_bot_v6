import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import json
from datetime import datetime, timezone, timedelta
import pytz
from openai import OpenAI


MN_TZ = pytz.timezone("Asia/Ulaanbaatar")

# ⏱ Монголын цаг
now_mn = datetime.now(MN_TZ)

# 🌐 Token-уудыг ENV-оос ачаална
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")


client = OpenAI(api_key=OPENAI_API_KEY)

# 📁 Файлын замууд (Render Volume: /mnt/data биш харин local path)
BASE_DIR = "data"

SCORE_FILE = f"{BASE_DIR}/scores.json"
MATCH_LOG_FILE = f"{BASE_DIR}/match_log.json"
LAST_FILE = f"{BASE_DIR}/last_match.json"
SHIELD_FILE = f"{BASE_DIR}/donate_shields.json"
DONATOR_FILE = f"{BASE_DIR}/donators.json"
SCORE_LOG_FILE = f"{BASE_DIR}/score_log.jsonl"
PLAYER_STATS_FILE = f"{BASE_DIR}/player_stats.json"

INFO_DIR = "Info"

COMMANDS_FILE = f"{INFO_DIR}/commands.md"
HELP_FILE = f"{INFO_DIR}/Readme.txt"

# ⚙️ Discord intents
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# 🎮 Session төлөв
GAME_SESSION = {
    "active": False,
    "start_time": None,
    "last_win_time": None
}

# 🧩 Баг бүрдүүлэлтийн төлөв
TEAM_SETUP = {
    "initiator_id": None,
    "player_ids": [],
    "team_count": 2,
    "players_per_team": 5,
    "teams": []
}







def now_mongolia():
    return datetime.now(MN_TZ)
  
# ✅ Админ шалгах decorator
def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

def load_scores():
    return load_json(SCORE_FILE)

# 📤 JSON хадгалах/ачаалах функцүүд
def load_json(filename):
    if not os.path.exists(filename):
        return {}
    with open(filename, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def append_to_json_list(filename, new_data):
    data = load_json(filename)

    if not isinstance(data, list):
        data = []

    data.append(new_data)
    save_json(filename, data)

    # 🟡 GitHub commit олон файл дотроос ганцыг явуулах тул list болгож оруулна
    commit_to_github_multi([filename], f"append match log to {os.path.basename(filename)}")

def log_score_transaction(action, winners, losers, initiator_id, timestamp):
    log_entry = {
        "action": action,
        "winners": winners,
        "losers": losers,
        "initiator_id": initiator_id,
        "timestamp": timestamp
    }
    append_to_json_list(SCORE_LOG_FILE, log_entry)

async def github_auto_commit():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            print("🕒 GitHub commit task ажиллаж байна...")
            file_list = [
                SCORE_FILE,
                MATCH_LOG_FILE,
                LAST_FILE,
                SHIELD_FILE,
                DONATOR_FILE,
                SCORE_LOG_FILE
            ]
            commit_to_github_multi(file_list, "⏱ Автомат GitHub commit (60мин)")
        except Exception as e:
            print("❌ GitHub commit task error:", e)

        await asyncio.sleep(3600)  # 60 минут

def commit_to_github_multi(file_list, message="update"):
    import base64
    import requests
    import os

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    branch = os.environ.get("GITHUB_BRANCH", "main")

    if not token or not repo:
        print("❌ GitHub тохиргоо бүрэн биш байна.")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }

    for filepath in file_list:
        github_path = os.path.basename(filepath)

        try:
            with open(filepath, "rb") as f:
                content = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            print(f"⚠️ {github_path} файл уншихад алдаа гарлаа:", e)
            continue

        url = f"https://api.github.com/repos/{repo}/contents/{github_path}"

        # 📥 sha авах (хуучин commit байвал)
        res = requests.get(url, headers=headers, params={"ref": branch})
        sha = res.json().get("sha") if res.ok else None

        data = {
            "message": message,
            "branch": branch,
            "content": content
        }
        if sha:
            data["sha"] = sha

        # 🚀 Commit хийнэ
        r = requests.put(url, headers=headers, json=data)
        if r.status_code in [200, 201]:
            print(f"✅ {github_path} GitHub-д хадгалагдлаа.")
        else:
            print(f"❌ {github_path} commit алдаа:", r.status_code, r.text)

# ⏱ Session хугацаа дууссан эсэх шалгагч task
async def session_timeout_checker():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(60)  # ⏳ 1 минут тутамд шалгана

        if GAME_SESSION["active"]:
            now = now_mongolia()

            # ❶ 24 цагийн timeout (одоогийн logic)
            if (
                GAME_SESSION["last_win_time"] and
                (now - GAME_SESSION["last_win_time"]).total_seconds() > 86400
            ):
                GAME_SESSION["active"] = False
                GAME_SESSION["start_time"] = None
                GAME_SESSION["last_win_time"] = None
                print("🕛 Session хаагдлаа (24 цаг).")
                continue

            # ❷ 5 минутын timeout: make_team хийсэн ч баг хуваарилаагүй үед
            if (
                TEAM_SETUP and
                not TEAM_SETUP.get("teams") and
                (now - GAME_SESSION["start_time"]).total_seconds() > 300
            ):
                GAME_SESSION["active"] = False
                GAME_SESSION["start_time"] = None
                GAME_SESSION["last_win_time"] = None
                TEAM_SETUP.clear()
                print("⏰ Session автоматаар хаагдлаа (5 минут баг хуваарилаагүй).")

TIER_WEIGHT = {
    "4-3": 0,
    "4-2": 5,
    "4-1": 10,
    "3-3": 15,
    "3-2": 20,
    "3-1": 25,
    "2-3": 30,
    "2-2": 35,
    "2-1": 40
}

def tier_score(data: dict) -> int:
    tier = data.get("tier", "4-3")
    score = data.get("score", 0)
    return TIER_WEIGHT.get(tier, 0) + score

def snake_teams(player_weights, team_count, players_per_team):
    sorted_players = sorted(player_weights.items(), key=lambda x: x[1], reverse=True)
    teams = [[] for _ in range(team_count)]

    forward = True
    team_index = 0
    for uid, _ in sorted_players:
        teams[team_index].append(uid)

        if forward:
            team_index += 1
            if team_index == team_count:
                team_index -= 1
                forward = False
        else:
            team_index -= 1
            if team_index < 0:
                team_index = 0
                forward = True

    return teams

def greedy_teams(player_weights, team_count, players_per_team):
    sorted_players = sorted(player_weights.items(), key=lambda x: x[1], reverse=True)
    teams = [[] for _ in range(team_count)]
    team_totals = [0] * team_count

    for uid, weight in sorted_players:
        min_team_index = team_totals.index(min(team_totals))
        teams[min_team_index].append(uid)
        team_totals[min_team_index] += weight

    return teams

def total_weight_difference(teams, player_weights):
    team_totals = [sum(player_weights.get(uid, 0) for uid in team) for team in teams]
    return max(team_totals) - min(team_totals)

def get_default_tier():
    return {"tier": "4-1", "score": 0}

TIER_ORDER = [
    "4-3", "4-2", "4-1",
    "3-3", "3-2", "3-1",
    "2-3", "2-2", "2-1"
]

def promote_tier(current_tier):
    try:
        idx = TIER_ORDER.index(current_tier)
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
        else:
            return current_tier  # аль хэдийн хамгийн дээд tier байна
    except ValueError:
        return current_tier  # tier list-д байхгүй байвал өөрчлөхгүй

def demote_tier(current_tier):
    try:
        idx = TIER_ORDER.index(current_tier)
        if idx - 1 >= 0:
            return TIER_ORDER[idx - 1]
        else:
            return current_tier  # аль хэдийн хамгийн доод tier байна
    except ValueError:
        return current_tier

def update_player_stats(winners, losers, undo=False):
    stats = load_json(PLAYER_STATS_FILE)

    for uid in winners:
        uid_str = str(uid)
        if uid_str not in stats:
            stats[uid_str] = {"wins": 0, "losses": 0}
        if undo:
            stats[uid_str]["wins"] = max(0, stats[uid_str]["wins"] - 1)
        else:
            stats[uid_str]["wins"] += 1

    for uid in losers:
        uid_str = str(uid)
        if uid_str not in stats:
            stats[uid_str] = {"wins": 0, "losses": 0}
        if undo:
            stats[uid_str]["losses"] = max(0, stats[uid_str]["losses"] - 1)
        else:
            stats[uid_str]["losses"] += 1

    save_json(PLAYER_STATS_FILE, stats)


def append_match_log(teams, winner_team, initiator_id, mode="manual"):
    if not os.path.exists(MATCH_LOG_FILE):
        match_log = []
    else:
        match_log = load_json(MATCH_LOG_FILE)

    match_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "initiator_id": initiator_id,
        "teams": teams,
        "winner_team": winner_team
    })

    save_json(MATCH_LOG_FILE, match_log)

def save_last_match(winners, losers):
    last = {
        "winners": winners,
        "losers": losers
    }
    save_json(LAST_FILE, last)

def clear_last_match():
    save_json(LAST_FILE, {})

def load_donators():
    if not os.path.exists(DONATOR_FILE):
        return {}
    try:
        with open(DONATOR_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}  # ⚠️ хоосон эсвэл буруу format-тай файл байвал зүгээр л хоосон dict буцаана

def save_donators(data):
    with open(DONATOR_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_donator_emoji(data):
    from datetime import datetime, timezone, timedelta

    total = data.get("total_mnt", 0)
    last_donated = data.get("last_donated")

    if not last_donated:
        return None

    donated_time = datetime.fromisoformat(last_donated)
    now = datetime.now(timezone.utc)

    # Хэрвээ 30 хоног хэтэрсэн бол emoji байхгүй
    if (now - donated_time).days > 30:
        return None

    if total >= 30000:
        return "👑"
    elif total >= 10000:
        return "💸"
    else:
        return "💰"
 
def clean_nickname(nick: str) -> str:
    if not nick:
        return ""
    if "|" in nick:
        return nick.split("|")[-1].strip()
    return nick.strip()

async def update_nicknames_for_users(guild, user_ids: list):
    scores = load_scores()
    donors = load_donators()

    for user_id in user_ids:
        member = guild.get_member(int(user_id))
        if not member:
            continue

        score_data = scores.get(str(user_id))
        if not score_data:
            continue

        tier = score_data.get("tier", "4-1")
        donor_data = donors.get(str(user_id), {})
        emoji = get_donator_emoji(donor_data)

        # ✅ nickname-ыг цэвэрлэнэ
        base_nick = clean_nickname(member.display_name)

        # ✅ Prefix-г бүрдүүлнэ
        if emoji:
            prefix = f"{emoji} {tier}"
        else:
            prefix = tier

        new_nick = f"{prefix} | {base_nick}"

        if member.nick == new_nick:
            continue

        try:
            await member.edit(nick=new_nick)
        except discord.Forbidden:
            print(f"⛔️ {member} nickname-г өөрчилж чадсангүй.")
        except Exception as e:
            print(f"⚠️ {member} nickname-д алдаа гарлаа: {e}")

def call_gpt_balance_api(team_count, players_per_team, player_ids, scores):
    if not OPENAI_API_KEY:
        raise ValueError("❌ OPENAI_API_KEY тодорхойлогдоогүй байна.")

    # 🔢 Онооны жингүүдийг бэлдэнэ
    player_scores = []
    for uid in player_ids:
        data = scores.get(str(uid), {})
        power = tier_score(data)
        player_scores.append({"id": uid, "power": power})

    prompt = f"""
{team_count} багт {players_per_team} хүнтэйгээр дараах тоглогчдыг онооны дагуу хамгийн тэнцүү хуваа.
Тоглогчид: {player_scores}
Хэрвээ баг дотор онооны зөрүү их байвал, хамгийн их оноотой тоглогчийг солих замаар онооны зөрүүг багасга.
JSON зөвхөн дараах бүтэцтэй буцаа:
{{"teams": [[123,456,789], [234,567,890]]}}
""".strip()

    print("📡 GPT-д хүсэлт илгээж байна...")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a helpful assistant that balances teams."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1024,
            seed=42,
            response_format="json"
        )
    except Exception as e:
        print("❌ GPT API error:", e)
        raise

    try:
        content = response.choices[0].message.content
        print("📥 GPT хариу:\n", content)
        parsed = json.loads(content)
        teams = parsed.get("teams", [])
        if not isinstance(teams, list) or not all(isinstance(team, list) for team in teams):
            raise ValueError("⚠️ GPT JSON бүтэц буруу байна.")
        return teams
    except Exception as e:
        print("❌ GPT response parse алдаа:", e)
        raise









@bot.tree.command(name="start_match", description="Session эхлүүлнэ, багийн тоо болон тоглогчийн тоог тохируулна")
@app_commands.describe(team_count="Хэдэн багтай байх вэ", players_per_team="Нэг багт хэдэн хүн байх вэ")
async def start_match(interaction: discord.Interaction, team_count: int, players_per_team: int):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # 🧠 Session эхлүүлнэ
    now = datetime.now(MN_TZ)
    GAME_SESSION["active"] = True
    GAME_SESSION["start_time"] = now
    GAME_SESSION["last_win_time"] = now

    TEAM_SETUP.clear()
    TEAM_SETUP["team_count"] = team_count
    TEAM_SETUP["players_per_team"] = players_per_team
    TEAM_SETUP["player_ids"] = []
    TEAM_SETUP["teams"] = []
    TEAM_SETUP["initiator_id"] = interaction.user.id

    await interaction.followup.send(f"🟢 {team_count} багтай, {players_per_team} хүнтэй Session эхэллээ. `addme` коммандаар тоглогчид бүртгүүлнэ үү.")

@bot.tree.command(name="addme", description="Тоглогч өөрийгөө бүртгүүлнэ")
async def addme(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    user_id = interaction.user.id

    if not GAME_SESSION["active"]:
        await interaction.followup.send("⚠️ Одоогоор session эхлээгүй байна.")
        return

    if user_id in TEAM_SETUP["player_ids"]:
        await interaction.followup.send("📌 Та аль хэдийн бүртгүүлсэн байна.")
        return

    TEAM_SETUP["player_ids"].append(user_id)

    await interaction.followup.send(f"✅ {interaction.user.mention} бүртгүүллээ.\nНийт бүртгэгдсэн: {len(TEAM_SETUP['player_ids'])}")


@bot.tree.command(name="remove", description="Тоглогч өөрийгөө бүртгэлээс хасна")
async def remove(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    user_id = interaction.user.id

    if not GAME_SESSION["active"]:
        await interaction.followup.send("⚠️ Session идэвхгүй байна.")
        return

    if user_id not in TEAM_SETUP["player_ids"]:
        await interaction.followup.send("❌ Та бүртгэлд байхгүй байна.")
        return

    TEAM_SETUP["player_ids"].remove(user_id)

    await interaction.followup.send(f"🗑 {interaction.user.mention} бүртгэлээс хасагдлаа.\nҮлдсэн: **{len(TEAM_SETUP['player_ids'])}** тоглогч")

@bot.tree.command(name="remove_user", description="Админ: тоглогчийг бүртгэлээс хасна")
@app_commands.describe(mention="Хасах тоглогчийг mention хийнэ")
async def remove_user(interaction: discord.Interaction, mention: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    # ID-г mention-оос салгаж авна
    user_ids = [int(word[2:-1].replace("!", "")) for word in mention.split() if word.startswith("<@") and word.endswith(">")]
    if not user_ids:
        await interaction.followup.send("⚠️ Зөв mention хийгээгүй байна.")
        return

    removed = 0
    for uid in user_ids:
        if uid in TEAM_SETUP["player_ids"]:
            TEAM_SETUP["player_ids"].remove(uid)
            removed += 1

    if removed == 0:
        await interaction.followup.send("ℹ️ Бүртгэлээс хасагдсан тоглогч олдсонгүй.")
    else:
        await interaction.followup.send(f"🗑 {removed} тоглогч бүртгэлээс хасагдлаа.")

@bot.tree.command(name="show_added_players", description="Бүртгэгдсэн тоглогчдыг харуулна")
async def show_added_players(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    if not TEAM_SETUP["player_ids"]:
        await interaction.followup.send("📭 Одоогоор бүртгэгдсэн тоглогч алга.")
        return

    guild = interaction.guild
    mentions = [guild.get_member(uid).mention for uid in TEAM_SETUP["player_ids"] if guild.get_member(uid)]
    mention_text = "\n".join(mentions)

    await interaction.followup.send(f"📋 Бүртгэгдсэн тоглогчид ({len(mentions)}):\n{mention_text}")

@bot.tree.command(name="set_match", description="Админ: гараар баг бүрдүүлнэ")
@app_commands.describe(team_number="Багийн дугаар", mentions="Тоглогчдыг mention хийнэ")
async def set_match(interaction: discord.Interaction, team_number: int, mentions: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    user_ids = [int(word[2:-1].replace("!", "")) for word in mentions.split() if word.startswith("<@") and word.endswith(">")]

    if not user_ids:
        await interaction.followup.send("⚠️ Хамгийн багадаа нэг тоглогч mention хийнэ үү.", ephemeral=True)
        return

    if not GAME_SESSION["active"]:
        GAME_SESSION["active"] = True
        GAME_SESSION["start_time"] = datetime.now(MN_TZ)
        GAME_SESSION["last_win_time"] = datetime.now(MN_TZ)

    # ⚠️ Давхар бүртгэл шалгана
    all_existing_ids = [uid for team in TEAM_SETUP["teams"] for uid in team]
    duplicate_ids = [uid for uid in user_ids if uid in all_existing_ids]
    if duplicate_ids:
        await interaction.followup.send("🚫 Зарим тоглогч аль нэг багт бүртгэгдсэн байна.", ephemeral=True)
        return

    # Хэрвээ teams[] байхгүй бол үүсгэнэ
    while len(TEAM_SETUP["teams"]) < team_number:
        TEAM_SETUP["teams"].append([])

    TEAM_SETUP["teams"][team_number - 1] = user_ids

    await interaction.followup.send(f"✅ {len(user_ids)} тоглогчийг {team_number}-р багт бүртгэлээ.")

@bot.tree.command(name="clear_match", description="Админ: одоогийн идэвхтэй match-ийн баг бүртгэлийг цэвэрлэнэ")
async def clear_match(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    # 🧹 Багийн бүртгэл цэвэрлэнэ
    TEAM_SETUP["teams"] = []
    GAME_SESSION["active"] = False
    GAME_SESSION["start_time"] = None
    GAME_SESSION["last_win_time"] = None
    
    if TEAM_SETUP["player_ids"]:
        cleared_users = [f"<@{uid}>" for uid in TEAM_SETUP["player_ids"]]
        await interaction.followup.send(f"⚠️ Дараах тоглогчдын бүртгэл цуцлагдлаа: {', '.join(cleared_users)}")

    await interaction.followup.send("🧼 Match-ийн бүртгэл амжилттай цэвэрлэгдлээ.")

@bot.tree.command(name="go_bot", description="Онооны дагуу тэнцвэртэй баг хуваарилна")
@app_commands.describe(
    team_count="Хэдэн багт хуваах вэ",
    players_per_team="Нэг багт хэдэн тоглогч байх вэ"
)
async def go_bot(interaction: discord.Interaction, team_count: int, players_per_team: int):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # ✅ Зөвхөн initiator эсвэл админ ажиллуулна
    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    # ✅ Session шалгана
    if not GAME_SESSION["active"]:
        await interaction.followup.send("⚠️ Session идэвхгүй байна.")
        return

    player_ids = TEAM_SETUP.get("player_ids", [])
    total_slots = team_count * players_per_team

    if len(player_ids) < total_slots:
        await interaction.followup.send(
            f"⚠️ {team_count} баг бүрдэхийн тулд нийт {total_slots} тоглогч бүртгэгдэх ёстой, одоогоор {len(player_ids)} байна."
        )
        return

    scores = load_scores()
    player_weights = {}

    for uid in player_ids:
        data = scores.get(str(uid), {})
        player_weights[uid] = tier_score(data)

    # 🧠 Хоёр хувилбараар баг хуваана
    snake = snake_teams(player_weights, team_count, players_per_team)
    greedy = greedy_teams(player_weights, team_count, players_per_team)

    snake_diff = total_weight_difference(snake, player_weights)
    greedy_diff = total_weight_difference(greedy, player_weights)

    if greedy_diff < snake_diff:
        best_teams = greedy
        strategy = "greedy"
    else:
        best_teams = snake
        strategy = "snake"

    # ✅ Баг, тохиргоо, session хадгална
    TEAM_SETUP["teams"] = best_teams
    TEAM_SETUP["team_count"] = team_count
    TEAM_SETUP["players_per_team"] = players_per_team
    TEAM_SETUP["strategy"] = strategy
    GAME_SESSION["last_win_time"] = datetime.now(timezone.utc)

    # 📝 Match log бүртгэнэ
    match_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "go_bot",
        "team_count": team_count,
        "players_per_team": players_per_team,
        "strategy": strategy,
        "teams": best_teams,
        "initiator": interaction.user.id
    }
    append_to_json_list(MATCH_LOG_FILE, match_data)

    # 📣 Багийн бүрэлдэхүүн харуулна
    guild = interaction.guild
    lines = []
    for i, team in enumerate(best_teams, start=1):
        names = [guild.get_member(uid).display_name for uid in team if guild.get_member(uid)]
        lines.append(f"**#{i}-р баг**: " + ", ".join(names))

    await interaction.followup.send(
        f"✅ `{strategy}` хуваарилалт ашиглав (онооны зөрүү: `{min(snake_diff, greedy_diff)}`)\n\n" + "\n".join(lines)
    )

@bot.tree.command(name="go_gpt", description="GPT-ээр онооны баланс хийж баг хуваарилна")
async def go_gpt(interaction: discord.Interaction):
    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")

    if not (is_admin or is_initiator):
        await interaction.response.send_message("❌ Зөвхөн admin эсвэл тохиргоог эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    team_count = TEAM_SETUP["team_count"]
    players_per_team = TEAM_SETUP["players_per_team"]
    player_ids = TEAM_SETUP["player_ids"]
    scores = load_scores()

    total_slots = team_count * players_per_team
    player_scores = []

    for uid in player_ids:
        data = scores.get(str(uid), {})
        power = tier_score(data)
        player_scores.append({"id": uid, "power": power})

    if len(player_scores) > total_slots:
        player_scores.sort(key=lambda x: x["power"], reverse=True)
        player_scores = player_scores[:total_slots]
        player_ids = [p["id"] for p in player_scores]

    try:
        teams = call_gpt_balance_api(team_count, players_per_team, player_ids, scores)
    except Exception as e:
        print("❌ GPT API error:", e)
        await interaction.followup.send(
            "⚠️ GPT-ээр баг хуваарилах үед алдаа гарлаа. Түр зуурын асуудал байж болзошгүй.\n"
            "⏳ Дараа дахин оролдоно уу эсвэл `/go_bot` командыг ашиглаарай."
        )
        return

    TEAM_SETUP["teams"] = teams
    GAME_SESSION["last_win_time"] = datetime.now(timezone.utc)

    used_ids = set(uid for team in teams for uid in team)
    team_emojis = ["🥇", "🥈", "🥉", "🎯", "🔥", "🚀", "🎮", "🛡️", "⚔️", "🧠"]

    lines = ["🤖 **ChatGPT-ээр тэнцвэржүүлсэн багууд:**"]
    for i, team in enumerate(teams):
        emoji = team_emojis[i % len(team_emojis)]
        total = sum(tier_score(scores.get(str(uid), {})) for uid in team)
        lines.append(f"\n{emoji} **Team {i + 1}** (нийт оноо: `{total}` 🧮):")
        for uid in team:
            score = tier_score(scores.get(str(uid), {}))
            lines.append(f"- <@{uid}> (оноо: {score})")

    left_out = [uid for uid in TEAM_SETUP["player_ids"] if uid not in used_ids]
    if left_out:
        mentions = "\n• ".join(f"<@{uid}>" for uid in left_out)
        lines.append(f"\n⚠️ **Дараах тоглогчид энэ удаад багт орсонгүй:**\n• {mentions}")

    await interaction.followup.send("\n".join(lines))




@bot.tree.command(name="set_match_result", description="Match бүртгэнэ, +1/-1 оноо, tier өөрчилнө")
@app_commands.describe(winner_teams="Ялсан багуудын дугаарууд (жишээ: 1 3)")
async def set_match_result(interaction: discord.Interaction, winner_teams: str):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    if not GAME_SESSION["active"] or not TEAM_SETUP.get("teams"):
        await interaction.followup.send("⚠️ Session идэвхгүй эсвэл багууд бүрдээгүй байна.", ephemeral=True)
        return

    try:
        win_indexes = [int(x.strip()) - 1 for x in winner_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Ялсан багуудын дугаарыг зөв оруулна уу (ж: 1 3)", ephemeral=True)
        return

    all_teams = TEAM_SETUP["teams"]
    if any(i < 0 or i >= len(all_teams) for i in win_indexes):
        await interaction.followup.send("⚠️ Ялсан багийн дугаар буруу байна.", ephemeral=True)
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i, team in enumerate(all_teams) if i not in win_indexes for uid in team]

    scores = load_scores()
    now = datetime.now(MN_TZ)
    guild = interaction.guild

    tier_list = list(TIER_WEIGHT.keys())

    def validate_tier(tier):
        return tier if tier in tier_list else "4-1"

    winner_details = [] 
    for uid in winners:
        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())
        old_score = data["score"]
        old_tier = data["tier"]
        data["tier"] = validate_tier(data.get("tier"))
        data["score"] += 1

        if data["score"] >= 5:
            try:
                cur_index = tier_list.index(data["tier"])
            except ValueError:
                data["tier"] = "4-1"
                cur_index = tier_list.index("4-1")
            if cur_index + 1 < len(tier_list):
                data["tier"] = tier_list[cur_index + 1]
            data["score"] = 0

        member = guild.get_member(uid)
        data["username"] = member.display_name if member else "Unknown"
        scores[uid_str] = data

        winner_details.append({
            "uid": uid,
            "username": data["username"],
            "team": next((i + 1 for i, team in enumerate(all_teams) if uid in team), None),
            "old_score": old_score,
            "new_score": data["score"],
            "old_tier": old_tier,
            "new_tier": data["tier"],
            "delta": +1
        })

    loser_details = []
    for uid in losers:
        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())
        old_score = data["score"]
        old_tier = data["tier"]
        data["tier"] = validate_tier(data.get("tier"))
        data["score"] -= 1

        if data["score"] <= -5:
            try:
                cur_index = tier_list.index(data["tier"])
            except ValueError:
                data["tier"] = "4-1"
                cur_index = tier_list.index("4-1")
            if cur_index - 1 >= 0:
                data["tier"] = tier_list[cur_index - 1]
            data["score"] = 0

        member = guild.get_member(uid)
        data["username"] = member.display_name if member else "Unknown"
        scores[uid_str] = data

        loser_details.append({
            "uid": uid,
            "username": data["username"],
            "team": next((i + 1 for i, team in enumerate(all_teams) if uid in team), None),
            "old_score": old_score,
            "new_score": data["score"],
            "old_tier": old_tier,
            "new_tier": data["tier"],
            "delta": -1
        })
    
    
    teams = TEAM_SETUP["teams"]  # ← энэ мөрийг заавал нэм
    append_match_log(teams, winners, interaction.user.id, mode="manual")
    update_player_stats(winners, losers)

    last_match = {
        "timestamp": now.isoformat(),
        "winner_team_indexes": win_indexes,
        "winners": winner_details,
        "losers": loser_details,
        "by": interaction.user.id,
        "by_username": interaction.user.display_name
    }
    
    save_last_match(winners, losers)

    GAME_SESSION["last_win_time"] = now

    uids = [u["uid"] for u in winner_details + loser_details]
    await update_nicknames_for_users(interaction.guild, uids)
    await interaction.followup.send(f"🏆 {winner_teams}-р баг(ууд) яллаа. Оноо, tier шинэчлэгдлээ.")

@bot.tree.command(name="set_match_result_fountain", description="Fountain match бүртгэнэ, +2/-2 оноо, tier өөрчилнө")
@app_commands.describe(winner_teams="Ялсан багуудын дугаарууд (жишээ: 1 3)")
async def set_match_result_fountain(interaction: discord.Interaction, winner_teams: str):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    if not GAME_SESSION["active"] or not TEAM_SETUP.get("teams"):
        await interaction.followup.send("⚠️ Session идэвхгүй эсвэл багууд бүрдээгүй байна.", ephemeral=True)
        return

    try:
        win_indexes = [int(x.strip()) - 1 for x in winner_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Ялсан багуудын дугаарыг зөв оруулна уу (ж: 1 3)", ephemeral=True)
        return

    all_teams = TEAM_SETUP["teams"]
    if any(i < 0 or i >= len(all_teams) for i in win_indexes):
        await interaction.followup.send("⚠️ Ялсан багийн дугаар буруу байна.", ephemeral=True)
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i, team in enumerate(all_teams) if i not in win_indexes for uid in team]

    scores = load_scores()
    now = datetime.now(MN_TZ)
    guild = interaction.guild

    tier_list = list(TIER_WEIGHT.keys())

    def validate_tier(tier):
        return tier if tier in tier_list else "4-1"

    winner_details = []
    for uid in winners:
        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())
        old_score = data["score"]
        old_tier = data["tier"]
        data["tier"] = validate_tier(data.get("tier"))
        data["score"] += 2

        if data["score"] >= 5:
            try:
                cur_index = tier_list.index(data["tier"])
            except ValueError:
                data["tier"] = "4-1"
                cur_index = tier_list.index("4-1")
            if cur_index + 1 < len(tier_list):
                data["tier"] = tier_list[cur_index + 1]
            data["score"] = 0

        member = guild.get_member(uid)
        data["username"] = member.display_name if member else "Unknown"
        scores[uid_str] = data

        winner_details.append({
            "uid": uid,
            "username": data["username"],
            "team": next((i + 1 for i, team in enumerate(all_teams) if uid in team), None),
            "old_score": old_score,
            "new_score": data["score"],
            "old_tier": old_tier,
            "new_tier": data["tier"],
            "delta": +2
        })

    loser_details = []
    for uid in losers:
        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())
        old_score = data["score"]
        old_tier = data["tier"]
        data["tier"] = validate_tier(data.get("tier"))
        data["score"] -= 2

        if data["score"] <= -5:
            try:
                cur_index = tier_list.index(data["tier"])
            except ValueError:
                data["tier"] = "4-1"
                cur_index = tier_list.index("4-1")
            if cur_index - 1 >= 0:
                data["tier"] = tier_list[cur_index - 1]
            data["score"] = 0

        member = guild.get_member(uid)
        data["username"] = member.display_name if member else "Unknown"
        scores[uid_str] = data

        loser_details.append({
            "uid": uid,
            "username": data["username"],
            "team": next((i + 1 for i, team in enumerate(all_teams) if uid in team), None),
            "old_score": old_score,
            "new_score": data["score"],
            "old_tier": old_tier,
            "new_tier": data["tier"],
            "delta": -2
        })

    teams = TEAM_SETUP["teams"]  # ← энэ мөрийг заавал нэм
    append_match_log(teams, winners, interaction.user.id, mode="manual")
    update_player_stats(winners, losers)

    last_match = {
        "timestamp": now.isoformat(),
        "winner_team_indexes": win_indexes,
        "winners": winner_details,
        "losers": loser_details,
        "by": interaction.user.id,
        "by_username": interaction.user.display_name
    }
    save_last_match(winners, losers)
    
    GAME_SESSION["last_win_time"] = now
    uids = [u["uid"] for u in winner_details + loser_details]
    await update_nicknames_for_users(interaction.guild, uids)
    await interaction.followup.send(f"💦 {winner_teams}-р баг(ууд) Fountain ялалт авлаа. Оноо, tier шинэчлэгдлээ.")

@bot.tree.command(name="undo_last_match", description="Сүүлд хийсэн match-ийн оноог буцаана")
async def undo_last_match(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        print("❌ Interaction already responded.")
        return

    # ✅ Эрх шалгах
    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    # 📦 last_match.json унших
    if not os.path.exists(LAST_FILE):
        await interaction.followup.send("⚠️ Сүүлд бүртгэсэн match олдсонгүй.", ephemeral=True)
        return

    last = load_json(LAST_FILE)
    winners = last.get("winners", [])
    losers = last.get("losers", [])

    scores = load_scores()
    changed_ids = []
    guild = interaction.guild

    for uid in winners:
        uid_str = str(uid)
        data = scores.get(uid_str)
        if data:
            data["score"] -= 1
            if data["score"] < -5:
                data["tier"] = demote_tier(data["tier"])
                data["score"] = 0
            scores[uid_str] = data
            changed_ids.append(uid)

    for uid in losers:
        uid_str = str(uid)
        data = scores.get(uid_str)
        if data:
            data["score"] += 1
            if data["score"] > 5:
                data["tier"] = promote_tier(data["tier"])
                data["score"] = 0
            scores[uid_str] = data
            changed_ids.append(uid)

    # 🧠 Undo статистик буцаана
    update_player_stats(winners, losers, undo=True)

    # 💾 Оноо хадгалах
    save_json(SCORE_FILE, scores)

    # 📝 Log бичих
    log_score_transaction(
        action="undo",
        winners=winners,
        losers=losers,
        initiator_id=interaction.user.id,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    # 🧹 Сүүлчийн match бүртгэл цэвэрлэнэ
    clear_last_match()

        # 📣 Хариу илгээнэ
    win_mentions = " ".join(f"<@{uid}>" for uid in winners)
    lose_mentions = " ".join(f"<@{uid}>" for uid in losers)
    uids = winners + losers
    await update_nicknames_for_users(interaction.guild, uids)
    await interaction.followup.send(
        f"♻️ Match буцаагдлаа!\n"
        f"🏆 Winner-ууд: {win_mentions}\n"
        f"💀 Loser-ууд: {lose_mentions}"
    )

@bot.tree.command(name="my_score", description="Таны оноо болон tier-г харуулна")
async def my_score(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    scores = load_scores()
    data = scores.get(uid)

    if not data:
        await interaction.response.send_message("⚠️ Таны оноо бүртгэлгүй байна.", ephemeral=True)
        return

    tier = data.get("tier", "?")
    score = data.get("score", 0)
    username = data.get("username") or interaction.user.display_name

    await interaction.response.send_message(
        f"🏅 {username}:\n"
        f"Tier: **{tier}**\n"
        f"Score: **{score}**",
        ephemeral=True
    )

@bot.tree.command(name="user_score", description="Бусад тоглогчийн оноо болон tier-г харуулна")
@app_commands.describe(user="Оноог нь харах discord хэрэглэгч")
async def user_score(interaction: discord.Interaction, user: discord.Member):
    uid = str(user.id)
    scores = load_scores()
    data = scores.get(uid)

    if not data:
        await interaction.response.send_message(f"⚠️ {user.display_name} оноо бүртгэлгүй байна.", ephemeral=True)
        return

    tier = data.get("tier", "?")
    score = data.get("score", 0)
    username = data.get("username") or user.display_name

    await interaction.response.send_message(
        f"🏅 {username}:\n"
        f"Tier: **{tier}**\n"
        f"Score: **{score}**",
        ephemeral=True
    )

@bot.tree.command(name="player_stats", description="Таны нийт win/loss статистик")
async def player_stats(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    stats = load_json(PLAYER_STATS_FILE)
    data = stats.get(uid)

    if not data:
        await interaction.response.send_message("⚠️ Таны статистик бүртгэлгүй байна.", ephemeral=True)
        return

    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses
    win_rate = (wins / total) * 100 if total > 0 else 0.0

    username = interaction.user.display_name

    await interaction.response.send_message(
        f"📊 **{username} статистик**\n"
        f"🏆 Ялалт: `{wins}` тоглолт\n"
        f"💀 Ялагдал: `{losses}` тоглолт\n"
        f"📊 Total: `{total}` тоглолт\n"
        f"🔥 Win rate: `{win_rate:.1f}%`",
        ephemeral=True
    )

@bot.tree.command(name="set_tier", description="Админ: тоглогчийн tier болон оноог гар аргаар тохируулна")
@app_commands.describe(
    user="Хэрэглэгчийг заана (@mention)",
    tier="Шинэ tier (ж: 3-2)",
    score="Оноо (default: 0)"
)
async def set_tier(interaction: discord.Interaction, user: discord.Member, tier: str, score: int = 0):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ тохируулж чадна.", ephemeral=True)
        return

    scores = load_scores()
    uid = str(user.id)
    data = scores.get(uid, get_default_tier())

    tier_list = list(TIER_WEIGHT.keys())
    if tier not in tier_list:
        await interaction.response.send_message("⚠️ Tier утга буруу байна.", ephemeral=True)
        return

    data["tier"] = tier
    data["score"] = score
    data["username"] = user.display_name

    scores[uid] = data
    save_json(SCORE_FILE, scores)

    await update_nicknames_for_users(interaction.guild, [user.id])
    await interaction.response.send_message(
        f"✅ {user.display_name}-ийн tier **{tier}**, score **{score}** болж шинэчлэгдлээ.", ephemeral=True
    )

@bot.tree.command(name="add_score", description="Админ: тоглогчид оноо нэмэх эсвэл хасах")
@app_commands.describe(
    user="Хэрэглэгчийг заана (@mention)",
    points="Нэмэх оноо (эсвэл хасах, default: 1)"
)
async def add_score(interaction: discord.Interaction, user: discord.Member, points: int = 1):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэж чадна.", ephemeral=True)
        return

    scores = load_scores()
    uid = str(user.id)
    data = scores.get(uid, get_default_tier())

    tier_list = list(TIER_WEIGHT.keys())
    old_score = data.get("score", 0)
    old_tier = data.get("tier", "4-1")
    data["tier"] = old_tier if old_tier in tier_list else "4-1"

    data["score"] += points
    cur_index = tier_list.index(data["tier"])

    if data["score"] >= 5 and cur_index + 1 < len(tier_list):
        data["tier"] = tier_list[cur_index + 1]
        data["score"] = 0
    elif data["score"] <= -5 and cur_index - 1 >= 0:
        data["tier"] = tier_list[cur_index - 1]
        data["score"] = 0

    data["username"] = user.display_name
    scores[uid] = data
    save_json(SCORE_FILE, scores)

    await update_nicknames_for_users(interaction.guild, [user.id])
    await interaction.response.send_message(
        f"✅ {user.display_name}-ийн оноо {points:+} болж, tier: **{data['tier']}**, score: **{data['score']}** боллоо.", ephemeral=True
    )

@bot.tree.command(name="add_donator", description="Админ: тоглогчийг donator болгоно")
@app_commands.describe(
    member="Donator болгох хэрэглэгч",
    mnt="Хандивласан мөнгө (₮)"
)
async def add_donator(interaction: discord.Interaction, member: discord.Member, mnt: int):
    # ✅ Админ шалгах
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Энэ командыг зөвхөн админ хэрэглэгч ажиллуулж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        print("❌ Interaction-д аль хэдийн хариулсан байна.")
        return

    # ✅ Donator мэдээллийг хадгалах
    donors = load_donators()
    uid = str(member.id)
    now = datetime.now(timezone.utc).isoformat()

    if uid not in donors:
        donors[uid] = {
            "total_mnt": mnt,
            "last_donated": now
        }
    else:
        donors[uid]["total_mnt"] += mnt
        donors[uid]["last_donated"] = now

    save_donators(donors)

    # ✅ Nickname-г update_nicknames_for_users ашиглан цэвэрхэн өөрчилнө
    await update_nicknames_for_users(interaction.guild, [member.id])

    total_mnt = donors[uid]["total_mnt"]
    await update_nicknames_for_users(interaction.guild, [member.id])
    await interaction.followup.send(
        f"🎉 {member.mention} хэрэглэгчийг Donator болголоо! (нийт {total_mnt:,}₮)"
    )

@bot.tree.command(name="donator_list", description="Donator хэрэглэгчдийн жагсаалт")
async def donator_list(interaction: discord.Interaction):
    # ✅ Эхлээд admin шалгана
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Энэ командыг зөвхөн админ хэрэглэгч ашиглаж болно.",
            ephemeral=True
        )
        return

    # ✅ дараа нь interaction-г defer хийнэ
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        print("❌ Interaction-д аль хэдийн хариулсан байна.")
        return

    donors = load_donators()
    if not donors:
        await interaction.followup.send("📭 Donator бүртгэл алга байна.")
        return

    scores = load_scores()
    msg = "💖 **Donators:**\n"
    sorted_donors = sorted(donors.items(), key=lambda x: x[1].get("total_mnt", 0), reverse=True)

    for uid, data in sorted_donors:
        member = interaction.guild.get_member(int(uid))
        if member:
            emoji = get_donator_emoji(data)
            total = data.get("total_mnt", 0)
            tier = scores.get(uid, {}).get("tier", "4-1")

            display_name = member.display_name
            for prefix in TIER_ORDER:
                if display_name.startswith(f"{prefix} |"):
                    display_name = display_name[len(prefix) + 2:].strip()
                    break

            display = f"{emoji} {tier} | {display_name}" if emoji else f"{tier} | {display_name}"
            msg += f"{display} — {total:,}₮\n"


    await interaction.followup.send(msg)

@bot.tree.command(name="help_info", description="Bot-ын танилцуулга (readme.md файлыг харуулна)")
async def help_info(interaction: discord.Interaction):
    try:
        with open("./Info/Readme.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        await interaction.response.send_message("⚠️ `Readme.md` файл олдсонгүй.", ephemeral=True)
        return

    if len(content) > 1900:
        content = content[:1900] + "\n...\n(үргэлжлэлтэй)"

    await interaction.response.send_message(
        f"📘 **RZR Bot Танилцуулга**\n```markdown\n{content}\n```", ephemeral=True
    )

@bot.tree.command(name="help_commands", description="Бүх командын тайлбар жагсаалт")
async def help_commands(interaction: discord.Interaction):
    try:
        with open("./Info/Commands_alt.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        await interaction.response.send_message("⚠️ `Commands.md` файл олдсонгүй.", ephemeral=True)
        return

    if len(content) > 1900:
        content = content[:1900] + "\n...\n(үргэлжлэлтэй)"

    await interaction.response.send_message(
        f"📒 **RZR Bot Коммандууд**\n```markdown\n{content}\n```", ephemeral=True
    )

@bot.tree.command(name="match_history", description="Сүүлийн 5 match-ийн мэдээлэл")
async def match_history(interaction: discord.Interaction):
    try:
        with open(MATCH_LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await interaction.response.send_message("⚠️ Match лог олдсонгүй.", ephemeral=True)
        return

    if not logs:
        await interaction.response.send_message("⚠️ Match бүртгэл хоосон байна.", ephemeral=True)
        return

    latest = logs[-5:][::-1]
    blocks = []

    for i, match in enumerate(latest, 1):
        time = match.get("timestamp", "")[:16].replace("T", " ")
        mode = match.get("mode", "manual")
        teams = match.get("teams", [])
        winners = set(match.get("winner_team", []))

        lines = [f"**#{i}.** `{time}` | 🎯 `{mode}`"]
        for idx, team in enumerate(teams, 1):
            tags = " ".join([f"<@{uid}>" for uid in team])
            if set(team) == winners:
                lines.append(f"🏆 **Team {idx}:** {tags}")
            else:
                lines.append(f"💀 Team {idx}: {tags}")
        blocks.append("\n".join(lines))

    msg = "\n\n".join(blocks)
    await interaction.response.send_message(f"📜 **Сүүлийн 5 Match:**\n{msg}", ephemeral=True)

@bot.tree.command(name="backup_now", description="Админ: GitHub руу гараар backup хийнэ")
async def backup_now(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    try:
        file_list = [
            SCORE_FILE,          # data/scores.json
            MATCH_LOG_FILE,            # data/match_log.json
            LAST_FILE,           # data/last_match.json
            SHIELD_FILE,         # data/donate_shields.json
            DONATOR_FILE,        # data/donators.json
            SCORE_LOG_FILE,      # data/score_log.jsonl
            PLAYER_STATS_FILE    # data/player_stats.json
        ]
        commit_to_github_multi(file_list, "🖐 Гар ажиллагаатай GitHub backup")
        await interaction.followup.send("✅ Backup амжилттай хийгдлээ.")
    except Exception as e:
        print("❌ backup_now алдаа:", e)
        await interaction.followup.send(f"❌ Backup хийхэд алдаа гарлаа: {e}")


# 🔄 Bot ажиллах үед
@bot.event
async def on_ready():
    print(f"🤖 RZR Bot v6.0 ажиллаж байна: {bot.user}")
    print("📁 Working directory:", os.getcwd())

    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"✅ Synced: {guild.name} ({guild.id})")
    asyncio.create_task(session_timeout_checker())   # ⏱ 24 цагийн session шалгагч
    asyncio.create_task(github_auto_commit())        # ⏱ 60 минутын GitHub backup task

# 🟢 Run bot
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN орчны хувьсагч тохируулаагүй байна.")
