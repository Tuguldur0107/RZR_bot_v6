import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
import time
import json
from datetime import datetime, timezone, timedelta
import pytz
import openai
import requests
from keep_alive import keep_alive
from dotenv import load_dotenv
import base64
from github_commit import commit_to_github

load_dotenv()
print("🧪 ENV LOADED", os.getenv("GUILD_ID")) 

MN_TZ = pytz.timezone("Asia/Ulaanbaatar")

# ⏱ Монголын цаг
now_mn = datetime.now(MN_TZ)

# 🌐 Token-уудыг ENV-оос ачаална
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None



# 📁 Файлын замууд (Render Volume: /mnt/data биш харин local path)
BASE_DIR = "/data"

SCORE_FILE = f"{BASE_DIR}/scores.json"
MATCH_LOG_FILE = f"{BASE_DIR}/match_log.json"
LAST_FILE = f"{BASE_DIR}/last_match.json"
SHIELD_FILE = f"{BASE_DIR}/donate_shields.json"
DONATOR_FILE = f"{BASE_DIR}/donators.json"
SCORE_LOG_FILE = f"{BASE_DIR}/score_log.jsonl"
PLAYER_STATS_FILE = f"{BASE_DIR}/player_stats.json"
SESSION_FILE = f"{BASE_DIR}/session.json"

INFO_DIR = "Info"

COMMANDS_FILE = f"{INFO_DIR}/commands.md"
HELP_FILE = f"{INFO_DIR}/Readme.txt"


# 🎮 Session төлөв
GAME_SESSION = {
    "active": False,
    "start_time": None,
    "last_win_time": None
}
# 🧩 Баг бүрдүүлэлтийн төлөв
TEAM_SETUP = {
    "initiator_id": None,
    "team_count": 2,
    "players_per_team": 5,
    "player_ids": [],
    "teams": [],
    "strategy": ""
}
SESSION_FILE = f"{BASE_DIR}/session.json"


def save_session():
    session_data = {
        "active": GAME_SESSION["active"],
        "start_time": GAME_SESSION["start_time"].isoformat() if GAME_SESSION["start_time"] else None,
        "last_win_time": GAME_SESSION["last_win_time"].isoformat() if GAME_SESSION["last_win_time"] else None,
        "initiator_id": TEAM_SETUP.get("initiator_id"),
        "team_count": TEAM_SETUP.get("team_count"),
        "players_per_team": TEAM_SETUP.get("players_per_team"),
        "player_ids": TEAM_SETUP.get("player_ids"),
        "teams": TEAM_SETUP.get("teams"),
        "strategy": TEAM_SETUP.get("strategy", "")
    }
    save_json(SESSION_FILE, session_data)

def load_session():
    if not os.path.exists(SESSION_FILE):
        return

    data = load_json(SESSION_FILE)
    GAME_SESSION["active"] = data.get("active", False)
    GAME_SESSION["start_time"] = datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None
    GAME_SESSION["last_win_time"] = datetime.fromisoformat(data["last_win_time"]) if data.get("last_win_time") else None

    TEAM_SETUP["initiator_id"] = data.get("initiator_id")
    TEAM_SETUP["team_count"] = data.get("team_count", 2)
    TEAM_SETUP["players_per_team"] = data.get("players_per_team", 5)
    TEAM_SETUP["player_ids"] = data.get("player_ids", [])
    TEAM_SETUP["teams"] = data.get("teams", [])
    TEAM_SETUP["strategy"] = data.get("strategy", "")


# 1. Flask server thread-ээр ажиллуулна
def keep_alive():
    from flask import Flask
    from threading import Thread

    app = Flask('')

    @app.route('/')
    def home():
        return "✅ I'm alive"

    def run():
        app.run(host='0.0.0.0', port=8080)

    t = Thread(target=run)
    t.start()

