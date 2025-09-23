# MonthlyTax.py
import os
import asyncio
import asyncpg
import datetime as dt
import discord
from discord.ext import commands, tasks
from discord import app_commands
from database import init_pool

# Tier → monthly fee map (₮)
TIERS = {1: 0, 2: 10000, 3: 15000, 4: 20000, 5: 25000}

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


GUILD_OBJ = discord.Object(id=int(GUILD_ID))

async def setup_hook():
    # 1) тухайн guild дээрх бүртгэлийг тэглээд
    try:
        bot.tree.clear_commands(guild=GUILD_OBJ)
    except Exception as e:
        print("clear guild cmds err:", e)

    # 2) локал модноос бүх командыг guild scope руу **шууд нэмнэ**
    try:
        for cmd in bot.tree.get_commands():
            bot.tree.add_command(cmd, guild=GUILD_OBJ)
        print("➕ added local cmds → guild (MonthlyTax)")
    except Exception as e:
        print("add_command err (MonthlyTax):", e)

    # 3) синк
    try:
        synced = await bot.tree.sync(guild=GUILD_OBJ)
        print(f"✅ guild sync OK (MonthlyTax): {[c.name for c in synced]}")
    except Exception as e:
        print("❌ guild sync failed (MonthlyTax):", e)

bot.setup_hook = setup_hook

# DB connection
async def db():
    return await asyncpg.connect(DATABASE_URL)

# --- Add below your imports/consts ---
FEE_BY_HEAD = {5: 25000, 4: 20000, 3: 15000, 2: 10000, 1: 0}

def _tier_head(v) -> int:
    """'4-3' -> 4, 3 -> 3, None/бусад -> 1"""
    if v is None: return 1
    if isinstance(v, int): return v if v in (1,2,3,4,5) else 1
    s = str(v)
    for ch in s:
        if ch.isdigit():
            d = int(ch)
            return d if d in (1,2,3,4,5) else 1
    return 1

def _fee_from_tier(v) -> int:
    return FEE_BY_HEAD[_tier_head(v)]

def _is_paid_by(tier_value, paid_until, status) -> bool:
    """Tier нь 1-ээр эхэлсэн бол төлбөргүй ч paid гэж үзнэ."""
    if _tier_head(tier_value) == 1:
        return True
    return bool(paid_until and paid_until >= dt.date.today() and status == "paid")

def _add_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,31,30,31,30,31,31,30,31,30,31][m-1])
    return dt.date(y, m, day)

async def _set_member_roles(guild: discord.Guild, member: discord.Member, tier: int, is_paid: bool):
    unpaid = discord.utils.get(guild.roles, name="Unpaid")
    paid = discord.utils.get(guild.roles, name=f"Paid-T{tier}")

    try:
        to_remove = [r for r in member.roles if (r.name == "Unpaid" or r.name.startswith("Paid-T"))]
        if to_remove:
            await member.remove_roles(*to_remove, reason="refresh membership")

        if is_paid and paid:
            await member.add_roles(paid, reason="membership paid")
        elif (not is_paid) and unpaid:
            await member.add_roles(unpaid, reason="membership unpaid")
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"role update failed for {member.id}: {e}")

def _split_blocks(text: str, limit: int = 1900):
    blocks, cur, n = [], [], 0
    for line in text.splitlines():
        ln = len(line) + 1
        if n + ln > limit:
            blocks.append("\n".join(cur)); cur = [line]; n = ln
        else:
            cur.append(line); n += ln
    if cur:
        blocks.append("\n".join(cur))
    return blocks

async def _fetch_members(active: bool, limit: int | None = None):
    where_active = "m.paid_until >= CURRENT_DATE AND m.status = 'paid'"
    where_inactive = "m.paid_until IS NULL OR m.paid_until < CURRENT_DATE OR m.status <> 'paid'"

    conn = await db()
    try:
        rows = await conn.fetch(f"""
            SELECT
                s.uid,
                s.username,
                s.tier,
                m.paid_until,
                COALESCE(m.status, 'unpaid') AS status
            FROM scores s
            LEFT JOIN LATERAL (
                SELECT paid_until, status
                FROM monthlyFee mf
                WHERE mf.uid = s.uid
                ORDER BY mf.paid_until DESC NULLS LAST, mf.created_at DESC
                LIMIT 1
            ) m ON TRUE
            WHERE {where_active if active else where_inactive}
            ORDER BY m.paid_until DESC NULLS LAST, s.username ASC
            {f"LIMIT {int(limit)}" if limit else ""}
        """)
    finally:
        await conn.close()
    return rows

