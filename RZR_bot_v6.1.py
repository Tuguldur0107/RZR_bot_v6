# 🌐 Built-in modules
import os
import json
import asyncio
import traceback
from datetime import datetime, timezone, timedelta

# 🌿 Third-party modules
import discord
from discord import app_commands, Embed
from discord.ext import commands
from dotenv import load_dotenv
import asyncpg
import openai

# 🗄️ Local modules
from database import (
    connect, pool, init_pool,

    # 🎯 Score & tier
    get_score, upsert_score, get_all_scores, get_default_tier,
    promote_tier, demote_tier, get_player_stats, update_player_stats,

    # 📊 Match
    save_last_match, get_last_match, insert_match, clear_last_match,

    # 🧾 Score log
    log_score_transaction,

    # 🛡 Session
    save_session_state, load_session_state, clear_session_state,

    # 💖 Donator
    get_all_donators, upsert_donator,

    # 🛡 Shields
    get_shields, upsert_shield
)



# 🌐 ENV
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY тохируулагдаагүй байна.")
openai.api_key = OPENAI_API_KEY
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None

# 🕰 Цагийн бүс
MN_TZ = timezone(timedelta(hours=8))

# 🔧 Discord intents
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# 🎮 Session + Team
# GAME_SESSION = {
#     "active": False,
#     "start_time": None,
#     "last_win_time": None
# }
# TEAM_SETUP = {
#     "initiator_id": None,
#     "team_count": 2,
#     "players_per_team": 5,
#     "player_ids": [],
#     "teams": [],
#     "changed_players": []
# }

# ⚙️ Tier config (1-1 → 5-5)
TIER_ORDER = [
    "5-5", "5-4", "5-3", "5-2", "5-1",
    "4-5", "4-4", "4-3", "4-2", "4-1",
    "3-5", "3-4", "3-3", "3-2", "3-1",
    "2-5", "2-4", "2-3", "2-2", "2-1",
    "1-5", "1-4", "1-3", "1-2", "1-1"
]

TIER_WEIGHT = {
    "1-1": 120, "1-2": 115, "1-3": 110, "1-4": 105, "1-5": 100,
    "2-1":  95, "2-2":  90, "2-3":  85, "2-4":  80, "2-5":  75,
    "3-1":  70, "3-2":  65, "3-3":  60, "3-4":  55, "3-5":  50,
    "4-1":  45, "4-2":  40, "4-3":  35, "4-4":  30, "4-5":  25,
    "5-1":  20, "5-2":  15, "5-3":  10, "5-4":   5, "5-5":   0
}


def calculate_weight(data):
    tier = data.get("tier", "4-1")
    score = data.get("score", 0)
    tier_weight = TIER_WEIGHT.get(tier, 0)
    return max(tier_weight + score, 0)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

async def call_gpt_balance_api(team_count, players_per_team, players):
    import json

    with open("prompts/balance_prompt.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(
        team_count=team_count,
        players_per_team=players_per_team,
        players=json.dumps(players)
    )

    try:
        response = await openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You're a helpful assistant that balances teams."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=1024,
            seed=42,
        )

        content = response.choices[0].message.content.strip()

        # Markdown блок устгана
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                try:
                    parsed = json.loads(part.strip().replace("json", ""))
                    if "teams" in parsed:
                        return parsed["teams"]
                except:
                    continue  # дараагийн блокыг үзнэ
            raise ValueError("GPT хариултанд 'teams' JSON блок олдсонгүй.")
        else:
            # Шууд JSON гэж үзээд оролдоно
            parsed = json.loads(content)
            return parsed.get("teams", [])

    except Exception as e:
        print("❌ GPT баг хуваарилалт алдаа:", e)
        raise Exception("GPT баг хуваарилалт амжилтгүй.")

def tier_score(data: dict) -> int:
    tier = data.get("tier", "4-1")
    score = data.get("score", 0)
    return TIER_WEIGHT.get(tier, 0) + score

def promote_tier(tier):  # Сайжрах → index -1
    try:
        i = TIER_ORDER.index(tier)
        return TIER_ORDER[max(i + 1, 0)]
    except:
        return tier

def demote_tier(tier):  # Дордох → index +1
    try:
        i = TIER_ORDER.index(tier)
        return TIER_ORDER[min(i - 1, len(TIER_ORDER) - 1)]
    except:
        return tier

def generate_tier_order():
    return [f"{i}-{j}" for i in range(5, 0, -1) for j in range(5, 0, -1)]

def get_default_tier():
    return {"score": 0, "tier": "4-1"}

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
        # ✅ хүн бүр багтаа дээд тал нь players_per_team хүргэж авна
        valid_indexes = [
            i for i in range(team_count)
            if len(teams[i]) < players_per_team
        ]

        if not valid_indexes:
            break  # бүх баг дүүрсэн бол зогсоно

        min_team_index = min(valid_indexes, key=lambda i: team_totals[i])
        teams[min_team_index].append(uid)
        team_totals[min_team_index] += weight

    return teams

def reflector_teams(player_weights: dict, team_count: int, players_per_team: int):
    sorted_players = sorted(player_weights.items(), key=lambda x: x[1], reverse=True)
    teams = [[] for _ in range(team_count)]

    left = 0
    right = len(sorted_players) - 1
    i = 0

    while left <= right:
        if len(teams[i]) < players_per_team:
            teams[i].append(sorted_players[left][0])
            left += 1
        if left <= right and len(teams[i]) < players_per_team:
            teams[i].append(sorted_players[right][0])
            right -= 1
        i = (i + 1) % team_count

    return teams

def total_weight_difference(teams, player_weights):
    team_totals = [sum(player_weights.get(uid, 0) for uid in team) for team in teams]
    return max(team_totals) - min(team_totals)

def get_donator_emoji(data):
    from datetime import datetime, timezone, timedelta

    total = data.get("total_mnt", 0)
    last_donated = data.get("last_donated")

    if not last_donated:
        return None

    try:
        donated_time = last_donated if isinstance(last_donated, datetime) else datetime.fromisoformat(str(last_donated))
        # 🛡️ Timezone-гүй байвал UTC болгож тохируулна
        if donated_time.tzinfo is None:
            donated_time = donated_time.replace(tzinfo=timezone.utc)
    except Exception as e:
        print("❌ Emoji parse fail:", e)
        return None

    now = datetime.now(timezone.utc)

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
    if " | " in nick:
        return nick.split(" | ")[-1].strip()
    return nick.strip()