def copy_scores_from_github():
    url = "https://raw.githubusercontent.com/Tuguldur0107/RZR_bot_v6/main/data/scores.json"
    local_path = SCORE_FILE  # ✅ Render volume руу хадгална

    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text)
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("✅ GitHub-с scores.json бүрэн хууллаа.")
        else:
            print(f"❌ GitHub-с татаж чадсангүй: {r.status_code}")
    except Exception as e:
        print("❌ GitHub fetch алдаа:", e)

def copy_donators_from_github():
    url = "https://raw.githubusercontent.com/Tuguldur0107/RZR_bot_v6/main/data/donators.json"
    local_path = DONATOR_FILE  # ✅ Volume дээрх замыг ашиглана

    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = json.loads(r.text)  # JSON-ийн бүтэн эсэхийг шалгах
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print("✅ GitHub-с donators.json бүрэн хууллаа.")
        else:
            print(f"❌ GitHub-с татаж чадсангүй: {r.status_code}")
    except Exception as e:
        print("❌ GitHub fetch алдаа:", e)


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

def commit_to_github_multi(file_list, message="update"):
    import base64
    import requests
    import os
    import json

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

    # 1. Эхлээд тухайн branch дээрх сүүлийн commit-аас sha авч байна
    url = f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}"
    res = requests.get(url, headers=headers)
    if not res.ok:
        print(f"❌ GitHub branch sha авахад алдаа: {res.status_code}")
        return
    branch_sha = res.json()["object"]["sha"]

    # 2. commit-аас tree авах
    url = f"https://api.github.com/repos/{repo}/git/commits/{branch_sha}"
    res = requests.get(url, headers=headers)
    if not res.ok:
        print(f"❌ GitHub commit tree авахад алдаа: {res.status_code}")
        return
    base_tree_sha = res.json()["tree"]["sha"]

    # 3. commit-д оруулах файлуудыг tree бүрдүүлэлтэнд нэмэх
    tree_items = []
    for filepath in file_list:
        try:
            with open(filepath, "rb") as f:
                content = f.read()
                encoded_content = base64.b64encode(content).decode("utf-8")
        except Exception as e:
            print(f"⚠️ {filepath} файл уншихад алдаа гарлаа: {e}")
            continue

        github_path = filepath.replace("\\", "/")
        if "/data/" in github_path:
            github_path = "data/" + github_path.split("/data/")[-1]
        else:
            github_path = os.path.basename(filepath)

        tree_items.append({
            "path": github_path,
            "mode": "100644",
            "type": "blob",
            "content": content.decode(errors="ignore")  # GitHub-д text content оруулна
        })

    # 4. Шинэ tree үүсгэх
    url = f"https://api.github.com/repos/{repo}/git/trees"
    data = {
        "base_tree": base_tree_sha,
        "tree": tree_items
    }
    res = requests.post(url, headers=headers, json=data)
    if not res.ok:
        print(f"❌ GitHub tree үүсгэхэд алдаа: {res.status_code} {res.text}")
        return
    new_tree_sha = res.json()["sha"]

    # 5. Шинэ commit үүсгэх
    url = f"https://api.github.com/repos/{repo}/git/commits"
    data = {
        "message": message,
        "tree": new_tree_sha,
        "parents": [branch_sha]
    }
    res = requests.post(url, headers=headers, json=data)
    if not res.ok:
        print(f"❌ GitHub commit үүсгэхэд алдаа: {res.status_code} {res.text}")
        return
    new_commit_sha = res.json()["sha"]

    # 6. Branch-ийг шинэ commit руу шилжүүлэх
    url = f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}"
    data = {
        "sha": new_commit_sha
    }
    res = requests.patch(url, headers=headers, json=data)
    if not res.ok:
        print(f"❌ GitHub branch update алдаа: {res.status_code} {res.text}")
        return

    print(f"✅ {len(tree_items)} файлыг GitHub руу багцлаад commit хийлээ.")