def _format_member_rows(rows):
    # Discord msg 2000 тэмдэгт лимитийг давахгүйн тул багцалж буцаана
    lines = []
    for r in rows:
        until = r["paid_until"].isoformat() if r["paid_until"] else "—"
        # username байхгүй/урт бол mention + uid ашиглая
        uname = (r["username"] or "unknown")
        lines.append(f"- <@{r['uid']}> | {uname} | tier: {r['tier']} | until: {until}")
    return "\n".join(lines) if lines else "Жагсаалт хоосон."

@bot.event
async def on_ready():
    print(f"✅ MonthlyTax ready: {bot.user}")
    print(f"APP_ID env     : {os.getenv('DISCORD_APP_ID')}")
    print(f"bot.user       : {bot.user}   (id={bot.user.id})")
    print(f"will sync guild: {GUILD_ID}")

    try:
        # Локал мод дахь бүх slash командын нэрсийг харуулъя
        local_cmds = [c.name for c in bot.tree.get_commands()]
        print(f"LOCAL tree commands ({len(local_cmds)}): {local_cmds}")

        # Guild дээр sync хийе
        guild_obj = discord.Object(id=int(GUILD_ID))
        synced = await bot.tree.sync(guild=guild_obj)
        print(f"Membership guild sync ({len(synced)}): {[c.name for c in synced]}")
    except Exception as e:
        print("❌ Membership guild sync error:", e)

    tax_check.start()


@bot.tree.command(name="mark_paid", description="Админ: хэрэглэгчийн сарын хураамжийг бүртгэнэ")
@app_commands.describe(
    user="Хэн",
    months="Хэдэн сар (default: 1)",
    amount="Төлсөн хэмжээ (өгөхгүй бол тарифоор автоматаар)",
    note="Тайлбар/баримтын дугаар (optional)"
)
@app_commands.checks.has_permissions(administrator=True)
async def mark_paid(interaction: discord.Interaction, user: discord.Member, months: int = 1, amount: int | None = None, note: str | None = None):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild or bot.get_guild(GUILD_ID)

    conn = await db()
    try:
        # 1) tier унших
        rec = await conn.fetchrow("SELECT tier FROM scores WHERE uid=$1", user.id)
        if not rec:
            await interaction.followup.send("⚠️ Энэ хэрэглэгч `scores` хүснэгтэд байхгүй байна.", ephemeral=True)
            return
        tier_raw  = rec["tier"]           # ж: '4-3' эсвэл 4
        tier_head = _tier_head(tier_raw)  # 4

        # 2) суурь огноо
        last = await conn.fetchrow("""
            SELECT paid_until
            FROM monthlyFee
            WHERE uid=$1
            ORDER BY paid_until DESC NULLS LAST, created_at DESC
            LIMIT 1
        """, user.id)
        today = dt.date.today()
        base = last["paid_until"] if (last and last["paid_until"] and last["paid_until"] >= today) else today
        new_until = _add_months(base, months)

        # 3) amount (өгөхгүй бол дүрмээр)
        calc_amount = (_fee_from_tier(tier_raw) * months) if amount is None else amount

        # 4) insert
        await conn.execute("""
            INSERT INTO monthlyFee (uid, amount, paid_until, status, note, created_at, updated_at)
            VALUES ($1, $2, $3, 'paid', $4, now(), now())
        """, user.id, int(calc_amount), new_until, note)
    finally:
        await conn.close()

    # 5) roles
    await _set_member_roles(guild, user, tier_head, is_paid=True)

    await interaction.followup.send(
        f"✅ {user.mention} — Tier **{tier_raw}**\n"
        f"Сар: **{months}**  Төлбөр: **{calc_amount:,}₮**\n"
        f"Хүчинтэй огноо: **{new_until}**\n"
        + (f"📝 {note}" if note else ""),
        ephemeral=True
    )

