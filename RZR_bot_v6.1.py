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
import traceback
from asyncio import sleep
from typing import List, Dict
import math

# 🗄️ Local modules
from database import (
    connect, pool, init_pool, ensure_pool,

    # 🎯 Score & tier
    get_score, upsert_score, get_all_scores, get_default_tier,
    promote_tier, demote_tier, get_player_stats, update_player_stats,

    # 📊 Match
    save_last_match, get_last_match, insert_match, clear_last_match,

    # 🛡 Session
    save_session_state, load_session_state, clear_session_state,

    # 💖 Donator
    get_all_donators, upsert_donator,

    log_score_result,

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
    from openai import OpenAI
    client = OpenAI()  # эсвэл таны одоо хэрэглэж буй openai объект

    with open("prompts/balance_prompt.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    prompt = prompt_template.format(
        team_count=team_count,
        players_per_team=players_per_team,
        players=json.dumps(players, ensure_ascii=False)
    )

    try:
        # GPT-5 mini Balanced сонголт: хурд + үнэ + чанар дундаж түвшинд.
        resp = await client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a precise team balancing engine that returns strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1024,
            seed=42,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content.strip()

        # Ашиглах JSON-оо шууд parse
        parsed = json.loads(content)
        teams = parsed.get("teams", None)
        if not isinstance(teams, list):
            raise ValueError("`teams` not found or not a list in GPT response.")
        return teams

    except Exception as e:
        print("❌ GPT баг хуваарилалт алдаа:", e)
        raise

def team_totals(teams, weights):
    return [sum(weights.get(uid, 0) for uid in team) for team in teams]

def balance_cost(teams, weights):
    totals = team_totals(teams, weights)
    return max(totals) - min(totals)

def all_ids(teams):
    return [uid for team in teams for uid in team]

def local_refine(teams, weights, max_rounds=200):
    """
    Жижигхэн greedy swap heuristic:
    - Багуудын аль хамгийн их/бага нийлбэртэйг олно
    - Тэр 2 багийн гишүүдээс солилцох хос хайна (зардлыг багасгавал шууд хэрэгжүүлнэ)
    - Давтана (max_rounds)
    """
    from copy import deepcopy
    T = deepcopy(teams)
    def score(tt): return balance_cost(tt, weights)

    best = score(T)
    rounds = 0

    while rounds < max_rounds:
        rounds += 1
        totals = team_totals(T, weights)
        hi = max(range(len(T)), key=lambda i: totals[i])
        lo = min(range(len(T)), key=lambda i: totals[i])

        improved = False
        # hi ба lo багийн хооронд swap хайна
        for a_idx, a in enumerate(T[hi]):
            for b_idx, b in enumerate(T[lo]):
                if a == b: 
                    continue
                cand = [list(x) for x in T]
                cand[hi][a_idx], cand[lo][b_idx] = cand[lo][b_idx], cand[hi][a_idx]
                c = score(cand)
                if c < best:
                    T = cand
                    best = c
                    improved = True
                    break
            if improved:
                break

        if not improved:
            break
    return T, best

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
        return ""

    try:
        donated_time = last_donated if isinstance(last_donated, datetime) else datetime.fromisoformat(str(last_donated))
        if donated_time.tzinfo is None:
            donated_time = donated_time.replace(tzinfo=timezone.utc)
    except Exception as e:
        print("❌ Emoji parse fail:", e)
        return ""

    now = datetime.now(timezone.utc)
    if (now - donated_time).days > 30:
        return ""

    if total >= 30000:
        return "👑"
    elif total >= 10000:
        return "💸"
    else:
        return "💰"

def clean_nickname(nick: str) -> str:
    """
    {donor} {tier} | {base} | {perf}  → base
    {tier} | {base}                    → base
    other                              → trimmed(nick)
    """
    if not nick:
        return ""
    parts = [p.strip() for p in nick.split(" | ")]
    if len(parts) >= 2:
        # len==3 (donor/tier | base | perf)  эсвэл len==2 (tier | base)
        return parts[1]
    return nick.strip()

async def update_nicknames_for_users(guild, user_ids: list[int]):
    from database import get_all_donators, get_score
    donors = await get_all_donators()

    MAX_LEN = 32
    for uid in user_ids:
        member = guild.get_member(uid)
        if not member:
            continue
        if member.top_role >= guild.me.top_role:
            continue

        data = await get_score(uid)
        if not data:
            continue

        tier = data.get("tier", "4-1")
        base = clean_nickname(member.display_name)

        donor_emoji = ""
        d = donors.get(str(uid))
        if d:
            donor_emoji = get_donator_emoji(d) or ""

        perf = await get_performance_emoji(uid)  # "✅✅", "❌", "⏸", "➖" г.м.

        # "{donor} {tier} | {base} | {perf}"  (perf хоосон/⏸/➖ байсан ч харагдана)
        prefix = f"{donor_emoji} {tier}".strip()
        parts = [prefix, base] + ([perf] if perf else [])
        new_nick = " | ".join(parts)

        if len(new_nick) > MAX_LEN:
            fixed_len = len(prefix) + 3 + (3 + len(perf) if perf else 0)  # prefix + " | " + (" | perf")
            allow = max(MAX_LEN - fixed_len, 0)
            base = base[:allow]
            parts = [prefix, base] + ([perf] if perf else [])
            new_nick = " | ".join(parts)

        try:
            if member.nick != new_nick:
                await member.edit(nick=new_nick)
                print(f"✅ nickname → {uid}: {new_nick}")
            else:
                print(f"↔️ {uid}: unchanged → алгасав ({new_nick})")
        except Exception as e:
            print(f"⚠️ Nickname update алдаа: {uid} — {e}")

async def ensure_pool() -> bool:
    try:
        if pool is None:
            print("ℹ️ ensure_pool: initializing pool…")
            await init_pool()  # database.py
        return True
    except Exception as e:
        print(f"⚠️ ensure_pool error: {e}")
        return False
    
PERF_EMOJI_CAP = None  # None = хязгааргүй; жишээ нь 5 бол 5 хүртэл

async def get_performance_emoji(uid: int) -> str:
    SQL = """
        SELECT result
        FROM score_log
        WHERE uid = $1
          AND timestamp >= (NOW() AT TIME ZONE 'UTC') - INTERVAL '12 HOURS'
    """
    rows, conn = [], None
    try:
        from database import ensure_pool as _ensure, pool as _pool, connect as _connect
        ok = await _ensure()
        if ok and _pool is not None:
            async with _pool.acquire() as c:
                rows = await c.fetch(SQL, uid)
        else:
            conn = await _connect()
            rows = await conn.fetch(SQL, uid)
    except Exception as e:
        print(f"⚠️ get_performance_emoji алдаа: {uid} — {e}")
        return ""
    finally:
        if conn:
            try:
                await conn.close()
            except:
                pass

    if not rows:
        return "⏸"  # сүүлийн 12 цагт тоглоогүй (ялгаатай тэмдэг)

    perf = sum(1 if r["result"] == "win" else -1 for r in rows)

    if perf > 0:
        n = perf if PERF_EMOJI_CAP is None else min(perf, PERF_EMOJI_CAP)
        return "✅" * n
    if perf < 0:
        n = (-perf) if PERF_EMOJI_CAP is None else min(-perf, PERF_EMOJI_CAP)
        return "❌" * n
    return "➖"  # ялалт/ялагдал тэнцүү

async def ensure_scores_for_users(guild, uids: list[int]) -> list[int]:
    """scores хүснэгтэд байхгүй бол default tier/score-оор үүсгэнэ."""
    created = []
    for uid in uids:
        try:
            if not await get_score(uid):
                member = guild.get_member(uid)
                username = member.display_name if member else "Unknown"
                d = get_default_tier()  # {"score":0,"tier":"4-1"}
                await upsert_score(uid, d["score"], d["tier"], username)
                created.append(uid)
        except Exception as e:
            print(f"⚠️ ensure_scores_for_users алдаа uid={uid}: {e}")
    if created:
        print(f"🆕 scores-д шинээр нэмэгдсэн: {created}")
    return created

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

def _tier_arrow(old_tier: str, new_tier: str) -> str:
    try:
        oi = TIER_ORDER.index(old_tier); ni = TIER_ORDER.index(new_tier)
        if ni < oi:  return "⬆"
        if ni > oi:  return "⬇"
        return "→"
    except Exception:
        return ""

async def _fmt_player_line(guild, weights_map, p: Dict) -> str:
    """
    p: {"uid", "username", "old_score","new_score","old_tier","new_tier","team"}
    """
    uid = p["uid"]
    member = guild.get_member(uid)
    name = member.display_name if member else p.get("username") or str(uid)
    old_s, new_s = p.get("old_score", 0), p.get("new_score", 0)
    old_t, new_t = p.get("old_tier", "4-1"), p.get("new_tier", "4-1")
    arrow = _tier_arrow(old_t, new_t)
    perf  = await get_performance_emoji(uid)  # ✅ / ❌ / ⏸ / ➖
    w     = weights_map.get(uid)  # байхгүй байж болно
    w_txt = f" · w:{w}" if w is not None else ""
    return f"- <@{uid}> **{name}** — `{old_s} → {new_s}` · `[{old_t} → {new_t}]` {arrow} {perf}{w_txt}"

def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

async def send_match_result_embed(
    interaction: discord.Interaction,
    *,
    mode_label: str,               # "Normal" | "Fountain"
    ranked: bool,
    win_indexes: List[int],
    lose_indexes: List[int],
    winner_details: List[Dict],
    loser_details: List[Dict],
    session: Dict,
    weights_map: Dict[int, int] | None = None
):
    guild = interaction.guild
    weights_map = weights_map or {}

    # ─ Summary ─
    win_str  = ", ".join(f"{i+1}-р баг" for i in win_indexes) if win_indexes else "—"
    lose_str = ", ".join(f"{i+1}-р баг" for i in lose_indexes) if lose_indexes else "—"
    ranked_badge = "🏅 Ranked" if ranked else "⚠️ Unranked"
    title = f"🏆 Match Result — {mode_label} ({ranked_badge})"

    emb = discord.Embed(
        title=title,
        description=f"**Winners:** {win_str}\n**Losers:** {lose_str}",
        color=0x43B581 if ranked else 0x7289DA
    )

    # ─ Winners field(s) ─
    if winner_details:
        lines_w = []
        for p in winner_details:
            try:
                line = await _fmt_player_line(guild, weights_map, p)
                lines_w.append(line)
            except Exception as e:
                print("winner line error:", e)
        # Discord embed field limit ~1024 тэмдэгт → хэсэглэж нэмнэ
        for part in _chunks(lines_w, 10):
            emb.add_field(name="✅ Winners", value="\n".join(part), inline=False)
    else:
        emb.add_field(name="✅ Winners", value="—", inline=False)

    # ─ Losers field(s) ─
    if loser_details:
        lines_l = []
        for p in loser_details:
            try:
                line = await _fmt_player_line(guild, weights_map, p)
                lines_l.append(line)
            except Exception as e:
                print("loser line error:", e)
        for part in _chunks(lines_l, 10):
            emb.add_field(name="💀 Losers", value="\n".join(part), inline=False)
    else:
        emb.add_field(name="💀 Losers", value="—", inline=False)

    # ─ Footer ─
    initiator = session.get("initiator_id")
    team_cnt  = session.get("team_count") or len(session.get("teams") or [])
    ppl_team  = session.get("players_per_team") or (max(len(t) for t in session.get("teams") or [[]]) if session.get("teams") else 0)
    emb.set_footer(text=f"Teams: {team_cnt} × {ppl_team} • Initiator: {initiator}")

    # Илгээх
    await interaction.followup.send(embed=emb)

# ── Team assignment Embed helper ─────────────────────────────────────────────
from typing import Dict, List

def _team_badge(i: int) -> str:
    badges = ["🥇","🥈","🥉","🎯","🔥","🚀","🎮","🛡️","⚔️","🧠","🏅"]
    return badges[i % len(badges)]

async def _fmt_member_line(guild, uid: int, w: int | None, is_leader: bool) -> str:
    member = guild.get_member(uid)
    name = member.display_name if member else str(uid)
    perf = await get_performance_emoji(uid)  # ✅/❌/⏸/➖
    leader = " 😎 Team Leader" if is_leader else ""
    wtxt = f" ({w})" if w is not None else ""
    return f"- {name}{wtxt} {perf}{leader}"

def _split_fields(lines: List[str], per_field: int = 10) -> List[str]:
    return ["\n".join(lines[i:i+per_field]) for i in range(0, len(lines), per_field)]

async def send_team_assignment_embed(
    interaction: discord.Interaction,
    *,
    title_prefix: str,            # "Bot" | "GPT"
    strategy_note: str,           # ж: "`snake` (diff=12)" эсвэл "`gpt+local_refine` (diff=7)"
    team_count: int,
    players_per_team: int,
    teams: List[List[int]],
    weights_map: Dict[int, int],
    left_out: List[int] | List[tuple] | None = None,
    ranked: bool | None = None
):
    guild = interaction.guild
    left_out = left_out or []
    # total & diff
    totals = [sum(weights_map.get(u, 0) for u in team) for team in teams]
    diff = (max(totals) - min(totals)) if totals else 0

    ranked_badge = ""
    if ranked is not None:
        ranked_badge = " • 🏅 Ranked" if ranked else " • ⚠️ Unranked"

    emb = discord.Embed(
        title=f"🤝 {title_prefix} — Team Assignment",
        description=f"Strategy: {strategy_note} • diff: `{diff}`{ranked_badge}\n"
                    f"Setup: **{team_count} × {players_per_team}**",
        color=0x2ECC71 if title_prefix.lower() == "bot" else 0x5865F2
    )

    # Teams
    for i, team in enumerate(teams):
        badge = _team_badge(i)
        t_total = totals[i] if i < len(totals) else 0
        # team leader (highest weight)
        leader_uid = max(team, key=lambda u: weights_map.get(u, 0)) if team else None

        # member lines
        member_lines = []
        for u in team:
            w = weights_map.get(u)
            member_lines.append(await _fmt_member_line(guild, u, w, is_leader=(u == leader_uid)))

        # split to multiple fields if long
        parts = _split_fields(member_lines, per_field=10)
        # first field shows team header
        if parts:
            emb.add_field(
                name=f"{badge} Team #{i+1} — total: `{t_total}`",
                value=parts[0],
                inline=False
            )
            for extra in parts[1:]:
                emb.add_field(name="\u200B", value=extra, inline=False)  # zero-width header
        else:
            emb.add_field(
                name=f"{badge} Team #{i+1} — total: `{t_total}`",
                value="—",
                inline=False
            )

    # Left‑out players (if any)
    lo_ids = []
    if left_out:
        # left_out may be list[(uid, weight)] эсвэл list[uid]
        for x in left_out:
            if isinstance(x, tuple) or isinstance(x, list):
                lo_ids.append(int(x[0]))
            else:
                lo_ids.append(int(x))
        lo_text = "• " + "\n• ".join(f"<@{u}>" for u in lo_ids)
        emb.add_field(name="⚠️ This round not included", value=lo_text, inline=False)

    await interaction.followup.send(embed=emb)


# 🧬 Start
@bot.event
async def on_ready():
    print(f"🤖 Bot нэвтэрлээ: {bot.user}")
    print("📁 Working directory:", os.getcwd())
    await init_pool() 
    print("✅ DB pool амжилттай эхэллээ.")
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

@bot.tree.command(name="start_match", description="Session эхлүүлнэ (шинэ тоглолтын session)")
async def start_match(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return
    try:
        await clear_session_state()
        print("🧼 өмнөх session_state устлаа.")
    except Exception as e:
        print("❌ clear_session_state алдаа:", e)

    try:
        now = datetime.now(timezone.utc)

        await save_session_state({
            "active": True,
            "start_time": now,
            "last_win_time": now,
            "initiator_id": interaction.user.id,
            "player_ids": [],
            "teams": [],
            "changed_players": [],
            "strategy": ""
        }, allow_empty=True)

        await interaction.followup.send(
            "🟢 Session эхэллээ. `addme` коммандаар тоглогчид бүртгүүлнэ үү."
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

        player_ids = session.get("player_ids", []) or []
        if not player_ids:
            await interaction.followup.send("📭 Одоогоор бүртгэгдсэн тоглогч алга.")
            return

        guild = interaction.guild

        # ✅ Нэг дор аваад DB round-trip багасгана
        all_scores = await get_all_scores()  # { "uid": {tier, score, ...}, ... }

        # 🔢 мөр бүрийн мэдээллийг параллель бэлдэх
        async def build_row(uid: int):
            member = guild.get_member(uid)
            name = member.display_name if member else f"{uid}"
            data = all_scores.get(str(uid)) or get_default_tier()
            tier = data.get("tier", "4-1")
            score = int(data.get("score", 0))
            weight = TIER_WEIGHT.get(tier, 0) + score
            perf = await get_performance_emoji(uid)  # ✅/❌/⏸/➖
            return (uid, name, tier, score, weight, perf)

        rows = await asyncio.gather(*[build_row(uid) for uid in player_ids])

        # 📊 Жингээр (ихээс багад) эрэмбэлнэ
        rows.sort(key=lambda r: r[4], reverse=True)

        # 🖼 Embed бэлдье
        emb = discord.Embed(
            title=f"📋 Бүртгэгдсэн тоглогчид — {len(rows)}",
            description="Жин (tier+score)‑ээр эрэмбэлсэн жагсаалт.",
            color=0xF1C40F
        )

        # мөрүүдийг 10-аар нь багцалж талбаруудад хийнэ (Discord field limit хамгаална)
        lines = [
            f"- {name} — `{tier} | {score:+}` · w:`{weight}` {perf}"
            for (_uid, name, tier, score, weight, perf) in rows
        ]
        parts = ["\n".join(lines[i:i+10]) for i in range(0, len(lines), 10)]

        if parts:
            emb.add_field(name="👥 Тоглогчид", value=parts[0], inline=False)
            for extra in parts[1:]:
                emb.add_field(name="\u200B", value=extra, inline=False)  # zero-width header
        else:
            emb.add_field(name="👥 Тоглогчид", value="—", inline=False)

        # 💡 Жижиг зөвлөмж
        team_count = session.get("team_count") or 2
        ppl_per = session.get("players_per_team") or 5
        emb.set_footer(text=f"Tip: /go_bot {team_count} {ppl_per} эсвэл /go_gpt {team_count} {ppl_per}")

        await interaction.followup.send(embed=emb)

    except Exception as e:
        print("❌ show_added_players алдаа:", e)
        await interaction.followup.send("⚠️ Тоглогчдыг харуулах үед алдаа гарлаа.")

@bot.tree.command(name="remove", description="Тоглогч өөрийгөө бүртгэлээс хасна")
async def remove(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)
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
        await interaction.response.defer(thinking=True)
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
@app_commands.describe(team_count="Хэдэн багтай байх вэ", players_per_team="Нэг багт хэдэн хүн байх вэ")
async def go_bot(interaction: discord.Interaction, team_count: int, players_per_team: int):
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
    session["team_count"] = team_count
    session["players_per_team"] = players_per_team
    session["teams"] = best_teams
    session["strategy"] = strategy
    session["last_win_time"] = datetime.now(timezone.utc).isoformat()

    try:
        await save_session_state(session, allow_empty=True)
    except Exception as e:
        print("❌ save_session_state алдаа /go_bot:", e)

    # 🆕 Embed render
    is_ranked = players_per_team in [4, 5] and team_count >= 2
    try:
        await send_team_assignment_embed(
            interaction,
            title_prefix="Bot",
            strategy_note=f"`{strategy}` (diff={best_diff})",
            team_count=team_count,
            players_per_team=players_per_team,
            teams=best_teams,
            weights_map=trimmed_weights,               # {uid: weight}
            left_out=[uid for uid, _ in left_out_players],
            ranked=is_ranked
        )
    except Exception:
        traceback.print_exc()


@bot.tree.command(name="go_gpt", description="GPT-ээр онооны баланс хийж баг хуваарилна")
@app_commands.describe(
    team_count="Багийн тоо (жишээ: 2)",
    players_per_team="Нэг багт хэдэн тоглогч байх вэ (жишээ: 5)"
)
async def go_gpt(interaction: discord.Interaction, team_count: int, players_per_team: int):
    session = await load_session_state()
    if not session or not session.get("active"):
        await interaction.response.send_message("⚠️ Session идэвхгүй байна.", ephemeral=True)
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_initiator = interaction.user.id == session.get("initiator_id")
    if not (is_admin or is_initiator):
        await interaction.response.send_message("❌ Зөвхөн admin эсвэл тохиргоог эхлүүлсэн хүн ажиллуулж чадна.", ephemeral=True)
        return

    if team_count < 2 or players_per_team < 1:
        await interaction.response.send_message("⚠️ Багийн тоо ≥ 2, тоглогчийн тоо ≥ 1 байх ёстой.", ephemeral=True)
        return

    try:
        await interaction.response.defer(thinking=True)
    except discord.errors.InteractionResponded:
        return

    total_slots = team_count * players_per_team
    player_ids = session.get("player_ids", []) or []

    if not player_ids:
        await interaction.followup.send("⚠️ Бүртгэгдсэн тоглогч алга байна.", ephemeral=True)
        return

    # 🔢 Жин (tier + score)
    all_scores = []
    for uid in player_ids:
        data = await get_score(uid) or get_default_tier()
        power = TIER_WEIGHT.get(data.get("tier", "4-1"), 0) + data.get("score", 0)
        all_scores.append({"id": uid, "power": power})

    sorted_players = sorted(all_scores, key=lambda x: x["power"], reverse=True)
    selected_players = sorted_players[:total_slots]         # яг дүүргэх тоогоор хайчилж авна
    left_out_players = sorted_players[total_slots:]
    weights = {p["id"]: p["power"] for p in selected_players}
    allowed_ids = {p["id"] for p in selected_players}

    # 🧽 Sanitize helper
    def sanitize(teams, team_count, players_per_team, allowed_ids):
        if not isinstance(teams, list) or len(teams) != team_count:
            return None
        clean = []
        seen = set()
        for t in teams:
            if not isinstance(t, list):
                return None
            row = []
            for u in t:
                try:
                    u = int(u)
                except:
                    continue
                if u in allowed_ids and u not in seen and len(row) < players_per_team:
                    row.append(u); seen.add(u)
            clean.append(row)

        # дутууг нөхөх
        remaining = [u for u in allowed_ids if u not in seen]
        for i in range(team_count):
            while len(clean[i]) < players_per_team and remaining:
                clean[i].append(remaining.pop())

        # валид
        if any(len(x) != players_per_team for x in clean):
            return None
        return clean

    # 🤖 GPT дуудах
    try:
        raw = await call_gpt_balance_api(team_count, players_per_team, selected_players)
    except Exception as e:
        print("❌ GPT API error:", e)
        traceback.print_exc()
        await interaction.followup.send("⚠️ GPT дуудлага амжилтгүй. Түр `/go_bot` эсвэл дараа дахин оролдоно уу.")
        return

    teams = sanitize(raw, team_count, players_per_team, allowed_ids)
    if teams is None:
        await interaction.followup.send("⚠️ GPT буцаасан бүтэц буруу байлаа. `/go_bot` ашиглана уу.")
        return

    # 🔧 GPT гарцыг локал сайжруулалт (swap) – зардлыг улам бууруулна
    refined_teams, cost = local_refine(teams, weights, max_rounds=300)

    # 💾 Session
    session["team_count"] = team_count
    session["players_per_team"] = players_per_team
    session["teams"] = refined_teams
    session["strategy"] = f"gpt+local_refine(cost={cost})"
    session["last_win_time"] = datetime.now(timezone.utc).isoformat()
    session["player_ids"] = list(weights.keys())

    await save_session_state(session, allow_empty=True)

    # ⚡ Performance emoji (кэштэй)
    perf_cache = {}
    async def perf(uid: int) -> str:
        if uid not in perf_cache:
            perf_cache[uid] = await get_performance_emoji(uid)
        return perf_cache[uid]

    # 🆕 Embed render
    is_ranked = players_per_team in [4, 5] and team_count >= 2
    try:
        await send_team_assignment_embed(
            interaction,
            title_prefix="GPT",
            strategy_note=f"`gpt+local_refine` (cost={cost})",
            team_count=team_count,
            players_per_team=players_per_team,
            teams=refined_teams,
            weights_map=weights,                        # {uid: power}
            left_out=[p["id"] for p in left_out_players],
            ranked=is_ranked
        )
    except Exception:
        traceback.print_exc()


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

    ranked = session.get("players_per_team") in [4, 5] and session.get("team_count", 0) >= 2
    if not ranked:
        await interaction.followup.send("ℹ️ Энэ match нь **Ranked биш** тул оноо, tier өөрчлөгдөхгүй. Гэхдээ бүртгэл хадгалагдана.")

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
    losers  = [uid for i in lose_indexes for uid in all_teams[i]]
    now = datetime.now(timezone.utc)
    guild = interaction.guild

    # 🆕 winners/losers бүх UID-д scores-д default бичлэг үүсгэнэ
    await ensure_scores_for_users(guild, list(set(winners + losers)))

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

    # ✅ WINNERS
    for uid in winners:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            member = guild.get_member(uid)
            username = member.display_name if member else "Unknown"

            # Оноо/түйвшин зөвхөн ranked үед
            if ranked:
                data = adjust_score(data, +1)
                await upsert_score(uid, data["score"], data["tier"], username)
                await update_player_stats(uid, is_win=True)

            # 🆕 PERF LOG — ranked‑аас үл хамааран
            try:
                await log_score_result(uid, "win")
            except Exception as e:
                print("⚠️ log_score_result(win) алдаа:", e)

            winner_details.append({
                "uid": uid, "username": username,
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score, "new_score": data["score"],
                "old_tier": old_tier, "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Winner uid:{uid} update fail:", e)

    # ❌ LOSERS
    for uid in losers:
        try:
            data = await get_score(uid) or get_default_tier()
            old_score, old_tier = data["score"], data["tier"]
            data["tier"] = validate_tier(data["tier"])
            member = guild.get_member(uid)
            username = member.display_name if member else "Unknown"

            if ranked:
                data = adjust_score(data, -1)
                await upsert_score(uid, data["score"], data["tier"], username)
                await update_player_stats(uid, is_win=False)

            # 🆕 PERF LOG — ranked‑аас үл хамааран
            try:
                await log_score_result(uid, "loss")
            except Exception as e:
                print("⚠️ log_score_result(loss) алдаа:", e)

            loser_details.append({
                "uid": uid, "username": username,
                "team": next((i+1 for i, team in enumerate(all_teams) if uid in team), None),
                "old_score": old_score, "new_score": data["score"],
                "old_tier": old_tier, "new_tier": data["tier"]
            })
        except Exception as e:
            print(f"❌ Loser uid:{uid} update fail:", e)

    # Nickname refresh
    try:
        await update_nicknames_for_users(guild, [p["uid"] for p in winner_details + loser_details])
    except Exception as e:
        print("⚠️ nickname update error:", e)

    # Match log
    try:
        print("✅ insert_match эхэлж байна...")
        await clear_last_match()
        await save_last_match(winner_details or [], loser_details or [])
        await insert_match(
            initiator_id=session.get("initiator_id", 0),
            team_count=len(session.get("teams", [])),
            players_per_team=max(len(t) for t in session.get("teams", [])) if session.get("teams") else 0,
            winners=[int(uid) for uid in winners],
            losers=[int(uid) for uid in losers],
            mode="manual",
            strategy="NormalMatch",
            notes="set_match_result"
        )
        print("✅ insert_match амжилттай дууслаа")
    except Exception as e:
        print("❌ Match log алдаа:", e)
        traceback.print_exc()

    session["last_win_time"] = now.isoformat()
    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ session save алдаа:", e)

    # Render
    try:
        await send_match_result_embed(
            interaction,
            mode_label="Normal",
            ranked=ranked,
            win_indexes=win_indexes,
            lose_indexes=lose_indexes,
            winner_details=winner_details,
            loser_details=loser_details,
            session=session,
            weights_map={}  # хүсвэл weights dict өгч болно
        )
    except Exception:
        traceback.print_exc()

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
    if not session:
        await interaction.followup.send("⚠️ Session мэдээлэл олдсонгүй.")
        return

    ranked = session.get("players_per_team") in [4, 5] and session.get("team_count", 0) >= 2
    if not ranked:
        await interaction.followup.send("ℹ️ Энэ match нь **Ranked биш** тул оноо, tier өөрчлөгдөхгүй. Гэхдээ бүртгэл хадгалагдана.")

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
    losers  = [uid for i in lose_indexes for uid in all_teams[i]]
    now = datetime.now(timezone.utc)
    guild = interaction.guild

    # 🆕 scores-д default үүсгэнэ
    await ensure_scores_for_users(guild, list(set(winners + losers)))

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
            member = guild.get_member(uid)
            username = member.display_name if member else "Unknown"

            if ranked:
                data = adjust_score(data, +2)
                await upsert_score(uid, data["score"], data["tier"], username)
                await update_player_stats(uid, is_win=True)

            # 🆕 PERF LOG
            try:
                await log_score_result(uid, "win")
            except Exception as e:
                print("⚠️ log_score_result(win) алдаа:", e)

            winner_details.append({
                "uid": uid, "username": username,
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
            member = guild.get_member(uid)
            username = member.display_name if member else "Unknown"

            if ranked:
                data = adjust_score(data, -2)
                await upsert_score(uid, data["score"], data["tier"], username)
                await update_player_stats(uid, is_win=False)

            # 🆕 PERF LOG
            try:
                await log_score_result(uid, "loss")
            except Exception as e:
                print("⚠️ log_score_result(loss) алдаа:", e)

            loser_details.append({
                "uid": uid, "username": username,
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
        await clear_last_match()
        await save_last_match(winner_details or [], loser_details or [])
        await insert_match(
            initiator_id=session.get("initiator_id", 0),
            team_count=len(session.get("teams", [])),
            players_per_team=max(len(t) for t in session.get("teams", [])) if session.get("teams") else 0,
            winners=winners,
            losers=losers,
            mode="manual",
            strategy="fountain",
            notes="set_match_result_fountain"
        )
    except Exception as e:
        print("❌ Match log алдаа:", e)
        traceback.print_exc()

    session["last_win_time"] = now.isoformat()
    try:
        await save_session_state(session)
    except Exception as e:
        print("❌ session save алдаа:", e)

    # Render
    try:
        await send_match_result_embed(
            interaction,
            mode_label="Fountain",
            ranked=ranked,
            win_indexes=win_indexes,
            lose_indexes=lose_indexes,
            winner_details=winner_details,
            loser_details=loser_details,
            session=session,
            weights_map={}  # хүсвэл weights dict өгч болно
        )
    except Exception:
        traceback.print_exc()

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
        return

    try:
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

        # 🧩 JSON parse
        winner_details = json.loads(last.get("winner_details", "[]"))
        loser_details = json.loads(last.get("loser_details", "[]"))
        guild = interaction.guild
        changed_ids = []

        async def restore_user(uid, old_score, old_tier):
            try:
                member = guild.get_member(uid)
                username = member.display_name if member else "Unknown"
                await upsert_score(uid, old_score, old_tier, username)
                changed_ids.append(uid)
            except Exception as e:
                print(f"❌ Undo fail uid:{uid} – {e}")

        for p in winner_details + loser_details:
            await restore_user(p["uid"], p["old_score"], p["old_tier"])

        try:
            for p in winner_details:
                await update_player_stats(p["uid"], is_win=True, undo=True)
            for p in loser_details:
                await update_player_stats(p["uid"], is_win=False, undo=True)
        except Exception as e:
            print("⚠️ player_stats undo алдаа:", e)

        # ✅ Matches-с хамгийн сүүлийн match-ийг id-аар нь устгана
        try:
            conn = await connect()
            await conn.execute("DELETE FROM matches WHERE id = (SELECT MAX(id) FROM matches)")
            await conn.close()
        except Exception as e:
            print("⚠️ matches-с устгах үед алдаа:", e)

        # ✅ Last match clear
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
    except Exception as e:
        print("❌ Match буцаах үед алдаа гарлаа:", e)
        await interaction.followup.send("❌ Match буцаах үед алдаа гарлаа.")

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

        # Donor-уудыг нийт мөнгөөр эрэмбэлэх
        sorted_donors = sorted(
            donors.items(),
            key=lambda x: x[1].get("total_mnt", 0),
            reverse=True
        )

        embed = discord.Embed(
            title="💖 Donators",
            description="**Манай server-г хөгжүүлж, дэмжиж буй бүх Donator хэрэглэгчиддээ баярлалаа!** 🎉",
            color=0xFFD700
        )

        top_emojis = ["🥇", "🥈", "🥉"]
        total_sum = 0
        others_text = ""

        for i, (uid, data) in enumerate(sorted_donors, start=1):
            member = interaction.guild.get_member(int(uid))
            if not member:
                continue

            total = int(data.get("total_mnt", 0))
            total_sum += total
            tier = scores.get(uid, {}).get("tier", "4-1")
            nick = member.mention

            emoji = top_emojis[i-1] if i <= 3 else "✨"
            value = f"{emoji} **{nick}** (Tier {tier}) — **{total:,}₮**"

            if i == 1:
                embed.add_field(name="🏆 Top Donators", value=value, inline=False)
            elif i <= 3:
                embed.add_field(name="\u200b", value=value, inline=False)
            else:
                others_text += f"\n{value}"

        # Top 3-с хойшхи бүх доноруудыг нэг field-д оруулах
        if others_text:
            embed.add_field(name="Бусад дэмжигчид", value=others_text.strip(), inline=False)

        embed.set_footer(text=f"RZR Bot 🌀 | Дэмжлэгийн нийт дүн: {total_sum:,}₮")

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

    try:
        conn = await connect()
        rows = await conn.fetch("""
            SELECT timestamp, mode, strategy, initiator_id, winners, losers
            FROM matches
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        await conn.close()
    except Exception:
        import traceback
        traceback.print_exc()
        await interaction.followup.send("❌ Match унших үед алдаа гарлаа.")
        return

    if not rows:
        await interaction.followup.send("📭 Match бүртгэл хоосон байна.")
        return

    lines = ["📜 **Сүүлийн Match-ууд:**"]

    import json
    from datetime import timezone, timedelta

    def ensure_list(x):
        if x is None:
            return []
        if isinstance(x, (list, tuple)):
            return list(x)
        if isinstance(x, str):
            try:
                v = json.loads(x)
                return v if isinstance(v, list) else []
            except Exception:
                return []
        return []

    for i, row in enumerate(rows, 1):
        ts = row["timestamp"]
        # tzinfo байхгүй timestamp ирвэл UTC гэж үзэж онооно
        try:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            # Ховор тохиолдолд ts нь datetime биш байвал алгасна
            pass

        try:
            dt = ts.astimezone(timezone(timedelta(hours=8)))
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            ts_str = str(ts)

        mode = (row["mode"] or "").upper()
        strategy = row["strategy"] or "?"
        initiator = f"<@{row['initiator_id']}>"

        winners = ensure_list(row["winners"])
        losers = ensure_list(row["losers"])

        win_str = ", ".join(f"<@{uid}>" for uid in winners) if winners else "—"
        lose_str = ", ".join(f"<@{uid}>" for uid in losers) if losers else "—"

        lines.append(
            f"\n**#{i} | {mode} | 🧠 `{strategy}` | 🕓 {ts_str}** — {initiator}\n"
            f"🏆 Winner: {win_str}\n"
            f"💀 Loser: {lose_str}"
        )

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

@bot.tree.command(name="diag", description="Админ: орчны онош")
async def diag(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ.", ephemeral=True); return
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    # DB
    db_ok, db_msg = False, ""
    try:
        conn = await connect()
        await conn.execute("SELECT 1")
        await conn.close()
        db_ok, db_msg = True, "DB OK"
    except Exception as e:
        db_msg = f"DB FAIL: {e}"

    # OpenAI (жижиг JSON test)
    ai_ok, ai_msg = False, ""
    try:
        import json
        from openai import OpenAI
        client = OpenAI()
        r = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"user","content":"Return {\"ok\":true} as JSON only"}],
            temperature=0,
            response_format={"type":"json_object"},
            max_tokens=16,
        )
        _ = json.loads(r.choices[0].message.content)
        ai_ok, ai_msg = True, "OpenAI OK"
    except Exception as e:
        ai_msg = f"OpenAI FAIL: {e}"

    # Perms (nickname edit)
    me = interaction.guild.me
    perm_ok = interaction.guild.me.guild_permissions.manage_nicknames
    perm_msg = "Nick perm OK" if perm_ok else "Nick perm MISSING"

    await interaction.followup.send(
        f"🩺 DIAG\n• {db_msg}\n• {ai_msg}\n• {perm_msg}",
        ephemeral=True
    )

@bot.tree.command(name="diag_dryrun", description="Админ: DRY-RUN оношилгоо (ямар ч өгөгдөл хадгалахгүй)")
@app_commands.describe(
    mode='Балансын тест: "mock" (анхдагч) эсвэл "real" (GPT дуудна, хадгалж үлдээхгүй)'
)
async def diag_dryrun(interaction: discord.Interaction, mode: str = "mock"):
    # 1) зөвшөөрөл
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⛔️ Зөвхөн админ.", ephemeral=True)
        return
    try:
        await interaction.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        return

    messages = []

    # 2) DB DRY-RUN — TEMP TABLE ашигладаг тул ямар ч ул мөр үлдэхгүй
    db_ok, db_msg = False, ""
    try:
        from database import connect
        conn = await connect()  # asyncpg.connect(DATABASE_URL) ашигладаг:contentReference[oaicite:1]{index=1}
        try:
            async with conn.transaction():
                await conn.execute("CREATE TEMP TABLE z_diag(x int);")
                await conn.execute("INSERT INTO z_diag(x) VALUES (1),(2),(3);")
                cnt = await conn.fetchval("SELECT COUNT(*) FROM z_diag;")
                db_ok = (cnt == 3)
            # TEMP TABLE нь transaction-оос хамааралгүйгээр сешн дуусмагц устна
            db_msg = "DB OK (temp write/read ажиллалаа)" if db_ok else "DB WARN (unexpected count)"
        finally:
            await conn.close()
    except Exception as e:
        db_msg = f"DB FAIL: {e}"
    messages.append(f"• {db_msg}")

    # 3) OpenAI DRY-RUN — жижиг JSON тест
    ai_ok, ai_msg = False, ""
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Return {\"ok\":true} as JSON only"}],
            temperature=0,
            max_tokens=16,
            # Хэрвээ танай орчинд response_format дэмжихгүй бол try/except-оор унтрааж болно
            response_format={"type": "json_object"},
        )
        _ = json.loads(resp.choices[0].message.content)
        ai_ok, ai_msg = True, "OpenAI OK"
    except Exception as e:
        ai_msg = f"OpenAI FAIL: {e}"
    messages.append(f"• {ai_msg}")

    # 4) Discord permission — nickname edit
    me = interaction.guild.me
    can_nick = bool(me.guild_permissions.manage_nicknames)
    perm_msg = "Nick perm OK" if can_nick else "Nick perm MISSING"
    messages.append(f"• {perm_msg}")

    # 5) Балансын DRY‑RUN (хуудуун GPT MOCK эсвэл бодитоор GPT дуудаад хадгалалгүй харуулна)
    try:
        # Жин үүсгэх: 10 тоглогч, 2 баг * 5 хүн
        team_count, players_per_team = 2, 5
        fake_players = [{"id": 10_000 + i, "power": random.randint(20, 120)} for i in range(team_count*players_per_team)]
        weights = {p["id"]: p["power"] for p in fake_players}

        if mode.lower() == "real":
            # бодитоор GPT-ээс баг авна (teams), ГЭХДЭЭ хадгалахгүй
            teams = await call_gpt_balance_api(team_count, players_per_team, fake_players)  # таны одоогийн функц:contentReference[oaicite:2]{index=2}
            # локал сайжруулалт (swap) — илүү сайн баланс
            teams, cost = local_refine(teams, weights, max_rounds=100)  # таны функц:contentReference[oaicite:3]{index=3}
            mode_note = f"gpt+local_refine (diff={max(sum(weights.get(u,0) for u in t) for t in teams) - min(sum(weights.get(u,0) for u in t) for t in teams)})"
        else:
            # MOCK: greedy эсвэл reflector ашиглаж түр хөрвүүлээд (кодод чинь бий):contentReference[oaicite:4]{index=4}
            teams = greedy_teams(weights, team_count, players_per_team)
            teams, cost = local_refine(teams, weights, max_rounds=100)
            mode_note = f"mock+local_refine (diff={cost})"

        # Хариуг зөвхөн шалгах зорилгоор харуулна — DB/session ТООРХОЙЛТ ХИЙХГҮЙ
        totals = [sum(weights.get(uid,0) for uid in t) for t in teams]
        lines = [f"🧪 Balance DRY‑RUN — {mode_note}",
                 f"Totals: {totals} (min={min(totals)}, max={max(totals)})"]
        for i, t in enumerate(teams, 1):
            lines.append(f"#{i} → " + ", ".join(f"{uid}:{weights[uid]}" for uid in t))
        messages.append("\n".join(lines))
    except Exception as e:
        messages.append(f"• Balance DRY‑RUN FAIL: {e}")

    # 6) Эцсийн тайлан (эпhemeral)
    await interaction.followup.send("🩺 **DRY‑RUN DIAG**\n" + "\n".join(messages), ephemeral=True)

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