# 🧠 nickname-г оноо + tier + emoji-гаар шинэчлэх
async def update_nicknames_for_users(guild, user_ids: list):
    donors = await get_all_donators()

    for uid in user_ids:
        member = guild.get_member(uid)
        if not member:
            continue

        data = await get_score(uid)
        if not data:
            continue

        tier = data.get("tier", "4-1")
        score = data.get("score", 0)
        base_nick = clean_nickname(member.display_name)

        donor_data = donors.get(str(uid))
        emoji = get_donator_emoji(donor_data) if donor_data else ""

        prefix = f"{emoji} {tier}".strip()
        new_nick = f"{prefix} | {base_nick}"

        try:
            await member.edit(nick=new_nick)
        except Exception as e:
            print(f"⚠️ Nickname update алдаа: {uid} — {e}")
            traceback.print_exc()

async def insert_match(
    timestamp: datetime,
    initiator_id: int,
    team_count: int,
    players_per_team: int,
    winners: list,
    losers: list,
    mode: str,
    strategy: str,
    notes: str = ""
):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO matches (
                timestamp, initiator_id, team_count, players_per_team,
                winners, losers, mode, strategy, notes
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, timestamp, initiator_id, team_count, players_per_team,
             winners, losers, mode, strategy, notes)

# ⏱ 24h session timeout
async def session_timeout_checker():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(3600)

        session = await load_session_state()
        if not session:
            continue

        if session.get("active"):
            last_win_time_str = session.get("last_win_time")
            if not last_win_time_str:
                continue

            try:
                last_win_time = datetime.fromisoformat(last_win_time_str)
                if last_win_time.tzinfo is None:
                    last_win_time = last_win_time.replace(tzinfo=timezone.utc)  # ✅ FIX

                now = datetime.now(timezone.utc)
                if (now - last_win_time).total_seconds() > 86400:
                    await clear_session_state()
                    print("🔚 Session автоматаар хаагдлаа (24h).")
            except Exception as e:
                print("⚠️ session_timeout_checker parse алдаа:", e)



# 🧬 Start
@bot.event
async def on_ready():
    print(f"🤖 Bot нэвтэрлээ: {bot.user}")
    print("📁 Working directory:", os.getcwd())

    # ⚙️ Slash командуудыг global sync хийнэ
    await bot.tree.sync()

    # 🧠 Async task-аар session болон DB pool initialize хийнэ
    asyncio.create_task(initialize_bot())

    # 🕓 Timeout шалгагчийг эхлүүлнэ
    asyncio.create_task(session_timeout_checker())

async def initialize_bot():
    try:
        await init_pool()
        print("✅ DB pool initialized.")
    except Exception as e:
        print("❌ DB pool initialization алдаа:", e)

    try:
        await load_session_state()
        print("📥 Session state амжилттай ачаалагдлаа.")
    except Exception as e:
        print("❌ Session ачаалах үед алдаа гарлаа:", e)

# 🧩 Command: ping
@bot.tree.command(name="ping", description="Bot-ийн latency-г шалгана")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

@bot.tree.command(name="start_match", description="Session эхлүүлнэ, багийн тоо болон тоглогчийн тоог тохируулна")
@app_commands.describe(team_count="Хэдэн багтай байх вэ", players_per_team="Нэг багт хэдэн хүн байх вэ")
async def start_match(interaction: discord.Interaction, team_count: int, players_per_team: int):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return
    # ✅ өмнөх session цэвэрлэх хэсэг
    try:
        await clear_session_state()
        print("🧼 өмнөх session_state устлаа.")
    except Exception as e:
        print("❌ clear_session_state алдаа:", e)
    try:
        now = datetime.now(timezone.utc)

        await save_session_state({
            "active": True,
            "start_time": now,             # ❗️ as datetime object
            "last_win_time": now,         # ❗️ as datetime object
            "initiator_id": interaction.user.id,
            "team_count": team_count,
            "players_per_team": players_per_team,
            "player_ids": [],
            "teams": [],
            "changed_players": [],
            "strategy": ""
        }, allow_empty=True)

        await interaction.followup.send(
            f"🟢 {team_count} багтай, {players_per_team} хүнтэй Session эхэллээ. `addme` коммандаар тоглогчид бүртгүүлнэ үү."
        )

    except Exception as e:
        print("❌ start_match бүхэлдээ гацлаа:", e)
        if not interaction.response.is_done():
            await interaction.followup.send("⚠️ Session эхлүүлэхэд алдаа гарлаа.", ephemeral=True)