@bot.tree.command(name="mark_unpaid", description="Админ: хэрэглэгчийг төлөөгүй болгож тохируулна")
@app_commands.checks.has_permissions(administrator=True)
async def mark_unpaid(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild or bot.get_guild(GUILD_ID)

    conn = await db()
    try:
        # Tier-ийг аваад толгойг нь гаргана (ж: '4-3' -> 4)
        rec = await conn.fetchrow("SELECT tier FROM scores WHERE uid=$1", user.id)
        tier_head = _tier_head(rec["tier"] if rec else None)

        # paid_until NOT NULL тул "өчигдөр" гэж тэмдэглэж дууссан төлөвт оруулна
        await conn.execute("""
            INSERT INTO monthlyFee (uid, amount, paid_until, status, note, created_at, updated_at)
            VALUES ($1, 0, CURRENT_DATE - 1, 'unpaid', 'manual-unpaid', now(), now())
        """, user.id)
    finally:
        await conn.close()

    # Ролиудыг шинэчилнэ
    await _set_member_roles(guild, user, tier_head, is_paid=False)
    await interaction.followup.send(f"🚫 {user.mention} төлбөрийн статус: **unpaid** боллоо.", ephemeral=True)

@bot.tree.command(name="players_active", description="Идэвхтэй (төлсөн) гишүүдийн жагсаалт")
@app_commands.describe(limit="Хэдийг харуулах вэ? (default 50)")
async def players_active(interaction: discord.Interaction, limit: int = 50):
    await interaction.response.defer(ephemeral=True)
    rows = await _fetch_members(active=True, limit=limit)
    body = _format_member_rows(rows)
    parts = _split_blocks(body)
    header = f"🟢 **Active members** (count: {len(rows)})\n"
    if parts:
        await interaction.followup.send(header + parts[0], ephemeral=True)
        for p in parts[1:]:
            await interaction.followup.send(p, ephemeral=True)
    else:
        await interaction.followup.send(header + "Жагсаалт хоосон.", ephemeral=True)

@bot.tree.command(name="players_inactive", description="Идэвхгүй (төлөөгүй/хугацаа дууссан) гишүүдийн жагсаалт")
@app_commands.describe(limit="Хэдийг харуулах вэ? (default 50)")
async def players_inactive(interaction: discord.Interaction, limit: int = 50):
    await interaction.response.defer(ephemeral=True)
    rows = await _fetch_members(active=False, limit=limit)
    body = _format_member_rows(rows)
    parts = _split_blocks(body)
    header = f"🔴 **Inactive members** (count: {len(rows)})\n"
    if parts:
        await interaction.followup.send(header + parts[0], ephemeral=True)
        for p in parts[1:]:
            await interaction.followup.send(p, ephemeral=True)
    else:
        await interaction.followup.send(header + "Жагсаалт хоосон.", ephemeral=True)

@bot.tree.command(name="payment_list", description="Төлбөрийн жагсаалт (эхлэх/дуусах огноогоор)")
@app_commands.describe(
    start="Эхлэх огноо (YYYY-MM-DD)",
    end="Дуусах огноо (YYYY-MM-DD)",
    user="Хэн (optional)",
    status="paid/unpaid/all",
    limit="Хэдийг харуулах вэ? (default 50)"
)
@app_commands.checks.has_permissions(administrator=True)
async def payment_list(
    interaction: discord.Interaction,
    start: str = None,
    end: str = None,
    user: discord.Member = None,
    status: str = "all",
    limit: int = 50
):
    await interaction.response.defer(ephemeral=True)

    # 1) огноо (inclusive) — end +1 өдөр хийж inclusive болгоно
    today = dt.date.today()
    try:
        d1 = dt.date.fromisoformat(start) if start else (today - dt.timedelta(days=30))
        d2 = dt.date.fromisoformat(end) if end else today
    except ValueError:
        await interaction.followup.send("⚠️ Огнооны формат буруу байна. Жишээ: 2025-09-08", ephemeral=True)
        return
    d2_excl = d2 + dt.timedelta(days=1)

    # 2) шүүлтүүд
    where = ["m.created_at >= $1", "m.created_at < $2"]
    params = [d1, d2_excl]
    if user:
        where.append("m.uid = $%d" % (len(params)+1))
        params.append(user.id)
    if status in ("paid", "unpaid"):
        where.append("m.status = $%d" % (len(params)+1))
        params.append(status)

    q = f"""
        SELECT
          m.id,
          m.uid,
          COALESCE(s.username, 'unknown') AS username,
          s.tier,
          m.amount,
          m.status,
          m.paid_until,
          m.created_at,
          m.note
        FROM monthlyFee m
        LEFT JOIN scores s ON s.uid = m.uid
        WHERE {' AND '.join(where)}
        ORDER BY m.created_at DESC
        LIMIT {int(limit)}
    """

    conn = await db()
    try:
        rows = await conn.fetch(q, *params)
    finally:
        await conn.close()

    if not rows:
        await interaction.followup.send("Жагсаалт хоосон.", ephemeral=True)
        return

    # 3) формат
    total_paid = 0
    lines = []
    for r in rows:
        ts = r["created_at"].strftime("%Y-%m-%d %H:%M")
        until = r["paid_until"].isoformat() if r["paid_until"] else "—"
        amt = r["amount"] if r["amount"] is not None else 0
        if r["status"] == "paid":
            total_paid += amt
        lines.append(
            f"- {ts} | <@{r['uid']}> | {r['username']} | tier:{r['tier']} | "
            f"{r['status']} | {amt:,}₮ | until:{until}" +
            (f" | {r['note']}" if r["note"] else "")
        )

    header = (
        f"💳 **Payments** {d1} → {d2} "
        f"{'(for ' + user.mention + ')' if user else ''}\n"
        f"Нийт мөр: **{len(rows)}**, Нийт төлбөр (paid): **{total_paid:,}₮**\n"
    )
    body = "\n".join(lines)

    # 4) Discord 2000 тэмдэгтийн лимит
    parts = _split_blocks(body)
    await interaction.followup.send(header + parts[0], ephemeral=True)
    for p in parts[1:]:
        await interaction.followup.send(p, ephemeral=True)

@bot.tree.command(name="setup_roles", description="Админ: Unpaid, Paid-T1..T5 ролиудыг үүсгэнэ")
@app_commands.checks.has_permissions(manage_roles=True)
async def setup_roles(interaction: discord.Interaction):
    guild = interaction.guild or bot.get_guild(GUILD_ID)
    created = []
    for name in ["Unpaid"] + [f"Paid-T{i}" for i in range(1, 6)]:
        if not discord.utils.get(guild.roles, name=name):
            r = await guild.create_role(name=name, mentionable=True, reason="membership bootstrap")
            created.append(r.name)
    await interaction.response.send_message(
        "✅ Roles ready. " + (f"Created: {', '.join(created)}" if created else "No new roles created."),
        ephemeral=True
    )

@bot.tree.command(name="setup_pay_channel", description="Админ: 'хураамж төлөх' сувгийг үүсгээд зөвшөөрөл тохируулна")
@app_commands.describe(channel_name="Сувгийн нэр (default: хураамж-төлөх)")
@app_commands.checks.has_permissions(manage_channels=True)
async def setup_pay_channel(interaction: discord.Interaction, channel_name: str = "хураамж-төлөх"):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild or bot.get_guild(GUILD_ID)

    ch = discord.utils.get(guild.text_channels, name=channel_name)
    if not ch:
        ch = await guild.create_text_channel(channel_name, topic="Хураамж төлөх мэдээлэл", reason="create pay channel")

    everyone = guild.default_role
    unpaid   = discord.utils.get(guild.roles, name="Unpaid")
    paid_roles = [discord.utils.get(guild.roles, name=f"Paid-T{i}") for i in range(1, 6)]

    # Бүгд харах, бичихгүй
    ow = { everyone: discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True) }
    if unpaid:
        ow[unpaid] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)

    # Paid-ууд ч бас харах, бичихгүй (админ эрхтэй нь байгалиараа бичиж чадна)
    for pr in paid_roles:
        if pr:
            ow[pr] = discord.PermissionOverwrite(view_channel=True, send_messages=False, read_message_history=True)

    await ch.edit(overwrites=ow, reason="pay channel perms")
    await interaction.followup.send(f"✅ Сувгийн зөвшөөрөл тохирлоо: #{ch.name}", ephemeral=True)