# Файлын хамгийн сүүлд өөрчлөгдсөн хугацааг хадгалах dictionary
async def github_auto_commit():
    await bot.wait_until_ready()
    await asyncio.sleep(3600)
    while not bot.is_closed():
        try:
            from github_commit import commit_to_github

            commit_to_github("data/scores.json", "auto: scores.json")
            commit_to_github("data/donators.json", "auto: donators.json")
            commit_to_github("data/score_log.jsonl", "auto: score_log.jsonl")
            commit_to_github("data/match_log.json", "auto: match_log.json")
            commit_to_github("data/last_match.json", "auto: last_match.json")
            commit_to_github("data/donate_shields.json", "auto: donate_shields.json")
            commit_to_github("data/player_stats.json", "auto: player_stats.json")

            print("✅ GitHub-д 60 минутаар автоматаар backup хийгдлээ.")
        except Exception as e:
            print("❌ GitHub auto commit алдаа:", e)

        await asyncio.sleep(3600)  # 60 минут


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
    tier = data.get("tier", "4-1")
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
            print(f"⚠️ Member {user_id} get_member олдсонгүй.")
            continue

        score_data = scores.get(str(user_id))
        if not score_data:
            print(f"⚠️ Member {user_id} score_data олдсонгүй.")
            continue

        tier = score_data.get("tier", "4-1")
        donor_data = donors.get(str(user_id), {})
        emoji = get_donator_emoji(donor_data)

        base_nick = clean_nickname(member.display_name)
        prefix = f"{emoji} {tier}" if emoji else tier
        new_nick = f"{prefix} | {base_nick}"

        if member.nick == new_nick:
            print(f"ℹ️ {member.display_name} nickname аль хэдийн тохирсон.")
            continue

        try:
            await member.edit(nick=new_nick)
            print(f"✅ {member.display_name} nickname шинэчлэгдлээ → {new_nick}")
        except discord.Forbidden:
            print(f"⛔️ {member.display_name} nickname-г өөрчилж чадсангүй. Permission асуудал байж магадгүй.")
        except Exception as e:
            print(f"⚠️ {member.display_name} nickname-д алдаа гарлаа: {e}")

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
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You're a helpful assistant that balances teams."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1024,
            seed=42,
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

# ⚙️ Discord intents
intents = discord.Intents.all()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

def remove_last_match_log():
    if not os.path.exists(MATCH_LOG_FILE):
        return

    try:
        matches = load_json(MATCH_LOG_FILE)
        if matches:
            matches.pop()  # хамгийн сүүлийн match-ийг устгана
            save_json(MATCH_LOG_FILE, matches)
    except Exception as e:
        print(f"❌ Match log устгах үед алдаа гарлаа: {e}")

@bot.tree.command(name="ping", description="Ботын latency-г шалгана")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! Latency: {latency_ms}ms", ephemeral=True)

@bot.tree.command(name="start_match", description="Session эхлүүлнэ, багийн тоо болон тоглогчийн тоог тохируулна")
@app_commands.describe(team_count="Хэдэн багтай байх вэ", players_per_team="Нэг багт хэдэн хүн байх вэ")
async def start_match(interaction: discord.Interaction, team_count: int, players_per_team: int):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # ✅ Хуучин session байсан бол хаана
    if GAME_SESSION["active"]:
        GAME_SESSION["active"] = False
        GAME_SESSION["start_time"] = None
        GAME_SESSION["last_win_time"] = None

    # 🧠 Шинэ session эхлүүлнэ
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

    await interaction.followup.send(
        f"🟢 {team_count} багтай, {players_per_team} хүнтэй Session эхэллээ. `addme` коммандаар тоглогчид бүртгүүлнэ үү."
    )
    
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()