@bot.tree.command(name="addme", description="Тоглогч өөрийгөө бүртгүүлнэ")
async def addme(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    try:
        user_id = interaction.user.id
        session = await load_session_state()
        if not session or not session.get("active"):
            await interaction.followup.send("⚠️ Одоогоор session эхлээгүй байна.")
            return

        player_ids = session.get("player_ids", [])
        if user_id in player_ids:
            await interaction.followup.send("📌 Та аль хэдийн бүртгүүлсэн байна.")
            return

        player_ids.append(user_id)
        session["player_ids"] = player_ids
        # 🧠 datetime хөрвүүлэлт хийж өгнө
        if isinstance(session.get("start_time"), str):
            session["start_time"] = datetime.fromisoformat(session["start_time"])
        if isinstance(session.get("last_win_time"), str):
            session["last_win_time"] = datetime.fromisoformat(session["last_win_time"])

        await save_session_state(session)
        await interaction.followup.send(
            f"✅ {interaction.user.mention} бүртгүүллээ.\nНийт бүртгэгдсэн: {len(player_ids)}"
        )

    except Exception as e:
        print("❌ addme бүхэлдээ алдаа:", e)
        await interaction.followup.send("⚠️ Бүртгэх үед алдаа гарлаа.")

@bot.tree.command(name="show_added_players", description="Бүртгэгдсэн тоглогчдыг харуулна")
async def show_added_players(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    try:
        session = await load_session_state()
        if not session:
            await interaction.followup.send("⚠️ Session ачаалахад алдаа гарлаа.")
            return

        player_ids = session.get("player_ids", [])
        if not player_ids:
            await interaction.followup.send("📭 Одоогоор бүртгэгдсэн тоглогч алга.")
            return

        guild = interaction.guild
        mentions = []
        for uid in player_ids:
            member = guild.get_member(uid)
            if member:
                try:
                    mentions.append(member.display_name)
                except Exception as e:
                    print(f"⚠️ mention алдаа uid={uid}:", e)

        if not mentions:
            await interaction.followup.send("⚠️ Discord серверээс нэрсийг ачаалж чадсангүй.")
            return

        text = "\n".join(mentions)
        await interaction.followup.send(f"📋 Бүртгэгдсэн {len(mentions)} тоглогч:\n{text}")

    except Exception as e:
        print("❌ show_added_players алдаа:", e)
        await interaction.followup.send("⚠️ Тоглогчдыг харуулах үед алдаа гарлаа.")

@bot.tree.command(name="remove", description="Тоглогч өөрийгөө бүртгэлээс хасна")
async def remove(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    try:
        user_id = interaction.user.id
        session = await load_session_state()
        if not session or not session.get("active"):
            await interaction.followup.send("⚠️ Session идэвхгүй байна.")
            return

        player_ids = session.get("player_ids", [])
        if user_id not in player_ids:
            await interaction.followup.send("❌ Та бүртгэлд байхгүй байна.")
            return

        try:
            player_ids.remove(user_id)
            session["player_ids"] = player_ids
        except ValueError:
            await interaction.followup.send("⚠️ Та бүртгэлээс аль хэдийн хасагдсан байна.")
            return
        # 🧠 datetime хөрвүүлэлт
        if isinstance(session.get("start_time"), str):
            session["start_time"] = datetime.fromisoformat(session["start_time"])
        if isinstance(session.get("last_win_time"), str):
            session["last_win_time"] = datetime.fromisoformat(session["last_win_time"])

        await save_session_state(session)

        await interaction.followup.send(
            f"🗑 {interaction.user.mention} бүртгэлээс хасагдлаа.\nҮлдсэн: **{len(player_ids)}** тоглогч"
        )
    except Exception as e:
        print("❌ /remove command бүхэлдээ алдаа:", e)
        await interaction.followup.send("⚠️ Хасах үед алдаа гарлаа.")

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

    try:
        user_ids = [int(word[2:-1].replace("!", "")) for word in mention.split() if word.startswith("<@") and word.endswith(">")]
    except Exception as e:
        print("❌ Mention parse алдаа:", e)
        await interaction.followup.send("⚠️ Mention parse хийхэд алдаа гарлаа.")
        return

    if not user_ids:
        await interaction.followup.send("⚠️ Зөв mention хийгээгүй байна.")
        return

    session = await load_session_state()
    if not session or not session.get("active"):
        await interaction.followup.send("⚠️ Session идэвхгүй байна.")
        return

    player_ids = session.get("player_ids", [])
    removed = 0

    for uid in user_ids:
        if uid in player_ids:
            player_ids.remove(uid)
            removed += 1

    session["player_ids"] = player_ids
    # ✅ datetime хөрвүүлэлт
    if isinstance(session.get("start_time"), str):
        session["start_time"] = datetime.fromisoformat(session["start_time"])
    if isinstance(session.get("last_win_time"), str):
        session["last_win_time"] = datetime.fromisoformat(session["last_win_time"])

    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ save_session_state алдаа:", e)

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

    try:
        user_ids = [int(word[2:-1].replace("!", "")) for word in mentions.split() if word.startswith("<@") and word.endswith(">")]
    except Exception as e:
        print("❌ mention parse алдаа:", e)
        await interaction.followup.send("⚠️ Mention parse хийхэд алдаа гарлаа.", ephemeral=True)
        return

    if not user_ids:
        await interaction.followup.send("⚠️ Хамгийн багадаа нэг тоглогч mention хийнэ үү.", ephemeral=True)
        return

    session = await load_session_state()
    now = datetime.now(timezone.utc)

    if not session or not session.get("active"):
        # Session байхгүй бол шинээр эхлүүлнэ
        session = {
            "active": True,
            "start_time": now.isoformat(),
            "last_win_time": now.isoformat(),
            "initiator_id": interaction.user.id,
            "team_count": team_number,
            "players_per_team": 5,
            "player_ids": [],
            "teams": [],
            "changed_players": [],
            "strategy": ""
        }

    teams = session.get("teams", [])
    player_ids = session.get("player_ids", [])

    # ⚠️ Давхардал шалгана
    all_existing_ids = [uid for team in teams for uid in team]
    duplicate_ids = [uid for uid in user_ids if uid in all_existing_ids]
    if duplicate_ids:
        await interaction.followup.send("🚫 Зарим тоглогч аль нэг багт бүртгэгдсэн байна.", ephemeral=True)
        return

    # 🔧 teams[] байхгүй бол үүсгэнэ
    while len(teams) < team_number:
        teams.append([])

    teams[team_number - 1] = user_ids

    for uid in user_ids:
        if uid not in player_ids:
            player_ids.append(uid)

    session["teams"] = teams
    session["player_ids"] = player_ids
    session["team_count"] = max(team_number, session.get("team_count", 2))
    session["initiator_id"] = session.get("initiator_id") or interaction.user.id

    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ save_session_state алдаа:", e)

    await interaction.followup.send(f"✅ {len(user_ids)} тоглогчийг {team_number}-р багт бүртгэлээ.")

@bot.tree.command(name="clear_match", description="Админ: одоогийн идэвхтэй match-ийн баг бүртгэлийг цэвэрлэнэ")
async def clear_match(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    try:
        await clear_session_state()
        await interaction.followup.send("🧼 Session бүрэн цэвэрлэгдлээ.")
    except Exception as e:
        print("❌ clear_session_state алдаа:", e)
        await interaction.followup.send("⚠️ Session цэвэрлэх үед алдаа гарлаа.")

@bot.tree.command(name="go_bot", description="Онооны дагуу тэнцвэртэй баг хуваарилна")
async def go_bot(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    session = await load_session_state()
    if not session or not session.get("active"):
        await interaction.followup.send("⚠️ Session идэвхгүй байна.", ephemeral=True)
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    team_count = session.get("team_count", 2)
    players_per_team = session.get("players_per_team", 5)
    total_slots = team_count * players_per_team
    player_ids = session.get("player_ids", [])

    if not player_ids:
        await interaction.followup.send("⚠️ Бүртгэгдсэн тоглогч алга байна.", ephemeral=True)
        return

    # ✅ Оноо + tier-ийн жин
    player_weights = {}
    for uid in player_ids:
        data = await get_score(uid) or get_default_tier()
        player_weights[uid] = calculate_weight(data)

    sorted_players = sorted(player_weights.items(), key=lambda x: x[1], reverse=True)
    trimmed_players = sorted_players[:total_slots]
    trimmed_weights = dict(trimmed_players)
    left_out_players = sorted_players[total_slots:]

    # 🧠 3 стратеги
    snake = snake_teams(trimmed_weights, team_count, players_per_team)
    greedy = greedy_teams(trimmed_weights, team_count, players_per_team)
    reflector = reflector_teams(trimmed_weights, team_count, players_per_team)

    strategy_diffs = {
        "snake": (snake, total_weight_difference(snake, trimmed_weights)),
        "greedy": (greedy, total_weight_difference(greedy, trimmed_weights)),
        "reflector": (reflector, total_weight_difference(reflector, trimmed_weights))
    }

    strategy, (best_teams, best_diff) = min(strategy_diffs.items(), key=lambda x: x[1][1])

    # 💾 Session хадгалах
    session["teams"] = best_teams
    session["strategy"] = strategy
    session["last_win_time"] = datetime.now(timezone.utc).isoformat()

    try:
        await save_session_state(session, allow_empty=True)
    except Exception as e:
        print("❌ save_session_state алдаа /go_bot:", e)

    # 📋 Хариу харуулах
    guild = interaction.guild
    team_emojis = ["🏆", "💎", "🔥", "🚀", "🛡️", "🎯", "🎮", "🧠", "📦", "⚡️"]
    lines = [f"✅ `{strategy}` хуваарилалт ашиглав (онооны зөрүү: `{best_diff}`)\n"]

    for i, team in enumerate(best_teams, start=1):
        emoji = team_emojis[i - 1] if i - 1 < len(team_emojis) else "🏅"
        total = sum(trimmed_weights.get(uid, 0) for uid in team)
        leader = max(team, key=lambda uid: trimmed_weights.get(uid, 0))
        lines.append(f"{emoji} **#{i}-р баг** (нийт оноо: {total}) 😎\n")
        for uid in team:
            member = guild.get_member(uid)
            name = member.display_name if member else str(uid)
            score = trimmed_weights.get(uid, 0)
            lines.append(f"{name} ({score})" + (" 😎 Team Leader\n" if uid == leader else "\n"))
        lines.append("\n")

    if left_out_players:
        out = "\n• ".join(f"<@{uid}>" for uid, _ in left_out_players)
        lines.append(f"⚠️ **Дараах тоглогчид энэ удаад багт орсонгүй:**\n• {out}")

    is_ranked = players_per_team in [4, 5] and team_count >= 2
    lines.append("\n" + ("🏅 Энэ match: **Ranked** ✅ (оноо тооцно)" if is_ranked else "⚠️ Энэ match: **Ranked биш** ❌"))

    await interaction.followup.send("".join(lines))
    await interaction.followup.send("✅ Match бүртгэгдлээ.")

@bot.tree.command(name="go_gpt", description="GPT-ээр онооны баланс хийж баг хуваарилна")
async def go_gpt(interaction: discord.Interaction):
    session = await load_session_state()
    if not session or not session.get("active"):
        await interaction.response.send_message("⚠️ Session идэвхгүй байна.", ephemeral=True)
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")

    if not (is_admin or is_initiator):
        await interaction.response.send_message("❌ Зөвхөн admin эсвэл тохиргоог эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    team_count = session.get("team_count", 2)
    players_per_team = session.get("players_per_team", 5)
    total_slots = team_count * players_per_team
    player_ids = session.get("player_ids", [])

    # ✅ Оноо + tier-ийн жингүүд
    all_scores = []
    for uid in player_ids:
        data = await get_score(uid) or get_default_tier()
        power = TIER_WEIGHT.get(data.get("tier", "4-1"), 0) + data.get("score", 0)
        all_scores.append({"id": uid, "power": power})

    # ✂️ Хэтэрсэн тоглогчдыг тайрна
    sorted_players = sorted(all_scores, key=lambda x: x["power"], reverse=True)
    selected_players = sorted_players[:total_slots]
    left_out_players = sorted_players[total_slots:]
    score_map = {p["id"]: p["power"] for p in selected_players}

    try:
        teams = await call_gpt_balance_api(team_count, players_per_team, selected_players)
    except Exception as e:
        print("❌ GPT API error:", e)
        await interaction.followup.send(
            "⚠️ GPT-ээр баг хуваарилах үед алдаа гарлаа. Түр зуурын асуудал байж болзошгүй.\n"
            "⏳ Дараа дахин оролдоно уу эсвэл `/go_bot` командыг ашиглаарай."
        )
        return

    # ✅ session шинэчилж хадгалах
    session["teams"] = teams
    session["strategy"] = "gpt"
    session["last_win_time"] = datetime.now(timezone.utc).isoformat()
    session["player_ids"] = list(score_map.keys())  # зөвхөн багт орсон

    await save_session_state(session, allow_empty=True)

    # 📋 Хариу харуулах
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

    session = await load_session_state()
    if not session:
        await interaction.followup.send("⚠️ Session мэдээлэл олдсонгүй.")
        return

    if not (session.get("players_per_team") in [4, 5] and session.get("team_count", 0) >= 2):
        await interaction.followup.send("⚠️ Энэ match нь 4v4/5v5 биш тул оноо тооцохгүй.")
        return

    if not session.get("active") or not session.get("teams"):
        await interaction.followup.send("⚠️ Session идэвхгүй эсвэл багууд бүрдээгүй байна.")
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.")
        return

    try:
        win_indexes = [int(x.strip()) - 1 for x in winner_teams.strip().split()]
        lose_indexes = [int(x.strip()) - 1 for x in loser_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Багийн дугааруудыг зөв оруулна уу (ж: 1 3)")
        return

    all_teams = session.get("teams", [])
    if any(i < 0 or i >= len(all_teams) for i in win_indexes + lose_indexes):
        await interaction.followup.send("⚠️ Багийн дугаар буруу байна.")
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i in lose_indexes for uid in all_teams[i]]
    now = datetime.now(timezone.utc)
    guild = interaction.guild

    def validate_tier(tier): return tier if tier in TIER_ORDER else "4-1"

    def adjust_score(data, delta):
        data["score"] += delta
        if data["score"] >= 5:
            data["tier"] = promote_tier(data["tier"])
            data["score"] = 0
        elif data["score"] <= -5:
            data["tier"] = demote_tier(data["tier"])
            data["score"] = 0
        return data

    winner_details, loser_details = [], []

    for uid in winners:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            data = adjust_score(data, +1)
            member = guild.get_member(uid)
            data["username"] = member.display_name if member else "Unknown"
            await upsert_score(uid, data["score"], data["tier"], data["username"])
            await log_score_transaction(uid, +1, data["score"], data["tier"], "set_match_result")
            await update_player_stats(uid, is_win=True)
            winner_details.append({
                "uid": uid,
                "username": data["username"],
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score,
                "new_score": data["score"],
                "old_tier": old_tier,
                "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Winner uid:{uid} update fail:", e)

    for uid in losers:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            data = adjust_score(data, -1)
            member = guild.get_member(uid)
            data["username"] = member.display_name if member else "Unknown"
            await upsert_score(uid, data["score"], data["tier"], data["username"])
            await log_score_transaction(uid, -1, data["score"], data["tier"], "set_match_result")
            await update_player_stats(uid, is_win=False)
            loser_details.append({
                "uid": uid,
                "username": data["username"],
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score,
                "new_score": data["score"],
                "old_tier": old_tier,
                "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Loser uid:{uid} update fail:", e)

    try:
        await update_nicknames_for_users(guild, [p["uid"] for p in winner_details + loser_details])
    except Exception as e:
        print("⚠️ nickname update error:", e)

    try:
        await save_last_match(winner_details, loser_details)
        await insert_match(
            timestamp=now,
            initiator_id=session.get("initiator_id", 0),
            team_count=session.get("team_count", 2),
            players_per_team=session.get("players_per_team", 5),
            winners=winners,
            losers=losers,
            mode="manual",
            strategy="NormalMatch",
            notes="set_match_result"
        )
    except Exception as e:
        print("❌ Match log алдаа:", e)

    session["last_win_time"] = now.isoformat()
    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ session save алдаа:", e)

    # 🧾 Message
    win_str = ", ".join(f"{i+1}-р баг" for i in win_indexes)
    lose_str = ", ".join(f"{i+1}-р баг" for i in lose_indexes)
    lines = [f"🏆 {win_str} ялж {lose_str} ялагдлаа.\nОноо, Tier шинэчлэгдлээ."]

    if winner_details:
        lines.append("")
        lines.append("✅ **Ялсан тоглогчид:**")
        for p in winner_details:
            try:
                old_tier = p.get("old_tier", "4-1")
                new_tier = p.get("new_tier", "4-1")
                old_score = p.get("old_score", 0)
                new_score = p.get("new_score", 0)
                uid = p["uid"]

                if old_tier not in TIER_ORDER or new_tier not in TIER_ORDER:
                    continue

                change = "⬆" if TIER_ORDER.index(new_tier) < TIER_ORDER.index(old_tier) else (
                        "⬇" if TIER_ORDER.index(new_tier) > TIER_ORDER.index(old_tier) else "")

                lines.append(f"- <@{uid}>: `{old_score} → {new_score}` (Tier: `{old_tier} → {new_tier}`) {change}")
            except Exception as e:
                print("❌ winner_details render алдаа:", e)

    if loser_details:
        lines.append("")
        lines.append("💀 **Ялагдсан тоглогчид:**")
        for p in loser_details:
            try:
                old_tier = p.get("old_tier", "4-1")
                new_tier = p.get("new_tier", "4-1")
                old_score = p.get("old_score", 0)
                new_score = p.get("new_score", 0)
                uid = p["uid"]

                if old_tier not in TIER_ORDER or new_tier not in TIER_ORDER:
                    continue

                change = "⬆" if TIER_ORDER.index(new_tier) < TIER_ORDER.index(old_tier) else (
                        "⬇" if TIER_ORDER.index(new_tier) > TIER_ORDER.index(old_tier) else "")

                lines.append(f"- <@{uid}>: `{old_score} → {new_score}` (Tier: `{old_tier} → {new_tier}`) {change}")
            except Exception as e:
                print("❌ loser_details render алдаа:", e)

    lines.append("✅ Match бүртгэгдлээ.")

    # ✅ Хэт урт мессежийг хэсэгчилж илгээнэ
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)

    for chunk in chunks:
        await interaction.followup.send(chunk)

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

    session = await load_session_state()
    if not session or not session.get("active") or not session.get("teams"):
        await interaction.followup.send("⚠️ Session идэвхгүй эсвэл багууд бүрдээгүй байна.")
        return

    if not (session.get("players_per_team") in [4, 5] and session.get("team_count", 0) >= 2):
        await interaction.followup.send("⚠️ Энэ match нь 4v4/5v5 биш тул оноо тооцохгүй.")
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.")
        return

    try:
        win_indexes = [int(x.strip()) - 1 for x in winner_teams.strip().split()]
        lose_indexes = [int(x.strip()) - 1 for x in loser_teams.strip().split()]
    except ValueError:
        await interaction.followup.send("⚠️ Багийн дугааруудыг зөв оруулна уу (ж: 1 3)")
        return

    all_teams = session.get("teams", [])
    if any(i < 0 or i >= len(all_teams) for i in win_indexes + lose_indexes):
        await interaction.followup.send("⚠️ Багийн дугаар буруу байна.")
        return

    winners = [uid for i in win_indexes for uid in all_teams[i]]
    losers = [uid for i in lose_indexes for uid in all_teams[i]]
    now = datetime.now(timezone.utc)
    guild = interaction.guild

    def validate_tier(tier): return tier if tier in TIER_ORDER else "4-1"
    def adjust_score(data, delta):
        data["score"] += delta
        if data["score"] >= 5:
            data["tier"] = promote_tier(data["tier"])
            data["score"] = 0
        elif data["score"] <= -5:
            data["tier"] = demote_tier(data["tier"])
            data["score"] = 0
        return data

    winner_details, loser_details = [], []

    for uid in winners:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            data = adjust_score(data, +2)
            member = guild.get_member(uid)
            data["username"] = member.display_name if member else "Unknown"
            await upsert_score(uid, data["score"], data["tier"], data["username"])
            await log_score_transaction(uid, +2, data["score"], data["tier"], "fountain")
            await update_player_stats(uid, is_win=True)
            winner_details.append({
                "uid": uid, "username": data["username"],
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score, "new_score": data["score"],
                "old_tier": old_tier, "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Winner uid:{uid} update fail:", e)

    for uid in losers:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            data = adjust_score(data, -2)
            member = guild.get_member(uid)
            data["username"] = member.display_name if member else "Unknown"
            await upsert_score(uid, data["score"], data["tier"], data["username"])
            await log_score_transaction(uid, -2, data["score"], data["tier"], "fountain")
            await update_player_stats(uid, is_win=False)
            loser_details.append({
                "uid": uid, "username": data["username"],
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score, "new_score": data["score"],
                "old_tier": old_tier, "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Loser uid:{uid} update fail:", e)

    try:
        await update_nicknames_for_users(guild, [p["uid"] for p in winner_details + loser_details])
    except Exception as e:
        print("⚠️ nickname update error:", e)

    try:
        await save_last_match(winner_details, loser_details)
        await insert_match(
            timestamp=now,
            initiator_id=session.get("initiator_id", 0),
            team_count=session.get("team_count", 2),
            players_per_team=session.get("players_per_team", 5),
            winners=winners,
            losers=losers,
            mode="manual",
            strategy="fountain",
            notes="set_match_result_fountain"
        )
    except Exception as e:
        print("❌ Match log алдаа:", e)

    session["last_win_time"] = now.isoformat()
    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ session save алдаа:", e)

    win_str = ", ".join(f"{i+1}-р баг" for i in win_indexes)
    lose_str = ", ".join(f"{i+1}-р баг" for i in lose_indexes)
    lines = [f"💦 {win_str} Fountain ялж {lose_str} ялагдлаа.\nОноо, Tier шинэчлэгдлээ."]

    if winner_details:
        lines.append("")
        lines.append("✅ **Ялсан тоглогчид:**")
        for p in winner_details:
            try:
                old_tier = p.get("old_tier", "4-1")
                new_tier = p.get("new_tier", "4-1")
                old_score = p.get("old_score", 0)
                new_score = p.get("new_score", 0)
                uid = p["uid"]

                if old_tier not in TIER_ORDER or new_tier not in TIER_ORDER:
                    print(f"⚠️ Tier алдаа: uid={uid}, old={old_tier}, new={new_tier}")
                    continue

                change = "⬆" if TIER_ORDER.index(new_tier) < TIER_ORDER.index(old_tier) else (
                        "⬇" if TIER_ORDER.index(new_tier) > TIER_ORDER.index(old_tier) else "")

                lines.append(f"- <@{uid}>: `{old_score} → {new_score}` (Tier: `{old_tier} → {new_tier}`) {change}")
            except Exception as e:
                print("❌ winner_details render алдаа:", e)

    if loser_details:
        lines.append("")
        lines.append("💀 **Ялагдсан тоглогчид:**")
        for p in loser_details:
            try:
                old_tier = p.get("old_tier", "4-1")
                new_tier = p.get("new_tier", "4-1")
                old_score = p.get("old_score", 0)
                new_score = p.get("new_score", 0)
                uid = p["uid"]

                if old_tier not in TIER_ORDER or new_tier not in TIER_ORDER:
                    print(f"⚠️ Tier алдаа: uid={uid}, old={old_tier}, new={new_tier}")
                    continue

                change = "⬆" if TIER_ORDER.index(new_tier) < TIER_ORDER.index(old_tier) else (
                        "⬇" if TIER_ORDER.index(new_tier) > TIER_ORDER.index(old_tier) else "")

                lines.append(f"- <@{uid}>: `{old_score} → {new_score}` (Tier: `{old_tier} → {new_tier}`) {change}")
            except Exception as e:
                print("❌ loser_details render алдаа:", e)

    lines.append("✅ Match бүртгэгдлээ.")
        # ✅ Хэт урт мессежийг хэсэгчилж илгээнэ
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)

    for chunk in chunks:
        await interaction.followup.send(chunk)

@bot.tree.command(name="change_player", description="Багийн гишүүдийг солих")
@app_commands.describe(
    from_user="Гарах тоглогч (@mention)",
    to_user="Орох тоглогч (@mention)"
)
async def change_player(interaction: discord.Interaction, from_user: discord.Member, to_user: discord.Member):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    session = await load_session_state()
    if not session or not session.get("active") or not session.get("teams"):
        await interaction.followup.send("⚠️ Session идэвхгүй эсвэл баг бүрдээгүй байна.", ephemeral=True)
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн сольж чадна.", ephemeral=True)
        return

    from_uid = from_user.id
    to_uid = to_user.id
    teams = session["teams"]

    from_team_index = None
    for i, team in enumerate(teams):
        if from_uid in team:
            from_team_index = i
            team.remove(from_uid)
            break

    if from_team_index is None:
        await interaction.followup.send("❌ Гаргах тоглогч багт байхгүй байна.", ephemeral=True)
        return

    # to_user аль багт байсан ч хамаагүй хасна
    for team in teams:
        if to_uid in team:
            team.remove(to_uid)

    # from_user байсан багт to_user-г оруулна
    teams[from_team_index].append(to_uid)

    changed = session.get("changed_players", [])
    if from_uid not in changed:
        changed.append(from_uid)
    if to_uid not in changed:
        changed.append(to_uid)
    session["changed_players"] = changed

    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ session save алдаа:", e)

    await interaction.followup.send(
        f"🔁 **{from_user.display_name}** багаа орхиж **{to_user.display_name}** орлоо!\n"
        f"📌 {from_team_index+1}-р багт солигдолт хийгдсэн."
    )

@bot.tree.command(name="undo_last_match", description="Сүүлд хийсэн match-ийн оноог буцаана")
async def undo_last_match(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        print("❌ Interaction already responded.")
        return

    session = await load_session_state()
    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.followup.send("⛔️ Зөвхөн админ эсвэл session эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    last = await get_last_match()
    if not last:
        await interaction.followup.send("⚠️ Сүүлд бүртгэсэн match олдсонгүй.", ephemeral=True)
        return

    winner_details = last.get("winner_details", [])
    loser_details = last.get("loser_details", [])
    guild = interaction.guild
    changed_ids = []

    async def restore_user(uid, old_score, old_tier):
        try:
            member = guild.get_member(uid)
            username = member.display_name if member else "Unknown"
            await upsert_score(uid, old_score, old_tier, username)
            await log_score_transaction(uid, 0, old_score, old_tier, reason="undo")
            changed_ids.append(uid)
        except Exception as e:
            print(f"❌ Undo fail uid:{uid} – {e}")

    for p in winner_details + loser_details:
        await restore_user(p["uid"], p["old_score"], p["old_tier"])

    try:
        await update_player_stats(
            [p["uid"] for p in winner_details], is_win=True, undo=True
        )
        await update_player_stats(
            [p["uid"] for p in loser_details], is_win=False, undo=True
        )
    except Exception as e:
        print("⚠️ player_stats undo алдаа:", e)

    try:
        await clear_last_match()
    except Exception as e:
        print("⚠️ clear_last_match алдаа:", e)

    try:
        await update_nicknames_for_users(guild, changed_ids)
    except Exception as e:
        print("⚠️ nickname update алдаа:", e)

    win_mentions = " ".join(f"<@{p['uid']}>" for p in winner_details)
    lose_mentions = " ".join(f"<@{p['uid']}>" for p in loser_details)

    await interaction.followup.send(
        f"♻️ Match буцаагдлаа!\n"
        f"🏆 Winner-ууд: {win_mentions}\n"
        f"💀 Loser-ууд: {lose_mentions}"
    )
    await interaction.followup.send("✅ Match бүртгэл цэвэрлэгдлээ.")

@bot.tree.command(name="my_score", description="Таны оноо болон tier-г харуулна")
async def my_score(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)  # ⬅️ public response
    except discord.errors.InteractionResponded:
        return

    uid = interaction.user.id
    data = await get_score(uid)

    if not data:
        await interaction.followup.send("⚠️ Таны оноо бүртгэлгүй байна.")
        return

    tier = data.get("tier", "?")
    score = data.get("score", 0)
    username = data.get("username") or interaction.user.display_name

    await interaction.followup.send(
        f"🏅 {username}:\n"
        f"Tier: **{tier}**\n"
        f"Score: **{score}**"
    )

@bot.tree.command(name="user_score", description="Бусад тоглогчийн оноо болон tier-г харуулна")
@app_commands.describe(user="Оноог нь харах discord хэрэглэгч")
async def user_score(interaction: discord.Interaction, user: discord.Member):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    uid = user.id
    data = await get_score(uid)

    if not data:
        await interaction.followup.send(f"⚠️ {user.display_name} оноо бүртгэлгүй байна.")
        return

    tier = data.get("tier", "4-1")
    score = data.get("score", 0)
    username = data.get("username") or user.display_name

    await interaction.followup.send(
        f"🏅 {username}:\n"
        f"Tier: **{tier}**\n"
        f"Score: **{score}**"
    )

@bot.tree.command(name="player_stats", description="Таны нийт win/loss статистик")
async def player_stats(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    uid = interaction.user.id
    conn = await connect()
    row = await conn.fetchrow("SELECT wins, losses FROM player_stats WHERE uid = $1", uid)
    await conn.close()

    if not row:
        await interaction.followup.send("⚠️ Таны статистик бүртгэлгүй байна.")
        return

    wins = row["wins"] or 0
    losses = row["losses"] or 0
    total = wins + losses
    win_rate = (wins / total) * 100 if total > 0 else 0.0

    username = interaction.user.display_name

    await interaction.followup.send(
        f"📊 **{username} статистик**\n"
        f"🏆 Ялалт: `{wins}` тоглолт\n"
        f"💀 Ялагдал: `{losses}` тоглолт\n"
        f"📊 Total: `{total}` тоглолт\n"
        f"🔥 Win rate: `{win_rate:.1f}%`"
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

    tier_list = list(TIER_WEIGHT.keys())
    if tier not in tier_list:
        await interaction.response.send_message("⚠️ Tier утга буруу байна.", ephemeral=True)
        return

    uid = user.id
    username = user.display_name

    await upsert_score(uid, score, tier, username)
    await update_nicknames_for_users(interaction.guild, [uid])

    await interaction.response.send_message(
        f"✅ {username}-ийн tier **{tier}**, score **{score}** болж шинэчлэгдлээ.", ephemeral=True
    )

@bot.tree.command(name="add_score", description="Тест: оноо нэмэх")
@app_commands.describe(
    mentions="@mention хэлбэрээр заана",
    points="Нэмэх оноо (default: 1)"
)
async def add_score(interaction: discord.Interaction, mentions: str, points: int = 1):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ хэрэглэнэ.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    user_ids = [int(word[2:-1].replace("!", "")) for word in mentions.split() if word.startswith("<@") and word.endswith(">")]

    if not user_ids:
        await interaction.followup.send("⚠️ Хэрэглэгчийн mention оруулна уу.")
        return

    updated = []

    for uid in user_ids:
        member = interaction.guild.get_member(uid)
        if not member:
            continue

        data = await get_score(uid) or get_default_tier()
        data["username"] = member.display_name
        data["score"] += points

        score = data["score"]
        tier = data["tier"]

        while score >= 5:
            tier = promote_tier(tier)
            score = 0
        while score <= -5:
            tier = demote_tier(tier)
            score = 0

        data["score"] = score
        data["tier"] = tier

        await upsert_score(uid, score, tier, data["username"])
        updated.append(uid)

    try:
        await update_nicknames_for_users(interaction.guild, updated)
    except Exception as e:
        print("⚠️ nickname update error:", e)

    mentions_text = ", ".join(f"<@{uid}>" for uid in updated)
    lines = []
    for uid in updated:
        data = await get_score(uid)
        if not data:
            continue
        lines.append(f"<@{uid}>: {data['score']} (Tier: {data['tier']})")

    await interaction.followup.send("✅ Оноо шинэчлэгдлээ:\n" + "\n".join(lines))

@bot.tree.command(name="add_donator", description="Админ: тоглогчийг donator болгоно")
@app_commands.describe(
    member="Donator болгох хэрэглэгч",
    mnt="Хандивласан мөнгө (₮)"
)
async def add_donator(interaction: discord.Interaction, member: discord.Member, mnt: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Энэ командыг зөвхөн админ хэрэглэгч ажиллуулж чадна.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    await upsert_donator(member.id, mnt)
    await update_nicknames_for_users(interaction.guild, [member.id])

    await interaction.followup.send(
        f"🎉 {member.mention} хэрэглэгчийг Donator болголоо! (+{mnt:,}₮ нэмэгдлээ)"
    )

@bot.tree.command(name="donator_list", description="Donator хэрэглэгчдийн жагсаалт")
async def donator_list(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Энэ командыг зөвхөн админ хэрэглэгч ашиглаж болно.",
            ephemeral=True
        )

    try:
        await interaction.response.defer(thinking=True)

        donors = await get_all_donators()
        if not donors:
            return await interaction.followup.send("📭 Donator бүртгэл алга байна.")

        scores = await get_all_scores()

        header_line = "💰" * 24
        footer_line = "💖" * 24
        separator = "-━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━-"

        lines = [f"```", header_line, separator]

        for uid, data in sorted(donors.items(), key=lambda x: x[1].get("total_mnt", 0), reverse=True):
            member = interaction.guild.get_member(int(uid))
            if not member:
                continue

            emoji = get_donator_emoji(data) or ""
            total = data.get("total_mnt", 0)
            tier = scores.get(uid, {}).get("tier", "4-1")
            nick = clean_nickname(member.display_name)

            name_section = f"{emoji} {tier} | {nick}"
            donation_section = f"{total:>7,}₮"
            line = f"{name_section:<47} — {donation_section:>10,}₮"
            lines.append(line)

        lines.append(separator)
        lines.append(footer_line)
        lines.append("```")

        embed = Embed(
            title="💖 Donators",
            description="**Талархал илэрхийлье! Доорх хэрэглэгчид манай server-г дэмжиж, хөгжлийг нь тэтгэсэн байна.**",
            color=0xFFD700
        )
        embed.add_field(name="Дэмжигчдийн жагсаалт", value="\n".join(lines), inline=False)
        embed.set_footer(text="RZR Bot 🌀")

        await interaction.followup.send(embed=embed)

    except Exception as e:
        print("❌ donator_list exception:", e)
        traceback.print_exc()
        await interaction.followup.send("⚠️ Donator жагсаалт авахад алдаа гарлаа.")

@bot.tree.command(name="help_info", description="Bot-ын танилцуулга (readme.md файлыг харуулна)")
async def help_info(interaction: discord.Interaction):
    try:
        with open("Info/Readme.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        await interaction.response.send_message("⚠️ `Readme.md` файл олдсонгүй.", ephemeral=True)
        return

    if len(content) > 1900:
        content = content[:1900] + "\n...\n(үргэлжлэлтэй)"

    await interaction.response.send_message(
        f"📘 **RZR Bot Танилцуулга**\n```markdown\n{content}\n```",
        ephemeral=True
    )

@bot.tree.command(name="help_commands", description="Бүх командын тайлбар жагсаалт")
async def help_commands(interaction: discord.Interaction):
    try:
        with open("Info/Commands_alt.md", "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        await interaction.response.send_message("⚠️ `Commands_alt.md` файл олдсонгүй.", ephemeral=True)
        return

    if len(content) > 1900:
        content = content[:1900] + "\n...\n(үргэлжлэлтэй)"

    await interaction.response.send_message(
        f"📒 **RZR Bot Коммандууд**\n```markdown\n{content}\n```",
        ephemeral=True
    )

@bot.tree.command(name="whois", description="Mention хийсэн хэрэглэгчийн нэрийг харуулна")
@app_commands.describe(mention="Хэрэглэгчийн mention (@name) хэлбэрээр")
async def whois(interaction: discord.Interaction, mention: str):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    try:
        uid = int(mention.strip("<@!>"))
        member = await interaction.guild.fetch_member(uid)
        await interaction.followup.send(
            f"🕵️‍♂️ Энэ ID: `{uid}`\n"
            f"🔗 Mention: {member.mention}\n"
            f"👤 Display Name: `{member.display_name}`",
            ephemeral=True
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Олдсонгүй: {e}", ephemeral=True)

@bot.tree.command(name="debug_id", description="Таны Discord ID-г харуулна")
async def debug_id(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    await interaction.followup.send(f"🆔 Таны Discord ID: `{interaction.user.id}`", ephemeral=True)

@bot.tree.command(name="current_match", description="Одоогийн идэвхтэй session-д хувиарлагдсан багуудыг харуулна")
async def current_match(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    # 🧠 Session DB-оос ачаална
    session = await load_session_state()
    if not session or not session.get("active"):
        await interaction.followup.send("⚠️ Session идэвхгүй байна.")
        return

    teams = session.get("teams", [])
    if not teams or not any(teams):
        await interaction.followup.send("📭 Багууд хараахан хуваарилагдаагүй байна.")
        return

    all_scores = await get_all_scores()
    guild = interaction.guild
    msg_lines = []

    for i, team in enumerate(teams, start=1):
        total_score = sum(tier_score(all_scores.get(str(uid), {})) for uid in team)
        msg_lines.append(f"**🏅 Team {i}** (нийт оноо: `{total_score}`):")

        for uid in team:
            data = all_scores.get(str(uid), {})
            tier = data.get("tier", "4-1")
            score = data.get("score", 0)
            member = guild.get_member(uid)
            name = member.display_name if member else f"`{uid}`"
            msg_lines.append(f"- {name} ({tier} | {score})")

        msg_lines.append("")  # newline

    await interaction.followup.send("\n".join(msg_lines))

@bot.tree.command(name="leaderboard", description="Топ 10 тоглогчийн оноо, win/loss, winrate харуулна")
async def leaderboard(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    all_scores = await get_all_scores()
    if not all_scores:
        await interaction.followup.send("📭 Онооны мэдээлэл байхгүй байна.")
        return

    # 🧮 Tier+score нийлбэрээр эрэмбэлнэ
    sorted_data = sorted(all_scores.items(), key=lambda x: tier_score(x[1]), reverse=True)
    uid_list = [int(uid) for uid, _ in sorted_data[:10]]

    # 📊 Player stats SQL-оос авахаар тохируулсан
    stat_rows = await get_player_stats(uid_list)
    stat_map = {str(row["uid"]): {"wins": row["wins"], "losses": row["losses"]} for row in stat_rows}

    lines = ["🏅 **Leaderboard** — Top 10 (Tier + Score | 🏆/💀 — Winrate%)"]
    for i, (uid, data) in enumerate(sorted_data[:10], 1):
        member = interaction.guild.get_member(int(uid))
        if not member:
            continue

        username = data.get("username") or member.display_name
        tier = data.get("tier", "4-1")
        score = data.get("score", 0)

        stat = stat_map.get(uid, {})
        wins = stat.get("wins", 0)
        losses = stat.get("losses", 0)
        total = wins + losses
        winrate = (wins / total * 100) if total > 0 else 0.0

        lines.append(f"{i}. {tier} | {score:+} — {username} 🏆{wins} / 💀{losses} — {winrate:.1f}%")

    await interaction.followup.send("\n".join(lines))

@bot.tree.command(name="match_history", description="Сүүлийн 5 match-ийн мэдээлэл (SQL хувилбар)")
async def match_history(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT timestamp, mode, initiator_id, strategy, teams, winner_team
        FROM matches
        ORDER BY timestamp DESC
        LIMIT 5;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await interaction.followup.send("📭 Match бүртгэл хоосон байна.")
        return

    lines = ["📜 **Сүүлийн Match-ууд:**"]
    for i, row in enumerate(rows, 1):
        ts = row["timestamp"]
        dt = datetime.fromisoformat(str(ts)).astimezone(timezone(timedelta(hours=8)))
        ts_str = dt.strftime("%Y-%m-%d %H:%M")

        mode = row["mode"]
        strategy = row.get("strategy", "-")
        initiator_id = row.get("initiator_id", None)
        initiator_tag = f"<@{initiator_id}>" if initiator_id else "?"
        teams = row["teams"]
        winner = row.get("winner_team", None)

        lines.append(f"\n**#{i} | {mode.upper()} | 🧠 `{strategy}` | 🕓 {ts_str}** — {initiator_tag}")

        for t_idx, team in enumerate(teams, 1):
            tag = "🏆" if winner == t_idx else "🎮"
            players = ", ".join(f"<@{uid}>" for uid in team)
            lines.append(f"{tag} Team {t_idx}: {players}")

    await interaction.followup.send("\n".join(lines))

@bot.tree.command(name="resync", description="Slash командуудыг дахин бүртгэнэ (админ)")
async def resync(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("⛔️ Зөвхөн админ ашиглана.", ephemeral=True)
        return

    try:
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ {len(synced)} команд амжилттай дахин бүртгэгдлээ.", ephemeral=True)
    except Exception as e:
        print("❌ resync алдаа:", e)
        await interaction.followup.send("⚠️ Комманд sync хийх үед алдаа гарлаа.", ephemeral=True)

# 🎯 Run
async def main():
    from keep_alive import keep_alive
    keep_alive()  # 🟢 Railway дээр амьд байлгах сервер

    if not TOKEN:
        print("❌ DISCORD_TOKEN тохируулагдаагүй байна.")
        return

    print("🚀 Bot эхлэх гэж байна...")
    await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