@bot.tree.command(name="apply_membership_lock", description="Админ: бүх сувгийг Paid-д нээж, Unpaid/@everyone-д хаана")
@app_commands.describe(pay_channel="'хураамж төлөх' суваг (онгорхой үлдээнэ)")
@app_commands.checks.has_permissions(manage_channels=True)
async def apply_membership_lock(interaction: discord.Interaction, pay_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild or bot.get_guild(GUILD_ID)

    everyone = guild.default_role
    unpaid   = discord.utils.get(guild.roles, name="Unpaid")
    paid_roles = [discord.utils.get(guild.roles, name=f"Paid-T{i}") for i in range(1, 6)]

    changed = 0
    for ch in guild.channels:
        # 'хураамж төлөх' сувгаа алгасна
        if ch.id == pay_channel.id:
            continue
        if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel, discord.CategoryChannel)):
            continue

        ow = { everyone: discord.PermissionOverwrite(view_channel=False) }
        if unpaid:
            ow[unpaid] = discord.PermissionOverwrite(view_channel=False)
        for pr in paid_roles:
            if pr:
                if isinstance(ch, (discord.VoiceChannel, discord.StageChannel)):
                    ow[pr] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, read_message_history=True)
                else:
                    ow[pr] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        try:
            await ch.edit(overwrites=ow, reason="membership lock")
            changed += 1
        except discord.Forbidden:
            continue

    await interaction.followup.send(f"✅ Бүх сувгийн зөвшөөрөл шинэчлэв. Нийт: **{changed}**", ephemeral=True)