@bot.tree.command(name="addme", description="Тоглогч өөрийгөө бүртгүүлнэ")
async def addme(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
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

    await interaction.followup.send(
        f"✅ {interaction.user.mention} бүртгүүллээ.\nНийт бүртгэгдсэн: {len(TEAM_SETUP['player_ids'])}"
    )

@bot.tree.command(name="show_added_players", description="Бүртгэгдсэн тоглогчдыг харуулна")
async def show_added_players(interaction: discord.Interaction):
    try:
        await interaction.response.defer()
    except discord.errors.InteractionResponded:
        return

    if not TEAM_SETUP["player_ids"]:
        await interaction.followup.send("📭 Одоогоор бүртгэгдсэн тоглогч алга.")
        return

    guild = interaction.guild
    mentions = [guild.get_member(uid).mention for uid in TEAM_SETUP["player_ids"] if guild.get_member(uid)]
    mention_text = "\n".join(mentions)

    await interaction.followup.send(f"📋 Бүртгэгдсэн тоглогчид ({len(mentions)}):\n{mention_text}")

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
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()

@bot.tree.command(name="go_bot", description="Онооны дагуу тэнцвэртэй баг хуваарилна")
async def go_bot(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    if not GAME_SESSION["active"]:
        await interaction.followup.send("⚠️ Session идэвхгүй байна.", ephemeral=True)
        return

    team_count = TEAM_SETUP["team_count"]
    players_per_team = TEAM_SETUP["players_per_team"]
    total_slots = team_count * players_per_team
    player_ids = TEAM_SETUP["player_ids"]

    if not player_ids:
        await interaction.followup.send("⚠️ Бүртгэгдсэн тоглогч алга байна.", ephemeral=True)
        return

    scores = load_scores()
    weights_all = {
        uid: tier_score(scores.get(str(uid), {}))
        for uid in player_ids
    }

    # Оноогоор эрэмбэлнэ
    sorted_players = sorted(weights_all.items(), key=lambda x: x[1], reverse=True)
    trimmed_players = sorted_players[:total_slots]
    player_weights = dict(trimmed_players)
    left_out_players = sorted_players[total_slots:]

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

    TEAM_SETUP["teams"] = best_teams
    TEAM_SETUP["strategy"] = strategy
    GAME_SESSION["last_win_time"] = datetime.now(timezone.utc)

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
    save_session()

    guild = interaction.guild
    lines = []
    for i, team in enumerate(best_teams, start=1):
        team_total = sum(player_weights.get(uid, 0) for uid in team)
        leader_uid = max(team, key=lambda uid: player_weights.get(uid, 0))
        leader_name = guild.get_member(leader_uid).display_name if guild.get_member(leader_uid) else str(leader_uid)

        lines.append(f"# {i}-р баг (нийт оноо: {team_total})\n")
        for uid in team:
            member = guild.get_member(uid)
            name = member.display_name if member else str(uid)
            score = player_weights.get(uid, 0)
            if uid == leader_uid:
                lines.append(f"{name} ({score}) 😎 Team Leader\n")
            else:
                lines.append(f"{name} ({score})\n")
        lines.append("\n")

    if left_out_players:
        mentions = "\n• ".join(f"<@{uid}>" for uid, _ in left_out_players)
        lines.append(f"⚠️ **Дараах тоглогчид энэ удаад багт орсонгүй:**\n• {mentions}")

    await interaction.followup.send(
        f"✅ `{strategy}` хуваарилалт ашиглав (онооны зөрүү: `{min(snake_diff, greedy_diff)}`)\n\n" + "".join(lines)
    )
    await interaction.followup.send("✅ Match бүртгэгдлээ.")

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

    if not GAME_SESSION["active"]:
        await interaction.followup.send("⚠️ Session идэвхгүй байна.", ephemeral=True)
        return

    team_count = TEAM_SETUP["team_count"]
    players_per_team = TEAM_SETUP["players_per_team"]
    player_ids = TEAM_SETUP["player_ids"]
    total_slots = team_count * players_per_team
    scores = load_scores()

    all_scores = []
    for uid in player_ids:
        power = tier_score(scores.get(str(uid), {}))
        all_scores.append({"id": uid, "power": power})

    sorted_players = sorted(all_scores, key=lambda x: x["power"], reverse=True)
    selected_players = sorted_players[:total_slots]
    left_out_players = sorted_players[total_slots:]

    score_map = {p["id"]: p["power"] for p in selected_players}

    try:
        teams = call_gpt_balance_api(team_count, players_per_team, selected_players)
    except Exception as e:
        print("❌ GPT API error:", e)
        await interaction.followup.send(
            "⚠️ GPT-ээр баг хуваарилах үед алдаа гарлаа. Түр зуурын асуудал байж болзошгүй.\n"
            "⏳ Дараа дахин оролдоно уу эсвэл `/go_bot` командыг ашиглаарай."
        )
        return

    TEAM_SETUP["teams"] = teams
    TEAM_SETUP["strategy"] = "gpt"
    GAME_SESSION["last_win_time"] = datetime.now(timezone.utc)

    match_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "go_gpt",
        "team_count": team_count,
        "players_per_team": players_per_team,
        "strategy": "gpt",
        "teams": teams,
        "initiator": interaction.user.id
    }
    append_to_json_list(MATCH_LOG_FILE, match_data)

    guild = interaction.guild
    team_emojis = ["🥇", "🥈", "🥉", "🎯", "🔥", "🚀", "🎮", "🛡️", "⚔️", "🧠"]
    used_ids = set(uid for team in teams for uid in team)

    lines = ["🤖 **ChatGPT-ээр тэнцвэржүүлсэн багууд:**"]
    for i, team in enumerate(teams):
        emoji = team_emojis[i % len(team_emojis)]
        team_total = sum(score_map.get(uid, 0) for uid in team)
        leader_uid = max(team, key=lambda uid: score_map.get(uid, 0))
        leader_name = guild.get_member(leader_uid).display_name if guild.get_member(leader_uid) else str(leader_uid)

        lines.append(f"\n{emoji} **#{i+1}-р баг** (нийт оноо: {team_total}) 😎\n")
        for uid in team:
            member = guild.get_member(uid)
            name = member.display_name if member else f"{uid}"
            weight = score_map.get(uid, 0)
            if uid == leader_uid:
                lines.append(f"{name} ({weight}) 😎 Team Leader\n")
            else:
                lines.append(f"{name} ({weight})\n")

    if left_out_players:
        mentions = "\n• ".join(f"<@{p['id']}>" for p in left_out_players)
        lines.append(f"\n⚠️ **Дараах тоглогчид энэ удаад багт орсонгүй:**\n• {mentions}")

    await interaction.followup.send("".join(lines))
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()

@bot.tree.command(name="set_match_result", description="Match бүртгэнэ, +1/-1 оноо, tier өөрчилнө")
@app_commands.describe(
    winner_teams="Ялсан багуудын дугаарууд (жишээ: 1 3)",
    loser_teams="Ялагдсан багуудын дугаарууд (жишээ: 2 4)"
)
async def set_match_result(interaction: discord.Interaction, winner_teams: str, loser_teams: str):
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
        lose_indexes = [int(x.strip()) - 1 for x in loser_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Багийн дугааруудыг зөв оруулна уу (ж: 1 3)", ephemeral=True)
        return

    all_teams = TEAM_SETUP["teams"]
    if any(i < 0 or i >= len(all_teams) for i in win_indexes + lose_indexes):
        await interaction.followup.send("⚠️ Багийн дугаар буруу байна.", ephemeral=True)
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i in lose_indexes for uid in all_teams[i]]

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
            cur_index = tier_list.index(data["tier"])
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
            cur_index = tier_list.index(data["tier"])
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

    save_json(SCORE_FILE, scores)

    log_score_transaction(
        action="set_match_result",
        winners=winners,
        losers=losers,
        initiator_id=interaction.user.id,
        timestamp=now.isoformat()
    )

    teams = TEAM_SETUP["teams"]
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

    win_str = " ".join(str(i + 1) for i in win_indexes)
    lose_str = " ".join(str(i + 1) for i in lose_indexes)
    lines = [f"🏆 {win_str}-р баг(ууд) ялж {lose_str}-р баг ялагдлаа. \\\nОноо, tier шинэчлэгдлээ.\n"]

    if winner_details:
        lines.append(f"\n\n✅ {win_str}-р багийн **ялагсан суперүүд:**")
        for p in winner_details:
            change = ""
            if p["old_tier"] != p["new_tier"]:
                if TIER_ORDER.index(p["new_tier"]) < TIER_ORDER.index(p["old_tier"]):
                    change = " ⬆"
                else:
                    change = " ⬇"
            lines.append(f"- <@{p['uid']}>: {p['old_score']} → {p['new_score']} (Tier: {p['old_tier']} → {p['new_tier']}){change}")

    if loser_details:
        lines.append(f"\n\n💀 {lose_str}-р багийн **ялагдагсан сугууд:**")
        for p in loser_details:
            change = ""
            if p["old_tier"] != p["new_tier"]:
                if TIER_ORDER.index(p["new_tier"]) < TIER_ORDER.index(p["old_tier"]):
                    change = " ⬆"
                else:
                    change = " ⬇"
            lines.append(f"- <@{p['uid']}>: {p['old_score']} → {p['new_score']} (Tier: {p['old_tier']} → {p['new_tier']}){change}")

    await interaction.followup.send("\n".join(lines))
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()
    
@bot.tree.command(name="set_match_result_fountain", description="Fountain match бүртгэнэ, +2/-2 оноо, tier өөрчилнө")
@app_commands.describe(
    winner_teams="Ялсан багуудын дугаарууд (жишээ: 1 3)",
    loser_teams="Ялагдсан багуудын дугаарууд (жишээ: 2 4)"
)
async def set_match_result_fountain(interaction: discord.Interaction, winner_teams: str, loser_teams: str):
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
        lose_indexes = [int(x.strip()) - 1 for x in loser_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Багийн дугааруудыг зөв оруулна уу (ж: 1 3)", ephemeral=True)
        return

    all_teams = TEAM_SETUP["teams"]
    if any(i < 0 or i >= len(all_teams) for i in win_indexes + lose_indexes):
        await interaction.followup.send("⚠️ Багийн дугаар буруу байна.", ephemeral=True)
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i in lose_indexes for uid in all_teams[i]]

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
            cur_index = tier_list.index(data["tier"])
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
            cur_index = tier_list.index(data["tier"])
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

    save_json(SCORE_FILE, scores)

    log_score_transaction(
        action="set_match_result_fountain",
        winners=winners,
        losers=losers,
        initiator_id=interaction.user.id,
        timestamp=now.isoformat()
    )

    append_match_log(all_teams, winners, interaction.user.id, mode="fountain")
    update_player_stats(winners, losers)
    save_last_match(winners, losers)
    GAME_SESSION["last_win_time"] = now

    uids = [u["uid"] for u in winner_details + loser_details]
    await update_nicknames_for_users(interaction.guild, uids)

    win_str = " ".join(str(i + 1) for i in win_indexes)
    lose_str = " ".join(str(i + 1) for i in lose_indexes)
    lines = [f"💦 {win_str}-р баг(ууд) Fountain ялж {lose_str}-р баг ялагдлаа. \\\nОноо, tier шинэчлэгдлээ.\n"]

    if winner_details:
        lines.append(f"\n\n✅ {win_str}-р багийн **ялагсан суперүүд:**")
        for p in winner_details:
            change = ""
            if p["old_tier"] != p["new_tier"]:
                if TIER_ORDER.index(p["new_tier"]) < TIER_ORDER.index(p["old_tier"]):
                    change = " ⬆"
                else:
                    change = " ⬇"
            lines.append(f"- <@{p['uid']}>: {p['old_score']} → {p['new_score']} (Tier: {p['old_tier']} → {p['new_tier']}){change}")

    if loser_details:
        lines.append(f"\n\n💀 {lose_str}-р багийн **ялагдагсан сугууд:**")
        for p in loser_details:
            change = ""
            if p["old_tier"] != p["new_tier"]:
                if TIER_ORDER.index(p["new_tier"]) < TIER_ORDER.index(p["old_tier"]):
                    change = " ⬆"
                else:
                    change = " ⬇"
            lines.append(f"- <@{p['uid']}>: {p['old_score']} → {p['new_score']} (Tier: {p['old_tier']} → {p['new_tier']}){change}")

    await interaction.followup.send("\n".join(lines))
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()

@bot.tree.command(name="undo_last_match", description="Сүүлд хийсэн match-ийн оноог буцаана")
async def undo_last_match(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        print("❌ Interaction already responded.")
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == TEAM_SETUP.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

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

    update_player_stats(winners, losers, undo=True)
    save_json(SCORE_FILE, scores)

    log_score_transaction(
        action="undo",
        winners=winners,
        losers=losers,
        initiator_id=interaction.user.id,
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    clear_last_match()
    remove_last_match_log()

    win_mentions = " ".join(f"<@{uid}>" for uid in winners)
    lose_mentions = " ".join(f"<@{uid}>" for uid in losers)
    uids = winners + losers
    await update_nicknames_for_users(interaction.guild, uids)
    await interaction.followup.send(
        f"♻️ Match буцаагдлаа!\n"
        f"🏆 Winner-ууд: {win_mentions}\n"
        f"💀 Loser-ууд: {lose_mentions}"
    )
    await interaction.followup.send("✅ Match бүртгэгдлээ.")
    save_session()

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

@bot.tree.command(name="add_score_test", description="Админ: тоглогчдод оноо нэмэх эсвэл хасах")
@app_commands.describe(
    mentions="Оноо өгөх тоглогчдыг mention хийнэ (@name @name...)",
    points="Нэмэх эсвэл хасах оноо (default: 1)"
)
async def add_score(interaction: discord.Interaction, mentions: str, points: int = 1):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # 👥 Mention-оос ID жагсаалт гаргаж авна
    user_ids = [int(word[2:-1].replace("!", "")) for word in mentions.split() if word.startswith("<@") and word.endswith(">")]

    if not user_ids:
        await interaction.followup.send("⚠️ Хэрэглэгчийн mention оруулна уу.")
        return

    scores = load_scores()
    updated = []

    for uid in user_ids:
        member = interaction.guild.get_member(uid)
        if not member:
            continue

        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())

        old_score = data.get("score", 0)
        old_tier = data.get("tier", "4-1")
        tier_list = list(TIER_WEIGHT.keys())

        data["tier"] = old_tier if old_tier in tier_list else "4-1"
        data["score"] += points
        cur_index = tier_list.index(data["tier"])

        if data["score"] >= 5 and cur_index + 1 < len(tier_list):
            data["tier"] = tier_list[cur_index + 1]
            data["score"] = 0
        elif data["score"] <= -5 and cur_index - 1 >= 0:
            data["tier"] = tier_list[cur_index - 1]
            data["score"] = 0

        data["username"] = member.display_name
        scores[uid_str] = data
        updated.append(uid)

        # 🧾 Онооны лог бүртгэнэ
        reason = f"add_score_by_{interaction.user.id}"
        log_score_transaction(uid_str, points, data["score"], data["tier"], reason=reason)

    save_json(SCORE_FILE, scores)
    await update_nicknames_for_users(interaction.guild, updated)

    mentions_text = ", ".join(f"<@{uid}>" for uid in updated)
    await interaction.followup.send(f"✅ Оноо {points:+} – {mentions_text}")



@bot.tree.command(name="add_score", description="Админ: тоглогчдод оноо нэмэх эсвэл хасах")
@app_commands.describe(
    mentions="Оноо өгөх тоглогчдыг mention хийнэ (@name @name...)",
    points="Нэмэх эсвэл хасах оноо (default: 1)"
)
async def add_score(interaction: discord.Interaction, mentions: str, points: int = 1):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # 👥 Mention-оос ID жагсаалт гаргаж авна
    user_ids = [int(word[2:-1].replace("!", "")) for word in mentions.split() if word.startswith("<@") and word.endswith(">")]

    if not user_ids:
        await interaction.followup.send("⚠️ Хэрэглэгчийн mention оруулна уу.")
        return

    scores = load_scores()
    updated = []

    for uid in user_ids:
        member = interaction.guild.get_member(uid)
        if not member:
            continue

        uid_str = str(uid)
        data = scores.get(uid_str, get_default_tier())

        old_score = data.get("score", 0)
        old_tier = data.get("tier", "4-1")
        tier_list = list(TIER_WEIGHT.keys())

        data["tier"] = old_tier if old_tier in tier_list else "4-1"
        data["score"] += points
        cur_index = tier_list.index(data["tier"])

        if data["score"] >= 5 and cur_index + 1 < len(tier_list):
            data["tier"] = tier_list[cur_index + 1]
            data["score"] = 0
        elif data["score"] <= -5 and cur_index - 1 >= 0:
            data["tier"] = tier_list[cur_index - 1]
            data["score"] = 0

        data["username"] = member.display_name
        scores[uid_str] = data
        updated.append(uid)

        # 🧾 Онооны лог бүртгэнэ
        reason = f"add_score_by_{interaction.user.id}"
        log_score_transaction(uid_str, points, data["score"], data["tier"], reason=reason)

    save_json(SCORE_FILE, scores)
    await update_nicknames_for_users(interaction.guild, updated)

    mentions_text = ", ".join(f"<@{uid}>" for uid in updated)
    await interaction.followup.send(f"✅ Оноо {points:+} – {mentions_text}")


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
            display_name = clean_nickname(member.display_name)

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

@bot.tree.command(name="whois", description="Mention хийсэн хэрэглэгчийн нэрийг харуулна")
@app_commands.describe(mention="Хэрэглэгчийн mention (@name) хэлбэрээр")
async def whois(interaction: discord.Interaction, mention: str):
    try:
        uid = int(mention.strip("<@!>"))
        member = await interaction.guild.fetch_member(uid)
        await interaction.response.send_message(f"🕵️‍♂️ Энэ ID: `{uid}` → {member.mention} / Нэр: `{member.display_name}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Олдсонгүй: {e}")

@bot.tree.command(name="debug_id", description="Таны Discord ID-г харуулна")
async def debug_id(interaction: discord.Interaction):
    await interaction.response.send_message(f"🆔 Таны Discord ID: `{interaction.user.id}`", ephemeral=True)

@bot.tree.command(name="resync", description="Админ: Slash командуудыг дахин sync хийнэ")
async def resync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ ажиллуулж чадна.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    try:
        synced = 0
        for guild in bot.guilds:
            await bot.tree.sync(guild=guild)
            synced += 1
        await interaction.followup.send(f"🔄 {synced} сервер дээр slash командууд дахин sync хийгдлээ.")
    except Exception as e:
        await interaction.followup.send(f"❌ Sync хийх үед алдаа гарлаа: {e}")


print(bot)  # bot объектийг print хий — id нь ямар байна?
# 🎯 1. event-үүд function-ий гадна байж таарна
@bot.event
async def on_ready():
    print("✅ on_ready ажиллалаа")
    print(f"🤖 RZR Bot ажиллаж байна: {bot.user}")
    print("📁 Working directory:", os.getcwd())

    print("🔄 Cleaning and syncing slash commands...")
    await bot.tree.sync()  # Global sync

    load_session()

    for guild in bot.guilds:
        await bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"✅ Slash commands synced: {guild.name} ({guild.id})")

    asyncio.create_task(session_timeout_checker())
    asyncio.create_task(github_auto_commit())

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    now = datetime.now(timezone.utc).isoformat()
    
    

    try:
        with open("last_message.json", "r") as f:
            last_seen = json.load(f)
    except FileNotFoundError:
        last_seen = {}

    last_seen[user_id] = now

    with open("last_message.json", "w") as f:
        json.dump(last_seen, f, indent=4)

    await bot.process_commands(message)
    


# 🎯 2. main() бол зөвхөн bot-г эхлүүлэх л үүрэгтэй байх ёстой
async def main():
    from keep_alive import keep_alive
    keep_alive()

    if not TOKEN:
        print("❌ DISCORD_TOKEN тохируулагдаагүй байна.")
        return

    print("🚀 Bot эхлэх гэж байна...")
    await bot.start(TOKEN)


# 🎯 3. run main
if __name__ == "__main__":
    asyncio.run(main())
