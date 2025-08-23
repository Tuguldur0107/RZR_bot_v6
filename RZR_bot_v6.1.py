# 🌐 Built-in modules
import os
import json
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
import unicodedata
import re

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
import math, random, os, PIL
from typing import Dict, List
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageFont, ImageChops, __file__ as PIL_FILE
from io import BytesIO


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

DONOR_BG_PATH = "./assets/donator_template_gold.png"
CANVAS_W, CANVAS_H = 1152, 768    # Жишээтэй ойролцоо 3:2 харьцаа
PAD = 48

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
    from openai import AsyncOpenAI
    client = AsyncOpenAI()  # async client

    # 📝 Тогтмол дүрэм (system message)
    PROMPT_RULES = f"""
    You are a precise team balancing engine.
    Rules:
    - Always return strict JSON only in this format: {{"teams": [[id1,id2,...],[...],...]}}
    - Use only the IDs given.
    - Exactly {team_count} teams, each with {players_per_team} players.
    - No explanations, no markdown, no text.
    """

    try:
        resp = await client.chat.completions.create(
            model="gpt-5-mini",   # эсвэл gpt-5 / gpt-5-nano гэж солиод хэрэглэж болно
            messages=[
                {"role": "system", "content": PROMPT_RULES},
                {"role": "user", "content": json.dumps({
                    "team_count": team_count,
                    "players_per_team": players_per_team,
                    "players": players
                }, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content.strip()
        if content.startswith("```"):
            lines = [ln for ln in content.splitlines() if not ln.strip().startswith("```")]
            content = "\n".join(lines).strip()

        parsed = json.loads(content)
        teams = parsed["teams"] if isinstance(parsed, dict) and "teams" in parsed else parsed
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
    return ""  # ялалт/ялагдал тэнцүү

async def daily_nickname_refresh():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("⚠️ guild олдсонгүй"); return

    while not bot.is_closed():
        # — Дараагийн 14:00 (UTC+8)-ийг тооцоолно
        now_utc = datetime.now(timezone.utc)
        now_mn  = now_utc.astimezone(MN_TZ)

        target_mn = now_mn.replace(hour=14, minute=0, second=0, microsecond=0)
        if target_mn <= now_mn:
            target_mn += timedelta(days=1)   # өнөөдрийн 14:00 өнгөрсөн бол маргааш

        # — Хэд унтахыг секундээр
        sleep_secs = (target_mn - now_mn).total_seconds()
        print(f"🕒 Nick refresh will run at {target_mn.isoformat()} (MN) — sleeping {int(sleep_secs)}s")
        await asyncio.sleep(sleep_secs)

        # — Ажиллуулах (rate-limit ээлтэйгээр хэсэглэж явуулъя)
        try:
            member_ids = [m.id for m in guild.members if not m.bot]
            BATCH = 50
            for i in range(0, len(member_ids), BATCH):
                chunk = member_ids[i:i+BATCH]
                await update_nicknames_for_users(guild, chunk)
                await asyncio.sleep(2)  # Discord rate limit-ээс сэргийлж амьсгаа авъя
            print("✅ Nicknames refreshed at 14:00 MN time")
        except Exception as e:
            print("❌ nickname refresh error:", e)
        # дараагийн давталт дахин “дараагийн 14:00”-ийг шинээр тооцно

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

async def _fmt_player_line(guild, weights_map, p: dict) -> str:
    """
    p: {"uid","username","old_score","new_score","old_tier","new_tier","team"}
    """
    uid = p["uid"]
    member = guild.get_member(uid)

    # 🔧 Ник доторх "tier | base | perf" загвараас зөвхөн BASE нэрийг гаргана
    raw_name = member.display_name if member else (p.get("username") or str(uid))
    base = clean_nickname(raw_name) or raw_name

    old_s, new_s = p.get("old_score", 0), p.get("new_score", 0)
    old_t, new_t = p.get("old_tier", "4-1"), p.get("new_tier", "4-1")

    # Tier өөрчлөлтийн сум
    try:
        oi = TIER_ORDER.index(old_t); ni = TIER_ORDER.index(new_t)
        t_arrow = "⬆" if ni < oi else ("⬇" if ni > oi else "→")
    except Exception:
        t_arrow = ""

    # Перф эможи (сүүлийн 12 цаг)
    perf = await get_performance_emoji(uid)

    # Хэрэв жин байгаа бол харуулна
    w = weights_map.get(uid)
    wtxt = f" · w:{w}" if w is not None else ""

    # 🧾 Эцсийн мөр – mention + base нэр, дараа нь оноо/тэр/перф
    return f"- <@{uid}> — `{old_s} → {new_s}` · `[{old_t} → {new_t}]` {t_arrow}{wtxt}"

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

def _team_badge(i: int) -> str:
    badges = ["🥇","🥈","🥉","🎯","🔥","🚀","🎮","🛡️","⚔️","🧠","🏅"]
    return badges[i % len(badges)]

async def _fmt_member_line(guild, uid: int, w: int | None, is_leader: bool) -> str:
    member = guild.get_member(uid)
    raw = member.display_name if member else str(uid)

    # 🔧 Никнэймээс base‑ийг салгаж авна (tier/emoji-г давтахгүй)
    base = clean_nickname(raw) or raw

    perf = await get_performance_emoji(uid)
    leader = " 😎 Team Leader" if is_leader else ""
    wtxt = f" ({w})" if w is not None else ""
    return f"- <@{uid}>{wtxt}{leader}"

def format_mnt(amount: int) -> str:
    return f"{amount:,}₮".replace(",", " ")

def _sanitize_name_for_card(text: str) -> str:
    import unicodedata
    # Compatibility normalize → фэнси үсгүүд A,B,... болж хувирна
    s = unicodedata.normalize("NFKC", text or "")
    # zero-width / variation selector-уудыг авч хаяна
    s = s.replace("\u200b","").replace("\u200d","").replace("\ufe0f","")
    # зөвхөн үсэг, тоо, space ба аюулгүй цөөн тэмдэг үлдээнэ
    allowed = " ._-'|()/+&[]:"
    s = "".join(ch for ch in s if ch.isalnum() or ch in allowed)
    return s.strip()

async def render_donor_card(member: discord.Member, amount_mnt: int) -> BytesIO:
    # 1) template-ээ бэлэн болгоно
    lay = _ensure_gold_template(DONOR_BG_PATH)
    W, H = CANVAS_W, CANVAS_H

    base = Image.open(DONOR_BG_PATH).convert("RGBA")
    img = base.copy()
    draw = ImageDraw.Draw(img)

    # 2) Avatar
    ax, ay, ad = lay["avatar"]
    REQ = 256
    try:
        asset = member.display_avatar.replace(size=REQ)
        data = await asset.read()
        av = Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        av = Image.new("RGBA", (REQ, REQ), (200,200,200,255))
    av = ImageOps.fit(av, (ad, ad), method=Image.LANCZOS)
    mask = Image.new("L", (ad, ad), 0)
    ImageDraw.Draw(mask).ellipse((0,0,ad,ad), fill=255)
    img.paste(av, (ax, ay), mask)

    # 3) Amount text (ж/нь: 50 000₮)
    amount_text = format_mnt(amount_mnt) if "format_mnt" in globals() else f"{amount_mnt:,}₮".replace(",", " ")
    x, y, w, h = lay["amount_box"]
    f_amount = _fit_font(draw, amount_text, prefer=82, min_size=42, max_w=w-40, bold=True)
    # center
    tw = draw.textlength(amount_text, font=f_amount)
    tx = x + (w - tw)//2
    ty = y + (h - f_amount.size)//2 - 6
    # small shadow + gold
    draw.text((tx+2, ty+2), amount_text, font=f_amount, fill=(40,15,0))
    draw.text((tx, ty), amount_text, font=f_amount, fill=(255,195,90))

    # 4) Name text (normalize хийж, фэнси тэмдэгтүүдийг цэвэрлэнэ)
    display_name = _sanitize_name_for_card(
        (member.global_name or member.display_name or member.name)
    )
    x, y, w, h = lay["name_box"]
    f_name = _fit_font(draw, display_name, prefer=78, min_size=40, max_w=w-40, bold=True)
    tw = draw.textlength(display_name, font=f_name)
    tx = x + (w - tw)//2
    ty = y + (h - f_name.size)//2 - 6
    draw.text((tx+2, ty+2), display_name, font=f_name, fill=(40,15,0))
    draw.text((tx, ty), display_name, font=f_name, fill=(255,205,120))

    # 5) Thank-you tagline (доорх хайрцагт, рандом нэг мөр)
    sx, sy, sw, sh = lay["extra_box"]
    sub = random.choice(THANK_LINES)
    f_sub = _fit_font(draw, sub, prefer=40, min_size=26, max_w=sw-40, bold=False)
    stw = draw.textlength(sub, font=f_sub)
    stx = sx + (sw - stw)//2
    sty = sy + (sh - f_sub.size)//2 - 2
    draw.text((stx+2, sty+2), sub, font=f_sub, fill=(40,15,0))
    draw.text((stx, sty), sub, font=f_sub, fill=(255,190,90))

    # 6) export
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

THANK_LINES = ["Дэмжлэгт тань баярлалаа!",]

_FONT_LOGGED = set()

def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    root = Path(__file__).resolve().parent
    candidates = [
        root / "assets" / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path(PIL_FILE).parent / "fonts" / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    ]
    for p in candidates:
        try:
            f = ImageFont.truetype(str(p), size)
            key = (str(p), size, bold)
            if key not in _FONT_LOGGED:
                print(f"🅵 Font loaded → {p.name} | size={size} | bold={bold}")
                _FONT_LOGGED.add(key)
            return f
        except Exception:
            continue
    # fallback – алдаа шидэхгүй
    print("🅵 Font fallback → ImageFont.load_default()")
    return ImageFont.load_default()

def _fit_font(draw: ImageDraw.ImageDraw, text: str, prefer: int, min_size: int, max_w: int, bold=True):
    size = prefer
    while size >= min_size:
        f = _font(size, bold=bold)
        w = draw.textlength(text, font=f)
        if w <= max_w:
            return f
        size -= 2
    return _font(min_size, bold=bold)

def _template_layout() -> dict:
    W, H = CANVAS_W, CANVAS_H
    av_d = int(min(W,H)*0.28)
    av_x = PAD + 30
    av_y = int(H*0.5 - av_d/2)

    # amount box: avatar-ийн баруун талд
    amount_w, amount_h = int(W*0.36), int(H*0.12)
    amount_x = av_x + av_d + 40
    amount_y = int(H*0.34) - amount_h//2

    # name box: доор нь
    name_w, name_h = int(W*0.36), int(H*0.13)
    name_x = amount_x
    name_y = amount_y + amount_h + 22

    # extra box (жижиг мөр, optional)
    extra_w, extra_h = name_w, int(H*0.09)
    extra_x = amount_x
    extra_y = name_y + name_h + 22

    return {
        "avatar": (av_x, av_y, av_d),
        "amount_box": (amount_x, amount_y, amount_w, amount_h),
        "name_box": (name_x, name_y, name_w, name_h),
        "extra_box": (extra_x, extra_y, extra_w, extra_h),
    }

def _ensure_gold_template(path: str = DONOR_BG_PATH) -> dict:
    p = Path(path)
    if p.exists():
        # Layout координатуудыг буцаана (avatar/amount/name хайрцгууд)
        return _template_layout()

    W, H = CANVAS_W, CANVAS_H
    bg = Image.new("RGB", (W, H), (36, 14, 0))

    # Radial + linear gradient blend (burnt orange)
    lin = Image.new("RGB", (1, H))
    lp = lin.load()
    top, bot = (92, 40, 8), (35, 14, 2)
    for y in range(H):
        t = y/(H-1)
        lp[0, y] = (
            int(top[0]*(1-t)+bot[0]*t),
            int(top[1]*(1-t)+bot[1]*t),
            int(top[2]*(1-t)+bot[2]*t)
        )
    lin = lin.resize((W, H))
    rad = Image.new("RGB", (W, H), (0,0,0))
    cx, cy = int(W*0.68), int(H*0.46)
    rp = rad.load()
    col1, col2 = (120, 55, 10), (60, 25, 4)
    rmax = math.hypot(W, H)
    for y in range(H):
        for x in range(W):
            t = min(math.hypot(x-cx, y-cy)/rmax*1.6, 1.0)
            rp[x, y] = (
                int(col1[0]*(1-t)+col2[0]*t),
                int(col1[1]*(1-t)+col2[1]*t),
                int(col1[2]*(1-t)+col2[2]*t),
            )
    bg = Image.blend(lin, rad, 0.55)

    # Subtle paper texture (noise)
    noise = Image.effect_noise((W, H), 24).filter(ImageFilter.GaussianBlur(0.6))
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    bg = ImageChops.overlay(bg, noise_rgb)

    draw = ImageDraw.Draw(bg)

    # ----- Medal (баруун тал) -----
    gold     = (243, 163, 62)
    gold_dim = (196, 117, 32)
    gold_dark= (132, 77, 18)

    # ribbons
    rb = Image.new("RGBA", (int(W*0.5), int(H*0.5)), (0,0,0,0))
    rbd = ImageDraw.Draw(rb)
    # зүүн тууз
    rbd.polygon([(80,0),(220,0),(320,260),(180,260)], fill=(*gold_dim,220))
    # баруун тууз
    rbd.polygon([(260,0),(400,0),(300,260),(160,260)], fill=(*gold,220))
    rb = rb.filter(ImageFilter.GaussianBlur(1))
    rb = rb.rotate(-11, resample=Image.BICUBIC, expand=1)
    bg.paste(rb, (int(W*0.58), int(H*0.02)), rb)

    # medal disk
    cx, cy, R = int(W*0.73), int(H*0.48), int(min(W,H)*0.18)
    # outer glow
    glow = Image.new("RGBA", (R*2+60, R*2+60), (0,0,0,0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((0,0,R*2+60,R*2+60), fill=(255,170,60,70))
    glow = glow.filter(ImageFilter.GaussianBlur(25))
    bg.paste(glow, (cx-R-30, cy-R-30), glow)

    # ring layers
    ring = Image.new("RGBA", (R*2, R*2), (0,0,0,0))
    rd = ImageDraw.Draw(ring)
    rd.ellipse((0,0,R*2,R*2), fill=gold)
    rd.ellipse((16,16,R*2-16,R*2-16), fill=gold_dim)
    rd.ellipse((30,30,R*2-30,R*2-30), fill=gold)
    ring = ring.filter(ImageFilter.GaussianBlur(0.6))
    bg.paste(ring, (cx-R, cy-R), ring)

    # heart in medal
    heart = Image.new("RGBA", (R, R), (0,0,0,0))
    hd = ImageDraw.Draw(heart)
    hr = R//2
    # зүрхний зам (хоёр тойрог + гурвалжин ойролцоолол)
    hd.pieslice((0,hr//2,hr,hr+hr//2), 180, 360, fill=gold_dim)
    hd.pieslice((hr,hr//2,R,hr+hr//2), 180, 360, fill=gold_dim)
    hd.polygon([(0,hr),(R,hr),(hr, R)], fill=gold_dim)
    heart = heart.filter(ImageFilter.GaussianBlur(0.5))
    bg.paste(heart, (cx-hr, cy-hr//2), heart)

    # dollar icons (background watermark)
    for i in range(6):
        s = random.randint(64, 120)
        op = random.randint(35, 70)
        fx = random.randint(int(W*0.52), W-80)
        fy = random.randint(40, H-80)
        f  = _font(s, bold=True)
        ImageDraw.Draw(bg).text((fx, fy), "$", font=f, fill=(230,150,50,op))

    # ----- Left placeholders: avatar circle + frames -----
    # avatar frame
    av_d = int(min(W,H)*0.28)
    av_x = PAD + 30
    av_y = int(H*0.5 - av_d/2)
    # outer ring glow
    rg = Image.new("RGBA", (av_d+34, av_d+34), (0,0,0,0))
    rgd = ImageDraw.Draw(rg)
    rgd.ellipse((0,0,av_d+34,av_d+34), fill=(255, 190, 90, 60))
    rgd.ellipse((17,17,av_d+17,av_d+17), fill=(0,0,0,0))
    rg = rg.filter(ImageFilter.GaussianBlur(8))
    bg.paste(rg, (av_x-17, av_y-17), rg)
    # thin ring
    ImageDraw.Draw(bg).ellipse((av_x, av_y, av_x+av_d, av_y+av_d), outline=gold, width=6)

    # amount / name / extra boxes (stroke only)
    def box(x,y,w,h, r=16, alpha=180, width=6):
        img = Image.new("RGBA", (w,h), (0,0,0,0))
        idr = ImageDraw.Draw(img)
        idr.rounded_rectangle((0,0,w,h), r, outline=(255,180,90,alpha), width=width)
        bg.paste(img, (x,y), img)

    lay = _template_layout()
    # amount
    ax, ay, aw, ah = lay["amount_box"]
    box(ax, ay, aw, ah, r=14)
    # name
    nx, ny, nw, nh = lay["name_box"]
    box(nx, ny, nw, nh, r=14)
    # tagline
    tx, ty, tw, th = lay["extra_box"]
    box(tx, ty, tw, th, r=14, alpha=150, width=5)

    # “DONATOR” word watermark (background хэсэгт)
    f = _font(128, bold=True)
    ImageDraw.Draw(bg).text((int(W*0.58), int(H*0.66)), "DONATOR", font=f, fill=(255,190,90,120))

    # save template
    Path(p.parent).mkdir(parents=True, exist_ok=True)
    bg.save(str(p), format="PNG", optimize=True)
    return lay

def _check_send_perms(interaction: discord.Interaction):
    """return: ok, err_text, can_embed, can_attach"""
    me = interaction.guild.me
    cp = interaction.channel.permissions_for(me)
    if not cp.send_messages:
        return False, "⛔ Надад send_messages эрх алга.", False, False
    # thread бол тусдаа
    if isinstance(interaction.channel, discord.Thread):
        if hasattr(cp, "send_messages_in_threads") and not cp.send_messages_in_threads:
            return False, "⛔ Thread дотор мессеж бичих эрх алга.", False, False
    return True, None, bool(getattr(cp, "embed_links", False)), bool(getattr(cp, "attach_files", False))

def _split_fields(lines: List[str], per_field: int = 10) -> List[str]:
    return ["\n".join(lines[i:i+per_field]) for i in range(0, len(lines), per_field)]

def _chunks(seq, size):
    """seq-ийг size-ээр хэсэглэн өгнө (embed field 1024 лимит хамгаалалт)."""
    for i in range(0, len(seq or []), size):
        yield seq[i:i+size]

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

START_MATCH_BANNER = Path("assets/Start_match.png")

async def _send_with_banner(interaction: discord.Interaction, content: str, *, banner_path: Path = START_MATCH_BANNER, ephemeral: bool = False):
    ok, err, can_embed, can_attach = _check_send_perms(interaction)
    file = None
    if banner_path.exists() and can_attach:
        file = discord.File(str(banner_path), filename=banner_path.name)

    sender = interaction.response.send_message if not interaction.response.is_done() else interaction.followup.send

    if file:
        await sender(content=content, file=file, ephemeral=ephemeral)
    else:
        msg = content
        if not banner_path.exists():
            msg += f"\n_(Зураг олдсонгүй: {banner_path.as_posix()})_"
        elif not can_attach:
            msg += "\n_(attach_files эрх алга — зураг хавсаргаж чадсангүй)_"
        await sender(content=msg, ephemeral=ephemeral)

GET_SCORE_TIMEOUT = 30  # таны утгыг хадгаллаа

# тоон tier-ийг өнгө/emoji bucket руу хөрвүүлэх map
NUMERIC_TIER_TO_META = {
    5: "S",
    4: "A",
    3: "B",
    2: "C",
    1: "E",
}

TIER_META = {
    "S": {"color": 0xF59E0B, "emoji": "🏆"},
    "A": {"color": 0x22C55E, "emoji": "🟢"},
    "B": {"color": 0x3B82F6, "emoji": "🔵"},
    "C": {"color": 0x9333EA, "emoji": "🟣"},
    "D": {"color": 0xE5E7EB, "emoji": "⚪"},
    "E": {"color": 0xEF4444, "emoji": "🟥"},
}

def tier_style(tier: str) -> tuple[discord.Color, str]:
    """'3-2' / '4-1' / 'S' гэх мэт tier-ээс (Color, emoji) буцаана."""
    t = (tier or "").strip().upper()

    meta = TIER_META.get(t)
    if not meta:
        m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", t)
        if m:
            major = int(m.group(1))
            key = NUMERIC_TIER_TO_META.get(major, "E")
            meta = TIER_META.get(key, TIER_META["E"])
        else:
            meta = TIER_META["E"]

    c = meta.get("color", 0x5865F2)
    colour = discord.Color(c if isinstance(c, int) else int(str(c).lstrip("#"), 16))
    return colour, meta.get("emoji", "🔹")

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _score_progress(score: int, width: int = 18):
    """–5..+5 хүрээнд прогресс ба хувь буцаана."""
    s = _clamp(int(score), -5, 5)
    ratio = (s + 5) / 10.0
    filled = int(round(ratio * width))
    bar = "█" * filled + "░" * (width - filled)
    pct = int(round(ratio * 100))
    steps = s + 5  # 0..10
    return bar, pct, steps

def _num(n) -> str:
    try:
        return f"{int(n):,}".replace(",", " ")
    except Exception:
        return str(n)
    
KICK_VOTE_THRESHOLD = 10

async def _db_acquire(timeout: float = 2.0):
    """Pool-оос холбоод авч үзнэ; амжихгүй бол шууд connect() фоллбэк."""
    p = globals().get("pool", None)
    if p and getattr(p, "acquire", None):
        try:
            con = await asyncio.wait_for(p.acquire(), timeout=timeout)
            return con, True  # from_pool=True
        except Exception:
            pass  # pool гацсан/дүүрсэн байж болно

    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    con = await asyncpg.connect(url, command_timeout=5)
    return con, False  # from_pool=False

async def _db_release(con, from_pool: bool):
    try:
        if from_pool and globals().get("pool", None):
            await pool.release(con)
        else:
            await con.close()
    except Exception:
        pass
    
async def _insert_vote_and_count(guild_id: int, target_id: int, voter_id: int, reason: str | None):
    con, from_pool = await _db_acquire()  # ⬅️ фоллбэктэй acquire
    try:
        row = await con.fetchrow(
            """
            WITH ins AS (
              INSERT INTO kick_votes (guild_id, target_id, voter_id, reason)
              VALUES ($1,$2,$3,$4)
              ON CONFLICT (guild_id, target_id, voter_id) DO NOTHING
              RETURNING 1
            )
            SELECT
              EXISTS(SELECT 1 FROM ins) AS inserted,
              (SELECT COUNT(*)::int FROM kick_votes WHERE guild_id=$1 AND target_id=$2) AS count
            """,
            guild_id, target_id, voter_id, (reason or "")[:240],
            timeout=4
        )
        return bool(row["inserted"]), int(row["count"])
    finally:
        await _db_release(con, from_pool)

async def _can_kick(guild: discord.Guild, target: discord.Member) -> tuple[bool, str | None]:
    me = guild.me
    if target.bot:
        return False, "Ботыг vote-kick хийхгүй."
    if guild.owner_id == target.id:
        return False, "Server owner-ыг kick хийхгүй."
    if target.guild_permissions.administrator:
        return False, "Админ эрхтэй хэрэглэгчийг vote-kick хийхгүй."
    if me.top_role <= target.top_role:
        return False, "Ботын роль доогуур байна (kick хийх боломжгүй)."
    if not me.guild_permissions.kick_members:
        return False, "Ботын **Kick Members** эрх дутуу байна."
    return True, None


# 🧬 Start
@bot.event
async def on_ready():
    print(f"🤖 Bot нэвтэрлээ: {bot.user}")
    print("📁 Working directory:", os.getcwd())

    await init_pool()
    print("✅ DB pool амжилттай эхэллээ.")

    # ✅ Donor cog-оо ачаалнах (эвэрхий нь Unknown Integration-г арилгана)
    try:
        # давхар нэмэгдэхээс сэргийлж өмнө нь байвал алгасъя
        if not bot.get_cog("Donor"):
            await bot.add_cog(Donor(bot))
            print("✅ Donor cog loaded")
        else:
            print("↔️ Donor cog already loaded")
    except Exception as e:
        print("❌ Donor cog load fail:", e)

    # ⚙️ Slash командыг шууд guild рүү түр sync хийвэл шууд харагдана
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.clear_commands(guild=guild)            # хуучны үлдэгдэл цэвэрлэнэ
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"🔁 Guild sync: {len(synced)} cmds")
        # global sync нэмэлтээр (сонголт)
        await bot.tree.sync()
        print("🔁 Global sync done")
    except Exception as e:
        print("❌ Command sync failed:", e)

    asyncio.create_task(daily_nickname_refresh())
    asyncio.create_task(initialize_bot())
    asyncio.create_task(session_timeout_checker())
async def initialize_bot():
    try:
        await load_session_state()
        print("📥 Session state амжилттай ачаалагдлаа.")
    except Exception as e:
        print("❌ Session ачаалах үед алдаа гарлаа:", e)


# 🧩 Command: ping
@bot.tree.command(name="ping", description="Bot-ийн latency-г шалгана")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("🏓 Pong!")

START_MATCH_BANNER = Path("assets/Start_match.png")

@bot.tree.command(name="start_match", description="Session эхлүүлнэ (шинэ тоглолтын session)")
async def start_match(interaction: discord.Interaction):

    # 1) Interaction-ийг эхлээд acknowledge (дараа нь followup-уудаар явуулна)
    try:
        await interaction.response.defer(ephemeral=False, thinking=False)
    except discord.errors.InteractionResponded:
        pass

    # 2) Өмнөх match/session-уудыг цэвэрлэх
    try:
        await clear_last_match()
    except Exception as e:
        print("⚠️ clear_last_match алдаа:", e)

    try:
        await clear_session_state()
        print("🧼 өмнөх session_state устлаа.")
    except Exception as e:
        print("❌ clear_session_state алдаа:", e)

    # 3) Шинэ session үүсгэх (UTC ISO string-ээр хадгална)
    now = datetime.now(timezone.utc)
    session = {
        "active": True,
        "start_time": now.isoformat(),
        "last_win_time": now.isoformat(),
        "initiator_id": interaction.user.id,
        "player_ids": [],
        "teams": [],
        "changed_players": [],
        "strategy": ""
    }
    try:
        await save_session_state(session, allow_empty=True)
    except Exception as e:
        print("❌ save_session_state алдаа:", e)
        return await interaction.followup.send("⚠️ Session эхлүүлэхэд алдаа гарлаа.", ephemeral=True)

    # 4) Баннертай анхны мэдэгдэл (нийтэд харагдана)
    text = "🏁 **Match эхэллээ!** ADDME гэж бичээд бүртгүүлээрэй."
    await _send_with_banner(interaction, text, banner_path=START_MATCH_BANNER, ephemeral=False)

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
            f"- {name} — `{tier} | {score:+}` · w:`{weight}`"
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
        emb.set_footer(text=f"Tip: /go_bot эсвэл /go_gpt хийж багт хувиарлаарай")

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
                    u = int(str(u).strip())
                except Exception as e:
                    print("⚠️ sanitize: invalid id", u, e)
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

@bot.tree.command(name="my_score", description="Таны tier, score, weight-ийг харуулна")
async def my_score(interaction: discord.Interaction):
    try:
        await interaction.response.defer(thinking=True)  # public
    except discord.errors.InteractionResponded:
        return

    uid = interaction.user.id
    try:
        data = await asyncio.wait_for(get_score(uid), timeout=GET_SCORE_TIMEOUT)
    except asyncio.TimeoutError:
        return await interaction.followup.send("⏱️ Оноог авахад удааширлаа. Дахин оролдоно уу.")
    except Exception as e:
        return await interaction.followup.send(f"⚠️ Оноог уншихад алдаа: {e}")

    if not data:
        return await interaction.followup.send("⚠️ Таны оноо бүртгэлгүй байна.")

    try:
        raw_tier = str(data.get("tier", "E")).strip()
        score = int(data.get("score", 0))
        username = data.get("username") or interaction.user.display_name

        # weight (танай calculate_weight-ыг ашиглана)
        try:
            weight = int(calculate_weight(data))
        except Exception:
            base = int(TIER_WEIGHT.get(raw_tier, 0))
            weight = max(base + score, 0)

        bar, pct, steps = _score_progress(score, width=18)
        colour, emoji = tier_style(raw_tier)

        emb = discord.Embed(
            title=f"{emoji} {username}",
            description="**Таны Tier • Score • Weight**",
            colour=colour,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_thumbnail(url=interaction.user.display_avatar.url)
        emb.add_field(name="Tier",   value=f"**{raw_tier}**",    inline=True)
        emb.add_field(name="Score",  value=f"**{_num(score)}**", inline=True)
        emb.add_field(name="Weight", value=f"**{_num(weight)}**", inline=True)

        if "rank" in data:
            emb.add_field(name="Rank", value=f"#{_num(data['rank'])}", inline=True)

        stats = []
        if "wins" in data:   stats.append(f"✅ Wins: **{_num(data['wins'])}**")
        if "losses" in data: stats.append(f"❌ Losses: **{_num(data['losses'])}**")
        if "games" in data:  stats.append(f"🎮 Games: **{_num(data['games'])}**")
        if stats:
            emb.add_field(name="Товч статистик", value="\n".join(stats), inline=False)

        emb.add_field(name="Дараагийн шат хүртэл", value=f"`{bar}`  {pct}% • **{steps}/10**", inline=False)
        emb.set_footer(text=f"User ID: {uid}")

        await interaction.followup.send(embed=emb)
    except Exception as e:
        # UI рендер үеийн ямар ч алдаа энд баригдаж мессэж бууна — "уншаад алга болох" асуудлыг хаана.
        await interaction.followup.send(f"⚠️ Дэлгэцэн дээр харуулахад алдаа: {type(e).__name__}: {e}")

@bot.tree.command(name="user_score", description="Бусад тоглогчийн tier, score, weight-ийг харуулна")
@app_commands.describe(user="Оноог нь харах discord хэрэглэгч")
async def user_score(interaction: discord.Interaction, user: discord.Member):
    try:
        await interaction.response.defer(thinking=True)  # public
    except discord.errors.InteractionResponded:
        return

    uid = user.id
    try:
        data = await asyncio.wait_for(get_score(uid), timeout=GET_SCORE_TIMEOUT)
    except asyncio.TimeoutError:
        return await interaction.followup.send(f"⏱️ {user.mention} — оноог авахад удааширлаа.")
    except Exception as e:
        return await interaction.followup.send(f"⚠️ {user.mention} — оноог уншихад алдаа: {e}")

    if not data:
        return await interaction.followup.send(f"⚠️ {user.mention} — оноо бүртгэлгүй байна.")

    try:
        raw_tier = str(data.get("tier", "E")).strip()
        score = int(data.get("score", 0))
        username = data.get("username") or user.display_name

        try:
            weight = int(calculate_weight(data))
        except Exception:
            base = int(TIER_WEIGHT.get(raw_tier, 0))
            weight = max(base + score, 0)

        bar, pct, steps = _score_progress(score, width=18)
        colour, emoji = tier_style(raw_tier)

        emb = discord.Embed(
            title=f"{emoji} {username}",
            description="**Тоглогчийн Tier • Score • Weight**",
            colour=colour,
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_thumbnail(url=user.display_avatar.url)
        emb.add_field(name="Tier",   value=f"**{raw_tier}**",    inline=True)
        emb.add_field(name="Score",  value=f"**{_num(score)}**", inline=True)
        emb.add_field(name="Weight", value=f"**{_num(weight)}**", inline=True)

        if "rank" in data:
            emb.add_field(name="Rank", value=f"#{_num(data['rank'])}", inline=True)

        stats = []
        if "wins" in data:   stats.append(f"✅ Wins: **{_num(data['wins'])}**")
        if "losses" in data: stats.append(f"❌ Losses: **{_num(data['losses'])}**")
        if "games" in data:  stats.append(f"🎮 Games: **{_num(data['games'])}**")
        if stats:
            emb.add_field(name="Товч статистик", value="\n".join(stats), inline=False)

        emb.add_field(name="Дараагийн шат хүртэл", value=f"`{bar}`  {pct}% • **{steps}/10**", inline=False)
        emb.set_footer(text=f"User ID: {uid}")

        await interaction.followup.send(embed=emb)
    except Exception as e:
        await interaction.followup.send(f"⚠️ {user.mention} — дэлгэцлэх үед алдаа: {type(e).__name__}: {e}")

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
class Donor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="add_donator", description="Хандив нэмэх (нийт дүн дээр нэмэгдэнэ)")
    @app_commands.describe(member="Хэрэглэгч", amount_mnt="Хандивын дүн (MNT)")
    async def add_donator(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount_mnt: int
    ):
        # 0. permissions check
        me = interaction.guild.me
        perms = interaction.channel.permissions_for(me)
        if not perms.send_messages:
            return await interaction.response.send_message(
                "⛔ send_messages эрх дутуу байна.", ephemeral=True
            )

        can_embed = perms.embed_links
        can_attach = perms.attach_files

        await interaction.response.defer()

        # 1. DB update
        from database import upsert_donator
        try:
            await upsert_donator(member.id, amount_mnt)
        except Exception as e:
            print("❌ upsert_donator fail:", e)
            return await interaction.followup.send("⚠️ DB бичихэд алдаа гарлаа.", ephemeral=True)

        # 2. Nickname update (энэ нь get_donator_emoji-г дотроо ашиглана)
        try:
            await update_nicknames_for_users(interaction.guild, [member.id])
        except Exception as e:
            print("⚠️ nickname update fail:", e)

        # 3. Announce (image + fallback)
        text = f"{member.mention} хандив өглөө! (+{format_mnt(amount_mnt)})"

        file = None
        if can_attach:
            try:
                img = await render_donor_card(member, amount_mnt)
                file = discord.File(img, filename="donator.png")
            except Exception as e:
                print("⚠️ donor card render error:", e)

        if can_embed:
            emb = discord.Embed(
                title="🎉 Donator Added",
                description=text,
                color=0x22C55E
            )
            if file:
                emb.set_image(url="attachment://donator.png")
                return await interaction.followup.send(embed=emb, file=file)
            return await interaction.followup.send(embed=emb)

        # fallback: зөвхөн текст
        if file:
            return await interaction.followup.send(text, file=file)
        return await interaction.followup.send(text)

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
        return await interaction.followup.send("⛔️ Зөвхөн админ ашиглана.", ephemeral=True)

    try:
        # ✅ хуучны үлдэгдлийг цэвэрлэж sync
        bot.tree.clear_commands(guild=interaction.guild)
        bot.tree.copy_global_to(guild=interaction.guild)
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

@bot.tree.command(name="kick", description="Vote-kick — саналаа өгнө (10 хүрвэл kick)")
@app_commands.describe(user="Кик саналд оруулах хэрэглэгч", reason="Таны шалтгаан (сонголт)")
async def kick_cmd(interaction: discord.Interaction, user: discord.Member, reason: str = ""):
    await interaction.response.defer(ephemeral=True)

    if user.id == interaction.user.id:
        return await interaction.followup.send("😅 Өөрийгөө vote-kick хийх боломжгүй.", ephemeral=True)

    ok, why = await _can_kick(interaction.guild, user)
    if not ok:
        # Саналыг хадгалах нь OK, гэхдээ босго хүрээд ч kick болохгүйг урьдчилан хэлж өгнө
        inserted, count = await _insert_vote_and_count(interaction.guild.id, user.id, interaction.user.id, reason)
        msg = "📌 Таных бүртгэгдсэн." if inserted else "📌 Таны санал өмнө бүртгэгдсэн."
        return await interaction.followup.send(f"{msg} Нийт санал: **{count}/{KICK_VOTE_THRESHOLD}**. ⛔ {why}", ephemeral=True)

    inserted, count = await _insert_vote_and_count(interaction.guild.id, user.id, interaction.user.id, reason)
    msg = "🗳 Санал бүртгэгдлээ." if inserted else "📌 Таны санал өмнө бүртгэгдсэн."
    if count >= KICK_VOTE_THRESHOLD:
        # Босго хүрсэн тул kick оролдоно
        ok2, why2 = await _can_kick(interaction.guild, user)
        if not ok2:
            return await interaction.followup.send(f"{msg} Нийт: **{count}/{KICK_VOTE_THRESHOLD}**. ⛔ {why2}", ephemeral=True)
        try:
            await user.kick(reason=f"Vote-kick • {count}/{KICK_VOTE_THRESHOLD} vote")
            return await interaction.followup.send(
                f"{msg} ✅ **{user}** kick хийгдлээ. (Нийт {count}/{KICK_VOTE_THRESHOLD})",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.followup.send(f"{msg} ❌ Kick амжилтгүй: {e}", ephemeral=True)

    remain = KICK_VOTE_THRESHOLD - count
    await interaction.followup.send(f"{msg} Нийт: **{count}/{KICK_VOTE_THRESHOLD}**. Дутагдаж буй санал: **{remain}**.", ephemeral=True)

@bot.tree.command(name="kick_review", description="Админ: vote-kick саналуудыг харах")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    user="Зорилтот хэрэглэгчээр шүүх (сонголт)",
    limit="Жагсаалтын мөрийн тоо (default 15)",
    public="Нийтэд харагдуулах уу? (default: false)"
)
async def kick_review_cmd(
    interaction: discord.Interaction,
    user: discord.Member | None = None,
    limit: int = 15,
    public: bool = False,
):
    eph = not public
    try:
        await interaction.response.defer(ephemeral=eph)
    except discord.errors.InteractionResponded:
        pass

    # Хэтэрхий өндөр утга орж ирвэл embed талбарыг давахаас сэргийлж 25-д хавчуулна
    limit = max(1, min(limit, 25))
    DETAILS_PER_TARGET_MAX = 12  # нэг хэрэглэгчийн дор харуулах дээд мөр

    con, from_pool = await _db_acquire()
    try:
        if user:
            # --- Нэг зорилтот хэрэглэгчийн дэлгэрэнгүйг embed-ээр ---
            rows = await con.fetch(
                """
                SELECT voter_id,
                       COALESCE(NULLIF(TRIM(reason), ''), '-') AS reason,
                       created_at
                FROM kick_votes
                WHERE guild_id = $1 AND target_id = $2
                ORDER BY created_at ASC
                """,
                interaction.guild.id, user.id,
                timeout=5
            )
            if not rows:
                return await interaction.followup.send("📭 Мэдээлэл алга.", ephemeral=eph)

            emb = discord.Embed(
                title=f"Vote-kick — {user.display_name} ({len(rows)} санал)",
                description=f"{user.mention}-д өгсөн саналууд:",
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc),
            )
            lines = []
            for r in rows[:limit]:
                reason = _shorten(r["reason"], 120)
                created = r["created_at"].strftime("%Y-%m-%d %H:%M")
                lines.append(f"• <@{r['voter_id']}> — {reason}  `{created}`")
            if len(rows) > limit:
                lines.append(f"… (+{len(rows) - limit} мөр)")

            emb.add_field(name="Санал өгөгчид", value="\n".join(lines), inline=False)
            emb.set_footer(text=f"Сервер: {interaction.guild.name}")
            try:
                return await interaction.followup.send(embed=emb, ephemeral=eph)
            except discord.Forbidden:
                # Embed эрхгүй сувгийн фоллбэк — энгийн текст
                return await interaction.followup.send("\n".join(lines), ephemeral=eph)

        # --- Хураангуй: топ зорилтууд + санал өгөгчдийн богино жагсаалт (нэг асуулгаар) ---
        rows = await con.fetch(
            """
            WITH top_targets AS (
              SELECT target_id, COUNT(*)::int AS votes
              FROM kick_votes
              WHERE guild_id = $1
              GROUP BY target_id
              ORDER BY votes DESC, target_id
              LIMIT $2
            ),
            details AS (
              SELECT kv.target_id,
                     kv.voter_id,
                     COALESCE(NULLIF(TRIM(kv.reason), ''), '-') AS reason,
                     kv.created_at,
                     ROW_NUMBER() OVER (
                       PARTITION BY kv.target_id
                       ORDER BY kv.created_at ASC
                     ) AS rn
              FROM kick_votes kv
              JOIN top_targets tt ON tt.target_id = kv.target_id
              WHERE kv.guild_id = $1
            )
            SELECT tt.target_id, tt.votes,
                   d.voter_id, d.reason, d.created_at, d.rn
            FROM top_targets tt
            LEFT JOIN details d ON d.target_id = tt.target_id AND d.rn <= $3
            ORDER BY tt.votes DESC, tt.target_id, d.rn ASC
            """,
            interaction.guild.id, limit, DETAILS_PER_TARGET_MAX,
            timeout=6
        )
        if not rows:
            return await interaction.followup.send("📭 Одоогоор санал алга.", ephemeral=eph)

        # Group-лох
        grouped: dict[int, dict] = {}
        for r in rows:
            tgt = r["target_id"]; votes = r["votes"]
            g = grouped.setdefault(tgt, {"votes": votes, "details": []})
            if r["voter_id"] is not None:
                g["details"].append((r["voter_id"], r["reason"]))

        # Embed-үүд: нэг зорилтот = нэг field (уншихад амар)
        emb = discord.Embed(
            title="Vote-kick — Топ зорилтууд",
            description="Хамгийн их санал авсан хэрэглэгчид (санал өгөгч + шалтгаан):",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        for tgt, data in grouped.items():
            total = data["votes"]
            name = f"<@{tgt}> — **{total}** санал"
            # Талбарын 1024 тэмдэгт лимитийг баримталж, мөрүүдийг багцалж багтаана
            vals, cur = [], ""
            for voter_id, reason in data["details"]:
                line = f"• <@{voter_id}> — {_shorten(reason, 100)}"
                if len(cur) + len(line) + 1 > 1000:
                    vals.append(cur)
                    cur = line
                else:
                    cur = (cur + "\n" + line) if cur else line
            if cur:
                vals.append(cur)
            if total > len(data["details"]):
                extra = total - len(data["details"])
                tail = f"\n… (+{extra} санал)"
                if len(vals[-1]) + len(tail) <= 1024:
                    vals[-1] += tail
                else:
                    vals.append(tail)

            # Нэг зорилтод олон мөр багтвал хэд хэдэн field болгон хуваана
            for i, v in enumerate(vals):
                emb.add_field(
                    name=name if i == 0 else "ᅠ",  # дараагийн field-д хоосон толгой
                    value=v,
                    inline=False
                )

        emb.set_footer(text=f"Сервер: {interaction.guild.name}")
        try:
            return await interaction.followup.send(embed=emb, ephemeral=eph)
        except discord.Forbidden:
            # Embed эрхгүй сувгийн фоллбэк
            lines = ["🧾 Хамгийн их санал авсан хэрэглэгчид:"]
            for tgt, data in grouped.items():
                lines.append(f"- <@{tgt}> — **{data['votes']}** санал")
                for voter_id, reason in data["details"]:
                    lines.append(f"    · <@{voter_id}>: {_shorten(reason, 100)}")
            text = "\n".join(lines)
            if len(text) > 2000: text = text[:1990] + "…"
            return await interaction.followup.send(text, ephemeral=eph)
    finally:
        await _db_release(con, from_pool)


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