# ---- FORCE SYNC VIA PREFIX COMMANDS (for debugging) ----
@bot.command(name="sync_here")
@commands.has_permissions(administrator=True)
async def sync_here(ctx: commands.Context):
    """Тухайн сервер дээрх бүх slash командыг шууд бүртгэнэ."""
    try:
        synced = await bot.tree.sync(guild=ctx.guild)
        names = ", ".join(c.name for c in synced) or "no-commands"
        await ctx.reply(f"✅ Synced to **{ctx.guild.name}**: {names}", mention_author=False)
    except Exception as e:
        await ctx.reply(f"⚠️ sync error: `{e}`", mention_author=False)

@bot.command(name="sync_global")
@commands.has_permissions(administrator=True)
async def sync_global(ctx: commands.Context):
    """Global-р бүртгэнэ (илрэхэд 1–60 мин зарцуулагдаж магадгүй)."""
    try:
        synced = await bot.tree.sync()
        names = ", ".join(c.name for c in synced) or "no-commands"
        await ctx.reply(f"🌐 Global sync ok: {names}", mention_author=False)
    except Exception as e:
        await ctx.reply(f"⚠️ global sync error: `{e}`", mention_author=False)

# өдөр бүр 1 удаа ажиллана
@tasks.loop(hours=24)
async def tax_check():
    await bot.wait_until_ready()
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    conn = await db()
    try:
        rows = await conn.fetch("""
            SELECT s.uid, s.tier, m.paid_until, m.status
            FROM scores s
            LEFT JOIN LATERAL (
                SELECT paid_until, status
                FROM monthlyFee mf
                WHERE mf.uid = s.uid
                ORDER BY mf.paid_until DESC NULLS LAST, mf.created_at DESC
                LIMIT 1
            ) m ON TRUE
        """)
    finally:
        await conn.close()

    today = dt.date.today()
    for r in rows:
        member = guild.get_member(r["uid"])
        if not member:
            try:
                member = await guild.fetch_member(r["uid"])
            except discord.NotFound:
                continue

        tier_val  = r["tier"]              # '3-2' г.м
        tier_head = _tier_head(tier_val)   # 3
        paid_until = r["paid_until"]
        status     = r["status"]
        is_paid    = _is_paid_by(tier_val, paid_until, status)

        await _set_member_roles(guild, member, tier_head, is_paid)

if __name__ == "__main__":
    bot.run(TOKEN)