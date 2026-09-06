import asyncio
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import redis
import telethon
import telethon.tl.types
from telethon import TelegramClient, events
from telethon import Button
from telethon.tl.functions.messages import ForwardMessagesRequest
from telethon.types import Message, UpdateNewMessage

from cansend import CanSend
from config import *
from terabox import get_files
from tools import (
    add_watermark,
    convert_seconds,
    download_file,
    download_image_to_bytesio,
    escape_markdown,
    extract_code_from_url,
    get_formatted_size,
    get_video_info,
    get_urls_from_string,
    is_user_on_chat,
    send_document_via_api,
    VIDEO_EXTENSIONS,
)

bot = TelegramClient("tele", API_ID, API_HASH)

db = redis.Redis(
    host=HOST,
    port=PORT,
    password=PASSWORD,
    decode_responses=True,
)

PREMIUM_SET_KEY = "premium_users"       # Redis SET — legacy, kept for /demote_all_premium
PREMIUM_EXPIRY_KEY = "premium_expiry"   # Redis HASH — user_id → expiry timestamp
BANNED_USERS_KEY = "banned_users"       # Redis SET — banned user IDs
HISTORY_KEY = "download_history"        # Redis HASH — user_id → JSON list of downloads
STATS_KEY = "bot_stats"                 # Redis HASH — total_downloads, total_users
BANNED_SET_KEY = "banned_users_set"
AUDIT_LOG_KEY = "audit_log"            # Redis LIST — recent admin actions
MAINTENANCE_KEY = "maintenance_mode"    # Redis STRING — "1" = maintenance on
COOLDOWN_KEY = "download_cooldown"     # Redis STRING — user_id → timestamp
DYNAMIC_ADMINS_KEY = "dynamic_admins"  # Redis SET — dynamically added admin IDs
CUSTOM_TAGS_KEY = "custom_tags"        # Redis HASH — user_id → custom tag
GC_USED_KEY = "gc_used"                # Redis HASH — code → "user_id:timestamp:days"
MAX_FILES_PER_REQUEST = 10
DOWNLOAD_COOLDOWN_SECONDS = 10


# ==================== DYNAMIC ADMIN SYSTEM ====================

def is_admin(user_id):
    """Check if user is admin (config + dynamic)."""
    uid = int(user_id)
    if uid in ADMINS:
        return True
    return db.sismember(DYNAMIC_ADMINS_KEY, str(uid))


def get_all_admins():
    """Return all admin IDs (config + dynamic)."""
    dynamic = db.smembers(DYNAMIC_ADMINS_KEY)
    all_admins = set(ADMINS)
    for uid in dynamic:
        all_admins.add(int(uid))
    return all_admins


def add_admin(user_id):
    """Add admin dynamically."""
    db.sadd(DYNAMIC_ADMINS_KEY, str(user_id))


def remove_admin(user_id):
    """Remove dynamic admin (can't remove config admins)."""
    db.srem(DYNAMIC_ADMINS_KEY, str(user_id))


def grant_premium(user_id, days):
    """Grant premium to user for N days from now."""
    import time as _time
    expiry = int(_time.time()) + (days * 86400)
    db.hset(PREMIUM_EXPIRY_KEY, str(user_id), expiry)
    db.sadd(PREMIUM_SET_KEY, str(user_id))


def revoke_premium(user_id):
    """Revoke premium from user."""
    db.hdel(PREMIUM_EXPIRY_KEY, str(user_id))
    db.srem(PREMIUM_SET_KEY, str(user_id))


def is_premium_user(user_id):
    """Check if user has active premium (not expired)."""
    import time as _time
    uid = str(user_id)
    if not db.hexists(PREMIUM_EXPIRY_KEY, uid):
        return False
    expiry = int(db.hget(PREMIUM_EXPIRY_KEY, uid) or 0)
    if _time.time() >= expiry:
        revoke_premium(user_id)
        return False
    return True


def get_premium_remaining(user_id):
    """Return remaining premium seconds, or 0."""
    import time as _time
    uid = str(user_id)
    expiry = int(db.hget(PREMIUM_EXPIRY_KEY, uid) or 0)
    remaining = expiry - int(_time.time())
    return max(remaining, 0)


def get_all_premium_users():
    """Return list of active premium user IDs."""
    return db.smembers(PREMIUM_SET_KEY)


def get_custom_tag(user_id):
    """Get custom tag for a user. Auto-sets owner/admin tags."""
    uid = str(user_id)
    # Auto-tag owner
    if user_id == OWNER_ID:
        tag = db.hget(CUSTOM_TAGS_KEY, uid) or "OWNER"
        db.hset(CUSTOM_TAGS_KEY, uid, tag)
        return tag
    # Auto-tag admins
    if is_admin(user_id):
        tag = db.hget(CUSTOM_TAGS_KEY, uid) or "ADMIN"
        db.hset(CUSTOM_TAGS_KEY, uid, tag)
        return tag
    return db.hget(CUSTOM_TAGS_KEY, uid) or ""


def set_custom_tag(user_id, tag):
    """Set custom tag for a user."""
    db.hset(CUSTOM_TAGS_KEY, str(user_id), tag)


def log_audit(action, admin_id, details=""):
    """Log admin action to Redis audit trail."""
    import json as _json
    entry = _json.dumps({
        "action": action,
        "admin": admin_id,
        "details": details,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    db.lpush(AUDIT_LOG_KEY, entry)
    db.ltrim(AUDIT_LOG_KEY, 0, 999)  # keep last 1000 entries


def is_maintenance():
    """Check if bot is in maintenance mode."""
    return db.get(MAINTENANCE_KEY) == "1"


def check_cooldown(user_id):
    """Check if user is on cooldown. Returns remaining seconds or 0."""
    last = db.get(f"{COOLDOWN_KEY}_{user_id}")
    if not last:
        return 0
    elapsed = time.time() - float(last)
    if elapsed < DOWNLOAD_COOLDOWN_SECONDS:
        return int(DOWNLOAD_COOLDOWN_SECONDS - elapsed)
    return 0


def set_cooldown(user_id):
    """Set download cooldown for user."""
    db.set(f"{COOLDOWN_KEY}_{user_id}", time.time(), ex=DOWNLOAD_COOLDOWN_SECONDS + 5)

# Define /info and /id commands to display user information
@bot.on(
    events.NewMessage(
        pattern="/info",
        incoming=True,
        outgoing=False,
    )
)
@bot.on(
    events.NewMessage(
        pattern="/id",
        incoming=True,
        outgoing=False,
    )
)
async def user_info(m: UpdateNewMessage):
    import time as _time
    from datetime import datetime

    user_id = m.sender_id
    name = m.sender.first_name
    username = m.sender.username if m.sender.username else "-"

    if is_premium_user(user_id):
        remaining = get_premium_remaining(user_id)
        if remaining > 9000000:
            plan = "⭐ Premium (Permanent)"
        else:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            mins = (remaining % 3600) // 60
            expiry_ts = int(_time.time()) + remaining
            expiry_str = datetime.fromtimestamp(expiry_ts).strftime("%d %b %Y, %I:%M %p")
            plan = f"⭐ Premium ({days}d {hours}h {mins}m left)\nExpires: {expiry_str}"
    else:
        plan = "🆓 Free"

    tag = get_custom_tag(user_id)
    tag_line = f"**Tag:** {tag}\n" if tag else ""

    info_text = (
        f"**Name:** {name}\n"
        f"**Username:** @{username}\n"
        f"**User ID:** `{user_id}`\n"
        f"{tag_line}"
        f"**Plan:** {plan}"
    )
    await m.reply(info_text, parse_mode="markdown", link_preview=False)


# Define /cmds or /help command to describe all available commands
# @bot.on(
#     events.NewMessage(
#         pattern="/cmds|/help",
#         incoming=True,
#         outgoing=False,
#         func=lambda x: x.is_private,
#     )
# )
# async def command_help(m: UpdateNewMessage):
#     help_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝘼𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨
# ┗━━━━━━━━━━━━━━━━━⍟

# /start - Start the bot and receive a welcome message.
# /info or /id - Get your user information.
# /redeem <gift_code> - Redeem a gift code for premium access.
# /cmds, or /help to view available cmds 
# /plan - To check availabe plan

# Directly share me the link i will share you the video with direct link

# For premium contact @abdul97233
# """
#     await m.reply(help_text)
@bot.on(
    events.NewMessage(
        pattern="/cmds|/help",
        incoming=True,
        outgoing=False,
    )
)
async def command_help(m: UpdateNewMessage):
    text = WELCOME_TEXT.format(name=m.sender.first_name)
    buttons = [
        [
            Button.inline("📥 How to Use", data="menu_howto"),
            Button.inline("📋 My Info", data="menu_info"),
        ],
        [
            Button.inline("⭐ Premium", data="menu_premium"),
            Button.inline("🎁 Redeem Card", data="menu_redeem"),
        ],
        [
            Button.inline("🛠 Tools", data="menu_tools"),
            Button.inline("🌐 Language", data="menu_lang"),
        ],
        [
            Button.url("📢 Channel", url="https://t.me/NTMpro"),
            Button.url("💬 Group", url="https://t.me/NTMchat"),
        ],
    ]
    if is_admin(m.sender_id):
        buttons.insert(2, [Button.inline("⚙️ Admin Panel", data="menu_admin")])

    await m.reply(
        text,
        link_preview=False,
        parse_mode="markdown",
        buttons=buttons,
    )

    

# Define /ping command to check bot's latency
@bot.on(
    events.NewMessage(
        pattern="/ping",
        incoming=True,
        outgoing=False,
        # func=lambda x: x.is_private,
    )
)
async def ping_pong(m: UpdateNewMessage):
    start_time = time.time()
    message = await m.reply("🖥️ Connection Status\nCommand: `/ping`\nResponse Time: Calculating...")
    end_time = time.time()
    latency = end_time - start_time  # Calculate latency in seconds
    latency_str = "{:.2f}".format(latency)  # Format latency with two decimal places
    await message.edit(f"🖥️ Connection Status\nCommand: `/ping`\nResponse Time: {latency_str} seconds")

# ==================== /gen — GENERATE GIFT CARDS ====================
# Usage: /gen <duration> [count] [tag]
# Example: /gen 7d 5 VIP → generates 5 gift codes for 7 days with VIP tag

GC_REDIS_KEY = "gift_cards"  # HASH: code → duration_days
GC_TAGS_KEY = "gc_tags"      # HASH: code → custom_tag

DURATION_MAP_GC = {
    "1d": 1, "2d": 2, "3d": 3, "5d": 5, "7d": 7,
    "1w": 7, "2w": 14, "1m": 30, "1mo": 30,
    "unlimited": 0, "perm": 0,
}

@bot.on(
    events.NewMessage(
        pattern=r"/gen\s+(\S+)(?:\s+(\d+))?(?:\s+(.+))?",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def generate_gc(m: UpdateNewMessage):
    duration_str = m.pattern_match.group(1).lower()
    count = int(m.pattern_match.group(2) or 1)
    tag = (m.pattern_match.group(3) or "").strip()

    if count > 50:
        return await m.reply("Max 50 codes at once.")

    if duration_str not in DURATION_MAP_GC:
        valid = ", ".join(DURATION_MAP_GC.keys())
        return await m.reply(
            f"Invalid duration: `{duration_str}`\n\n"
            f"Valid: `{valid}`\n\n"
            f"**Usage:** `/gen <duration> [count] [tag]`\n"
            f"Examples:\n"
            f"- `/gen 7d 5` — 5 cards, 7 days\n"
            f"- `/gen 7d 5 VIP` — 5 cards, 7 days, VIP tag\n"
            f"- `/gen unlimited 1 PREMIUM` — 1 card, permanent, PREMIUM tag"
        )

    days = DURATION_MAP_GC[duration_str]
    codes = []
    for _ in range(count):
        code = f"NTM-{str(uuid4())[:8].upper()}"
        db.hset(GC_REDIS_KEY, code, days)
        if tag:
            db.hset(GC_TAGS_KEY, code, tag)
        codes.append(code)

    duration_label = f"{days} day(s)" if days > 0 else "Permanent (Unlimited)"

    # Build redeem codes with /redeem prefix for easy copy
    redeem_lines = []
    for c in codes:
        if tag:
            redeem_lines.append(f"`/redeem {c}` (Tag: {tag})")
        else:
            redeem_lines.append(f"`/redeem {c}`")

    tag_info = f"\nTag: **{tag}**" if tag else ""

    await m.reply(
        f"**{count} Gift Card(s) Generated**\n\n"
        f"Duration: **{duration_label}**{tag_info}\n\n"
        f"**Send these to users:**\n" + "\n".join(redeem_lines),
        parse_mode="markdown",
    )


# ==================== /gclist — LIST ALL GIFT CARDS (WITH BUTTONS) ====================

GC_LIST_PER_PAGE = 10

@bot.on(
    events.NewMessage(
        pattern="/gclist",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def list_gc(m: UpdateNewMessage):
    unused = db.hgetall(GC_REDIS_KEY)
    used = db.hgetall(GC_USED_KEY)

    if not unused and not used:
        return await m.reply("No gift cards found.")

    # Build combined list: unused first, then used
    items = []
    for code, days in unused.items():
        days = int(days)
        label = "Permanent" if days == 0 else f"{days}d"
        items.append({"code": code, "status": "available", "label": label})

    for code, val in used.items():
        parts = val.split(":")
        uid = parts[0] if len(parts) > 0 else "?"
        ts = parts[1] if len(parts) > 1 else "?"
        days = int(parts[2]) if len(parts) > 2 else 0
        label = "Permanent" if days == 0 else f"{days}d"
        items.append({"code": code, "status": "used", "label": label, "user": uid, "time": ts})

    total = len(items)
    total_pages = max(1, (total + GC_LIST_PER_PAGE - 1) // GC_LIST_PER_PAGE)
    page = 1

    await _send_gc_list(m, items, page, total_pages, total)


async def _send_gc_list(m, items, page, total_pages, total):
    start = (page - 1) * GC_LIST_PER_PAGE
    end = start + GC_LIST_PER_PAGE
    page_items = items[start:end]

    unused_count = sum(1 for i in items if i["status"] == "available")
    used_count = total - unused_count

    lines = []
    for i, item in enumerate(page_items, start=start + 1):
        if item["status"] == "available":
            lines.append(f"{i}. `/redeem {item['code']}` — {item['label']} [Available]")
        else:
            user = item.get("user", "?")
            lines.append(f"{i}. `{item['code']}` — {item['label']} [Used by `{user}`]")

    text = (
        f"**Gift Cards** ({total} total)\n"
        f"Available: {unused_count} | Used: {used_count}\n"
        f"Page {page}/{total_pages}\n\n" +
        "\n".join(lines)
    )

    buttons = []
    nav = []
    if page > 1:
        nav.append(Button.inline("◀️ Prev", data=f"gcpage_{page - 1}_{total}"))
    if page < total_pages:
        nav.append(Button.inline("Next ▶️", data=f"gcpage_{page + 1}_{total}"))
    if nav:
        buttons.append(nav)
    buttons.append([Button.inline("Refresh", data=f"gcpage_{page}_{total}")])

    await m.reply(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(func=lambda e: e.data and e.data.startswith(b"gcpage_")))
async def gc_page_cb(e):
    try:
        parts = e.data.decode().split("_")
        page = int(parts[1])
        total = int(parts[2])
    except Exception:
        return await e.answer("Invalid callback data.", alert=True)

    unused = db.hgetall(GC_REDIS_KEY)
    used = db.hgetall(GC_USED_KEY)
    tags = db.hgetall(GC_TAGS_KEY)

    items = []
    for code, days in unused.items():
        days = int(days)
        label = "Permanent" if days == 0 else f"{days}d"
        tag = tags.get(code, "")
        items.append({"code": code, "status": "available", "label": label, "tag": tag})
    for code, val in used.items():
        parts = val.split(":")
        uid = parts[0] if len(parts) > 0 else "?"
        days = int(parts[2]) if len(parts) > 2 else 0
        label = "Permanent" if days == 0 else f"{days}d"
        tag = tags.get(code, "")
        items.append({"code": code, "status": "used", "label": label, "user": uid, "tag": tag})

    total_pages = max(1, (len(items) + GC_LIST_PER_PAGE - 1) // GC_LIST_PER_PAGE)
    page = min(page, total_pages)
    start = (page - 1) * GC_LIST_PER_PAGE
    end = start + GC_LIST_PER_PAGE
    page_items = items[start:end]

    unused_count = sum(1 for i in items if i["status"] == "available")
    used_count = len(items) - unused_count

    lines = []
    for i, item in enumerate(page_items, start=start + 1):
        tag_str = f" [{item.get('tag', '')}]" if item.get('tag') else ""
        if item["status"] == "available":
            lines.append(f"{i}. `/redeem {item['code']}` — {item['label']}{tag_str} [Available]")
        else:
            user = item.get("user", "?")
            lines.append(f"{i}. `{item['code']}` — {item['label']}{tag_str} [Used by `{user}`]")

    text = (
        f"**Gift Cards** ({len(items)} total)\n"
        f"Available: {unused_count} | Used: {used_count}\n"
        f"Page {page}/{total_pages}\n\n" +
        "\n".join(lines)
    )

    buttons = []
    nav = []
    if page > 1:
        nav.append(Button.inline("◀️ Prev", data=f"gcpage_{page - 1}_{len(items)}"))
    if page < total_pages:
        nav.append(Button.inline("Next ▶️", data=f"gcpage_{page + 1}_{len(items)}"))
    if nav:
        buttons.append(nav)
    buttons.append([Button.inline("Refresh", data=f"gcpage_{page}_{len(items)}")])

    await e.edit(text, parse_mode="markdown", buttons=buttons)


# ==================== /gcdel — DELETE A GIFT CARD ====================

@bot.on(
    events.NewMessage(
        pattern=r"/gcdel\s+(\S+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def delete_gc(m: UpdateNewMessage):
    code = m.pattern_match.group(1).upper()
    if db.hdel(GC_REDIS_KEY, code):
        await m.reply(f"Deleted `{code}`.")
    else:
        await m.reply(f"Code `{code}` not found.")


# ==================== /gctrack — TRACK GIFT CARD USAGE ====================

@bot.on(
    events.NewMessage(
        pattern=r"/gctrack(?:\s+(\S+))?",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def track_gc(m: UpdateNewMessage):
    filter_type = m.pattern_match.group(1)

    used = db.hgetall(GC_USED_KEY)
    if not used:
        return await m.reply("No redeemed gift cards found.")

    now = int(time.time())
    results = []

    for code, val in used.items():
        parts = val.split(":")
        uid = parts[0] if len(parts) > 0 else "?"
        ts = int(parts[1]) if len(parts) > 1 else 0
        days = int(parts[2]) if len(parts) > 2 else 0

        age_hours = (now - ts) / 3600 if ts else 0
        label = "Permanent" if days == 0 else f"{days}d"
        from datetime import datetime
        time_str = datetime.fromtimestamp(ts).strftime("%d %b %Y, %I:%M %p") if ts else "?"

        entry = {
            "code": code, "user": uid, "days": label,
            "time": time_str, "age_hours": round(age_hours, 1),
        }

        if filter_type == "1h" and age_hours > 1:
            continue
        elif filter_type == "24h" and age_hours > 24:
            continue
        elif filter_type == "7d" and age_hours > 168:
            continue
        elif filter_type and filter_type.isdigit():
            if uid != filter_type:
                continue
        elif filter_type:
            if code.upper() != filter_type.upper():
                continue

        results.append(entry)

    if not results:
        return await m.reply("No matching gift cards found.")

    lines = []
    for r in results:
        lines.append(
            f"`{r['code']}` — {r['days']}\n"
            f"  User: `{r['user']}`\n"
            f"  Time: {r['time']} ({r['age_hours']}h ago)"
        )

    text = f"**Gift Card Usage** ({len(results)} found)\n\n" + "\n\n".join(lines)
    if len(text) > 3000:
        text = text[:3000] + "\n\n... (truncated)"

    buttons = [
        [Button.inline("Last 1h", data="gctrack_1h"),
         Button.inline("Last 24h", data="gctrack_24h"),
         Button.inline("Last 7d", data="gctrack_7d")],
        [Button.inline("All", data="gctrack_all")],
    ]

    await m.reply(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(func=lambda e: e.data and e.data.startswith(b"gctrack_")))
async def gctrack_cb(e):
    try:
        filter_type = e.data.decode().split("_", 1)[1]
    except Exception:
        return await e.answer("Invalid callback data.", alert=True)

    used = db.hgetall(GC_USED_KEY)
    now = int(time.time())
    results = []

    for code, val in used.items():
        parts = val.split(":")
        uid = parts[0] if len(parts) > 0 else "?"
        ts = int(parts[1]) if len(parts) > 1 else 0
        days = int(parts[2]) if len(parts) > 2 else 0

        age_hours = (now - ts) / 3600 if ts else 0
        label = "Permanent" if days == 0 else f"{days}d"
        from datetime import datetime
        time_str = datetime.fromtimestamp(ts).strftime("%d %b %Y, %I:%M %p") if ts else "?"

        if filter_type == "1h" and age_hours > 1:
            continue
        elif filter_type == "24h" and age_hours > 24:
            continue
        elif filter_type == "7d" and age_hours > 168:
            continue

        results.append({
            "code": code, "user": uid, "days": label,
            "time": time_str, "age_hours": round(age_hours, 1),
        })

    if not results:
        return await e.answer("No results for this filter.", alert=True)

    lines = []
    for r in results:
        lines.append(
            f"`{r['code']}` — {r['days']}\n"
            f"  User: `{r['user']}`\n"
            f"  Time: {r['time']} ({r['age_hours']}h ago)"
        )

    text = f"**Gift Card Usage** ({len(results)} found)\n\n" + "\n\n".join(lines)
    if len(text) > 3000:
        text = text[:3000] + "\n\n... (truncated)"

    buttons = [
        [Button.inline("Last 1h", data="gctrack_1h"),
         Button.inline("Last 24h", data="gctrack_24h"),
         Button.inline("Last 7d", data="gctrack_7d")],
        [Button.inline("All", data="gctrack_all")],
    ]

    await e.edit(text, parse_mode="markdown", buttons=buttons)


# ==================== /redeem — REDEEM GIFT CARD ====================

@bot.on(
    events.NewMessage(
        pattern=r"/redeem\s+(\S+)",
        incoming=True,
        outgoing=False,
    )
)
async def redeem_gc(m: UpdateNewMessage):
    code = m.pattern_match.group(1).upper()
    user_id = m.sender_id

    # Check if user already redeemed AND still has active premium
    if db.get(f"gc_redeemed_{user_id}") and is_premium_user(user_id):
        return await m.reply(
            "You have already redeemed a gift card and your premium is still active.\n"
            "Each user can only redeem **1 gift card** while premium is active.\n"
            "Wait for expiry or contact admin."
        )

    days_str = db.hget(GC_REDIS_KEY, code)

    if not days_str:
        return await m.reply("Invalid or already used gift card.")

    days = int(days_str)
    # Get tag before deleting
    tag = db.hget(GC_TAGS_KEY, code) or ""
    db.hdel(GC_REDIS_KEY, code)
    db.hdel(GC_TAGS_KEY, code)
    # Track who used this code
    db.hset(GC_USED_KEY, code, f"{user_id}:{int(time.time())}:{days}")
    # Mark user as having redeemed a gift card (permanent record)
    db.set(f"gc_redeemed_{user_id}", "1")

    # Apply tag if gift card had one
    if tag:
        set_custom_tag(user_id, tag)

    tag_info = f"\nTag: **{tag}**" if tag else ""

    if days == 0:
        grant_premium(user_id, 99999)
        await m.reply(
            f"Gift card redeemed!\n\n"
            f"**Premium: Unlimited**\n"
            f"Duration: Permanent (never expires){tag_info}",
            parse_mode="markdown",
        )
    else:
        grant_premium(user_id, days)
        import time as _time
        from datetime import datetime
        expiry = int(_time.time()) + (days * 86400)
        expiry_str = datetime.fromtimestamp(expiry).strftime("%d %b %Y, %I:%M %p")
        await m.reply(
            f"Gift card redeemed!\n\n"
            f"**Premium: {days} day(s)**\n"
            f"Expires: `{expiry_str}`{tag_info}",
            parse_mode="markdown",
        )

    # Notify admins
    user = await bot.get_entity(m.sender_id)
    name = user.first_name
    username = user.username if user.username else "-"
    tag_msg = f"\nTag: {tag}" if tag else ""
    for admin_id in get_all_admins():
        await bot.send_message(
            admin_id,
            f"Gift Card Redeemed!\nUser: {name} (@{username})\nID: `{m.sender_id}`\nCode: `{code}`\nDuration: {days}d{tag_msg}"
        )


# ==================== /allowredeem — OWNER RESETS USER GC REDEMPTION ====================

@bot.on(
    events.NewMessage(
        pattern=r"/allowredeem\s+(\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def allow_redeem(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    db.delete(f"gc_redeemed_{user_id}")
    log_audit("ALLOW_REDEEM", m.sender_id, f"Reset GC redemption for {user_id}")
    await m.reply(f"User `{user_id}` can now redeem another gift card.")


# ==================== /settag — SET CUSTOM TAG ====================

@bot.on(
    events.NewMessage(
        pattern=r"/settag\s+(\d+)\s+(.+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def set_tag_cmd(m: UpdateNewMessage):
    user_id = int(m.pattern_match.group(1))
    tag = m.pattern_match.group(2).strip()
    set_custom_tag(user_id, tag)
    log_audit("SET_TAG", m.sender_id, f"Set tag '{tag}' for {user_id}")
    await m.reply(f"Tag set!\nUser: `{user_id}`\nTag: **{tag}**", parse_mode="markdown")


# ==================== /tag — VIEW YOUR TAG ====================

@bot.on(
    events.NewMessage(
        pattern="/tag",
        incoming=True,
        outgoing=False,
    )
)
async def view_tag_cmd(m: UpdateNewMessage):
    tag = get_custom_tag(m.sender_id)
    if tag:
        await m.reply(f"Your tag: **{tag}**", parse_mode="markdown")
    else:
        await m.reply("You have no custom tag.\nAdmins can set one with `/settag <user_id> <tag>`")


@bot.on(
    events.NewMessage(
        pattern="/broadcast",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def broadcast_message(m: UpdateNewMessage):
    broadcast_text = m.text.split("/broadcast", 1)[1].strip()
    if not broadcast_text:
        return await m.reply(
            "**Usage:** `/broadcast <message>`\n"
            "Send a message to all bot users."
        )

    status = await m.reply("Broadcasting...")

    all_users = await bot.get_participants(-1001336746488)
    total = len(all_users)
    sent = 0
    failed = 0

    for user in all_users:
        try:
            await bot.send_message(user.id, broadcast_text)
            sent += 1
        except Exception:
            failed += 1

    await status.edit(
        f"**Broadcast Complete**\n\n"
        f"Total users: **{total}**\n"
        f"Sent: **{sent}**\n"
        f"Failed: **{failed}**",
        parse_mode="markdown",
    )


# Define start command to check user's plan and send welcome message accordingly
# @bot.on(
#     events.NewMessage(
#         pattern="/start",
#         incoming=True,
#         outgoing=False,
#     )
# )
# async def start(m: UpdateNewMessage):
#     user_id = m.sender_id
#     if db.sismember(PREMIUM_USERS_KEY, user_id):
#         # Premium user
#         reply_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
# ┗━━━━━━━━━━━━━━━━━⍟
# ╔══════════⍟
# ┃🌟 Welcome! 🌟
# ┃
# ┃Excited to introduce Tera Box video downloader bot! 🤖 
# ┃Simply share the terabox link, and voila! 
# ┃Your desired video will swiftly start downloading. 
# ┃It's that easy! 🚀
# ╚═════════════════⍟
# Do /help or /cmds - Display available commands.

# [『 𝗡⋆𝗧⋆𝗠 』](https://t.me/NTMpro) 
# """
#     else:
#         # Free user
#         reply_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝐅𝐑𝐄𝐄 𝐔𝐒𝐄𝐑 
# ┗━━━━━━━━━━━━━━━━━⍟
# ╔══════════⍟ 
# ┃ As a free user, 
# ┃ you're not approved to access the full capabilities of this bot.
# ┃
# ┃ Upgrade to premium or utilize /id, /cmds, or /help to view available details. 
# ┃
# ┃ To check availabe plan do /plan in chat group @NTMchat
# ╚═════════════════⍟
# For subscription inquiries, contact @abdul97233.
# """

#     # Send the welcome message
#     check_if = await is_user_on_chat(bot, "@NTMpro", m.peer_id)
#     if not check_if:
#         return await m.reply("Please join @NTMpro then send me the link again.")
#     await m.reply(reply_text, link_preview=False, parse_mode="markdown")

# ==================== /start — MODERN BUTTON MENU ====================

WELCOME_TEXT = """
┏━━━━━━━━━━━━━━━━━⍟
┃  𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫
┗━━━━━━━━━━━━━━━━━━━━━⍟

👋 Welcome **{name}**!

Simply send me a **TeraBox link** and I'll download the video for you instantly.

⚡ Free: 10 downloads/hour
⭐ Premium: Unlimited + no limits

Choose an option below 👇
"""

@bot.on(
    events.NewMessage(
        pattern="/start",
        incoming=True,
        outgoing=False,
    )
)
async def start(m: UpdateNewMessage):
    user_id = m.sender_id
    user = await bot.get_entity(user_id)
    name = user.first_name

    # Notify admins
    admin_message = f"👤 New user started bot:\nName: {name}\nUsername: @{user.username or '-'}\nID: `{user_id}`"
    for admin_id in get_all_admins():
        try:
            await bot.send_message(admin_id, admin_message)
        except Exception:
            pass

    plan = "⭐ Premium" if is_premium_user(user_id) else "🆓 Free"
    remaining = ""
    if is_premium_user(user_id):
        rem = get_premium_remaining(user_id)
        if rem > 9000000:
            remaining = " ♾️ Permanent"
        else:
            days = rem // 86400
            hours = (rem % 86400) // 3600
            remaining = f" ({days}d {hours}h left)"

    text = WELCOME_TEXT.format(name=name)

    buttons = [
        [
            Button.inline("📥 How to Use", data="menu_howto"),
            Button.inline("📋 My Info", data="menu_info"),
        ],
        [
            Button.inline("⭐ Premium", data="menu_premium"),
            Button.inline("🎁 Redeem Card", data="menu_redeem"),
        ],
        [
            Button.inline("🛠 Tools", data="menu_tools"),
            Button.inline("🌐 Language", data="menu_lang"),
        ],
        [
            Button.url("📢 Channel", url="https://t.me/NTMpro"),
            Button.url("💬 Group", url="https://t.me/NTMchat"),
        ],
    ]

    if user_id in ADMINS:
        buttons.insert(2, [
            Button.inline("⚙️ Admin Panel", data="menu_admin"),
        ])

    await m.reply(
        text,
        link_preview=False,
        parse_mode="markdown",
        buttons=buttons,
    )


# ==================== CALLBACK HANDLERS ====================

@bot.on(events.CallbackQuery(data=b"menu_howto"))
async def cb_howto(e):
    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  📥 𝐇𝐨𝐰 𝐭𝐨 𝐔𝐬𝐞
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Step 1:** Join our Channel & Group
**Step 2:** Send me any TeraBox link
**Step 3:** Wait for the magic! ✨

**Supported formats:**
mp4, mkv, webm, mov, avi, flv, wmv, m4v, mpg, mpeg, 3gp, ts, and more...

**Commands:**
`/dl <link>` — Download original
`/dl 720p <link>` — Download + compress 720p
`/dl 480p <link>` — Download + compress 480p
`/folder <link>` — Download entire folder
`/mp3` — Reply to video → extract audio
`/compress` — Reply to video → compress
"""
    buttons = [[Button.inline("◀️ Back", data="menu_main")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_info"))
async def cb_info(e):
    user_id = e.sender_id
    user = await bot.get_entity(user_id)
    name = user.first_name
    username = user.username or "-"

    if is_premium_user(user_id):
        rem = get_premium_remaining(user_id)
        if rem > 9000000:
            plan = "⭐ Premium (Permanent)"
        else:
            days = rem // 86400
            hours = (rem % 86400) // 3600
            mins = (rem % 3600) // 60
            plan = f"⭐ Premium ({days}d {hours}h {mins}m)"
    else:
        plan = "🆓 Free"

    downloads = int(db.hget(STATS_KEY, "total_downloads") or 0)

    text = f"""
┏━━━━━━━━━━━━━━━━━⍟
┃  📋 𝐌𝐲 𝐈𝐧𝐟𝐨
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Name:** {name}
**Username:** @{username}
**User ID:** `{user_id}`
**Plan:** {plan}
"""
    buttons = [
        [Button.inline("📜 Download History", data="menu_history")],
        [Button.inline("◀️ Back", data="menu_main")],
    ]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_history"))
async def cb_history(e):
    import json as _json
    raw = db.get(f"history_{e.sender_id}")
    if not raw:
        text = "📭 No download history yet."
    else:
        history = _json.loads(raw)
        lines = []
        for i, entry in enumerate(reversed(history[-10:]), 1):
            en = _json.loads(entry)
            lines.append(f"{i}. `{en['file'][:30]}` ({en['size']})")
        text = f"**📜 Last {len(lines)} Downloads:**\n\n" + "\n".join(lines)

    buttons = [[Button.inline("◀️ Back", data="menu_info")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_premium"))
async def cb_premium(e):
    user_id = e.sender_id
    if is_premium_user(user_id):
        rem = get_premium_remaining(user_id)
        if rem > 9000000:
            status = "♾️ **Permanent Premium**"
        else:
            days = rem // 86400
            hours = (rem % 86400) // 3600
            status = f"⏰ **Active** — {days}d {hours}h remaining"
    else:
        status = "🆓 **Free Plan**"

    text = f"""
┏━━━━━━━━━━━━━━━━━⍟
┃  ⭐ 𝐏𝐫𝐞𝐦𝐢𝐮𝐦
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Your Status:** {status}

**Free Plan:**
• 10 downloads/hour
• Single file only
• 500MB size limit

**Premium Plan:**
• ✅ Unlimited downloads
• ✅ Multi-file support
• ✅ No size limit
• ✅ Priority speed
• ✅ Custom thumbnail
• ✅ Folder download

Contact @abdul97233 to purchase.
"""
    buttons = [
        [Button.inline("🎁 Redeem Gift Card", data="menu_redeem")],
        [Button.inline("◀️ Back", data="menu_main")],
    ]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_redeem"))
async def cb_redeem(e):
    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  🎁 𝐑𝐞𝐝𝐞𝐞𝐦 𝐆𝐢𝐟𝐭 𝐂𝐚𝐫𝐝
┗━━━━━━━━━━━━━━━━━━━━━⍟

Send your gift card code like this:

`/redeem NTM-XXXXXXXX`

You will receive premium instantly!
"""
    buttons = [[Button.inline("◀️ Back", data="menu_main")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_tools"))
async def cb_tools(e):
    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  🛠 𝐓𝐨𝐨𝐥𝐬
┗━━━━━━━━━━━━━━━━━━━━━⍟

**📥 Download Tools:**
`/dl <link>` — Download original
`/dl 720p <link>` — Download + compress 720p
`/dl 480p <link>` — Download + compress 480p
`/folder <link>` — Entire folder (⭐)

**🎵 Media Tools:**
`/mp3` — Reply to video → Audio
`/compress` — Reply to video → Compress
`/compress low` — Low quality compress

**🎨 Customization:**
`/setthumb` — Set custom thumbnail (⭐)
`/removethumb` — Remove thumbnail
`/lang ne` — Set language (en/ne/hi)
"""
    buttons = [[Button.inline("◀️ Back", data="menu_main")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_lang"))
async def cb_lang(e):
    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  🌐 𝐒𝐞𝐭 𝐋𝐚𝐧𝐠𝐮𝐚𝐠𝐞
┗━━━━━━━━━━━━━━━━━━━━━⍟

Choose your preferred language:
"""
    buttons = [
        [
            Button.inline("English 🇬🇧", data="setlang_en"),
            Button.inline("नेपाली 🇳🇵", data="setlang_ne"),
        ],
        [
            Button.inline("हिन्दी 🇮🇳", data="setlang_hi"),
        ],
        [Button.inline("◀️ Back", data="menu_main")],
    ]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(pattern=b"setlang_"))
async def cb_setlang(e):
    lang_code = e.data.decode().replace("setlang_", "")
    db.set(f"{LANG_KEY}_{e.sender_id}", lang_code)
    lang_name = LANGUAGES.get(lang_code, "English")
    await e.answer(f"Language set to {lang_name}!", alert=False)
    # Refresh main menu
    user = await bot.get_entity(e.sender_id)
    text = WELCOME_TEXT.format(name=user.first_name)
    buttons = [
        [
            Button.inline("📥 How to Use", data="menu_howto"),
            Button.inline("📋 My Info", data="menu_info"),
        ],
        [
            Button.inline("⭐ Premium", data="menu_premium"),
            Button.inline("🎁 Redeem Card", data="menu_redeem"),
        ],
        [
            Button.inline("🛠 Tools", data="menu_tools"),
            Button.inline("🌐 Language", data="menu_lang"),
        ],
        [
            Button.url("📢 Channel", url="https://t.me/NTMpro"),
            Button.url("💬 Group", url="https://t.me/NTMchat"),
        ],
    ]
    if is_admin(e.sender_id):
        buttons.insert(2, [Button.inline("⚙️ Admin Panel", data="menu_admin")])
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"menu_main"))
async def cb_main(e):
    user = await bot.get_entity(e.sender_id)
    text = WELCOME_TEXT.format(name=user.first_name)
    buttons = [
        [
            Button.inline("📥 How to Use", data="menu_howto"),
            Button.inline("📋 My Info", data="menu_info"),
        ],
        [
            Button.inline("⭐ Premium", data="menu_premium"),
            Button.inline("🎁 Redeem Card", data="menu_redeem"),
        ],
        [
            Button.inline("🛠 Tools", data="menu_tools"),
            Button.inline("🌐 Language", data="menu_lang"),
        ],
        [
            Button.url("📢 Channel", url="https://t.me/NTMpro"),
            Button.url("💬 Group", url="https://t.me/NTMchat"),
        ],
    ]
    if is_admin(e.sender_id):
        buttons.insert(2, [Button.inline("⚙️ Admin Panel", data="menu_admin")])
    await e.edit(text, parse_mode="markdown", buttons=buttons)


# ==================== ADMIN PANEL BUTTONS ====================

@bot.on(events.CallbackQuery(data=b"menu_admin"))
async def cb_admin(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  ⚙️ 𝐀𝐝𝐦𝐢𝐧 𝐏𝐚𝐧𝐞𝐥
┗━━━━━━━━━━━━━━━━━━━━━⍟

Choose an admin action 👇
"""
    buttons = [
        [
            Button.inline("📊 Stats", data="admin_stats"),
            Button.inline("💻 Usage", data="admin_usage"),
        ],
        [
            Button.inline("⭐ Premium Mgmt", data="admin_premium"),
            Button.inline("🎁 Gift Cards", data="admin_gc"),
        ],
        [
            Button.inline("🏷 Tags", data="admin_tags"),
            Button.inline("🚫 Ban Users", data="admin_ban"),
        ],
        [
            Button.inline("📝 Logs", data="admin_logs"),
            Button.inline("📢 Broadcast", data="admin_broadcast"),
        ],
        [
            Button.inline("💾 Backup", data="admin_backup"),
        ],
        [Button.inline("◀️ Back", data="menu_main")],
    ]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_stats"))
async def cb_admin_stats(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    total_downloads = int(db.hget(STATS_KEY, "total_downloads") or 0)
    total_users = int(db.hget(STATS_KEY, "total_users") or 0)
    premium_count = len(db.smembers(PREMIUM_SET_KEY))
    banned_count = len(db.smembers(BANNED_USERS_KEY))
    gc_count = db.hlen(GC_REDIS_KEY)
    today_key = f"active_{time.strftime('%Y-%m-%d')}"
    active_today = int(db.get(today_key) or 0)

    text = f"""
┏━━━━━━━━━━━━━━━━━⍟
┃  📊 𝐁𝐨𝐭 𝐒𝐭𝐚𝐭𝐢𝐬𝐭𝐢𝐜𝐬
┗━━━━━━━━━━━━━━━━━━━━━⍟

📥 **Total Downloads:** {total_downloads}
👤 **Total Users:** {total_users}
🟢 **Active Today:** {active_today}
⭐ **Premium:** {premium_count}
🚫 **Banned:** {banned_count}
🎁 **Gift Cards:** {gc_count}
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_usage"))
async def cb_admin_usage(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    import shutil
    import platform
    disk = shutil.disk_usage("/")
    disk_used = round(disk.used / (1024**3), 2)
    disk_total = round(disk.total / (1024**3), 2)
    disk_pct = round((disk.used / disk.total) * 100, 1)

    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    mem[parts[0]] = int(parts[1]) // 1024
        ram_used = mem.get("MemTotal:", 0) - mem.get("MemAvailable:", 0)
        ram_total = mem.get("MemTotal:", 0)
        ram_pct = round((ram_used / ram_total) * 100, 1) if ram_total else 0
    except Exception:
        ram_used = ram_total = ram_pct = 0

    dl_size = 0
    dl_count = 0
    if os.path.isdir(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            fp = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fp):
                dl_size += os.path.getsize(fp)
                dl_count += 1

    text = f"""
┏━━━━━━━━━━━━━━━━━⍟
┃  💻 𝐑𝐞𝐬𝐨𝐮𝐫𝐜𝐞 𝐔𝐬𝐚𝐠𝐞
┗━━━━━━━━━━━━━━━━━━━━━⍟

💾 **Disk:** {disk_used}GB / {disk_total}GB ({disk_pct}%)
🧠 **RAM:** {ram_used}MB / {ram_total}MB ({ram_pct}%)
📁 **Downloads:** {dl_count} files ({round(dl_size/1048576, 1)}MB)
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_premium"))
async def cb_admin_premium(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  ⭐ 𝐏𝐫𝐞𝐦𝐢𝐮𝐦 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Commands:**
`/pre <user_id> <duration>` — Promote
`/de <user_id>` — Demote
`/premium_users` — List all
`/demote_all_premium` — Remove all

**Duration:** 1d, 2d, 3d, 5d, 7d, 1w, 2w, 1m, unlimited
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_gc"))
async def cb_admin_gc(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  🎁 𝐆𝐢𝐟𝐭 𝐂𝐚𝐫𝐝 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Commands:**
`/gen <duration> [count]` — Generate cards
`/gclist` — List all cards (with buttons)
`/gctrack` — Track who used cards
`/gctrack 24h` — Cards used last 24h
`/gctrack <user_id>` — Cards used by user
`/gcdel <code>` — Delete a card
`/allowredeem <user_id>` — Reset user redemption

**Duration:** 1d, 2d, 3d, 5d, 7d, 1w, 2w, 1m, unlimited
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_tags"))
async def cb_admin_tags(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  🏷 𝐓𝐚𝐠 𝐌𝐚𝐧𝐚𝐠𝐞𝐦𝐞𝐧𝐭
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Commands:**
`/settag <user_id> <tag>` — Set custom tag
`/tag` — View your own tag

**Auto Tags:**
Owner and Admins get auto-tagged if no custom tag set.
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_ban"))
async def cb_admin_ban(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    banned = db.smembers(BANNED_USERS_KEY)
    if banned:
        lines = []
        for uid in list(banned)[:10]:
            try:
                user = await bot.get_entity(int(uid))
                lines.append(f"• {user.first_name} — `{uid}`")
            except Exception:
                lines.append(f"• Unknown — `{uid}`")
        ban_list = "\n".join(lines)
    else:
        ban_list = "No banned users."

    text = f"""
┏━━━━━━━━━━━━━━━━━⍟
┃  🚫 𝐁𝐚𝐧 𝐔𝐬𝐞𝐫𝐬
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Current banned:**
{ban_list}

**Commands:**
`/ban <user_id>` — Ban
`/unban <user_id>` — Unban
`/banned_users` — List all
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_logs"))
async def cb_admin_logs(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  📝 𝐋𝐨𝐠𝐬
┗━━━━━━━━━━━━━━━━━━━━━⍟

Use: `/logs` or `/logs 50`
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_broadcast"))
async def cb_admin_broadcast(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  📢 𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭
┗━━━━━━━━━━━━━━━━━━━━━⍟

**Commands:**
`/broadcast <message>` — Send now
`/announce <minutes> <msg>` — Schedule delay
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)


@bot.on(events.CallbackQuery(data=b"admin_backup"))
async def cb_admin_backup(e):
    if not is_admin(e.sender_id):
        return await e.answer("Access denied!", alert=True)

    text = """
┏━━━━━━━━━━━━━━━━━⍟
┃  💾 𝐁𝐚𝐜𝐤𝐮𝐩
┗━━━━━━━━━━━━━━━━━━━━━⍟

Use: `/backup`
Exports all Redis data to a JSON file.
"""
    buttons = [[Button.inline("◀️ Back", data="menu_admin")]]
    await e.edit(text, parse_mode="markdown", buttons=buttons)
# Handler for when a user joins the chat
@bot.on(events.ChatAction)
async def user_joined(event):
    if event.user_joined:
        user_id = event.user_id
        user = await bot.get_entity(user_id)
        name = user.first_name
        username = user.username if user.username else "-"
        
        admin_message = f"User joined the bot:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
        for admin_id in get_all_admins():
            await bot.send_message(admin_id, admin_message)

@bot.on(
    events.NewMessage(
        pattern="/remove (.*)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def remove(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    if db.get(f"check_{user_id}"):
        db.delete(f"check_{user_id}")
        await m.reply(f"Removed {user_id} from the list.")
    else:
        await m.reply(f"{user_id} is not in the list.")
        

# Define /plan command to display premium plans and payment methods
@bot.on(
    events.NewMessage(
        pattern="/plan",
        incoming=True,
        outgoing=False,
    )
)
async def display_plan(m: UpdateNewMessage):
    plan_text = """
┏━━━━━━━━━━━━━━━━━⍟
┃ 𝐓𝐄𝐑𝐀 𝐁𝐎𝐗 𝐁𝐎𝐓
┗━━━━━━━━━━━━━━━━━━━━━⍟

🌟 **Free Plan**
• 10 downloads/hour
• Single file only
• 500MB size limit

⚡ **Premium Plan**
• Unlimited downloads
• Multi-file support
• No size limit
• Priority speed

Contact @abdul97233 for premium.
"""
    await m.reply(plan_text, parse_mode="markdown")

# ==================== /pre — PROMOTE WITH DURATION ====================
# Usage: /pre <user_id> <duration>
# Duration: 1d, 2d, 3d, 5d, 7d, 14d, 30d, unlimited

DURATION_MAP = {
    "1d": 1, "2d": 2, "3d": 3, "5d": 5, "7d": 7,
    "1w": 7, "2w": 14, "1m": 30, "1mo": 30,
    "unlimited": 0, "0": 0, "perm": 0,
}

@bot.on(
    events.NewMessage(
        pattern=r"/pre\s+(\d+)\s+(\S+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def pre(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    duration_str = m.pattern_match.group(2).lower()

    if duration_str not in DURATION_MAP:
        valid = ", ".join(DURATION_MAP.keys())
        return await m.reply(
            f"Invalid duration: `{duration_str}`\n\n"
            f"Valid: `{valid}`\n\n"
            f"**Usage:** `/pre <user_id> <duration>`\n"
            f"Example: `/pre 123456 7d`"
        )

    days = DURATION_MAP[duration_str]

    if days == 0:
        grant_premium(user_id, 99999)
        await m.reply(
            f"✅ **{user_id}** promoted to **permanent premium**."
        )
    else:
        grant_premium(user_id, days)
        import time as _time
        expiry = int(_time.time()) + (days * 86400)
        from datetime import datetime
        expiry_str = datetime.fromtimestamp(expiry).strftime("%d %b %Y, %I:%M %p")
        await m.reply(
            f"✅ **{user_id}** promoted to premium for **{days} day(s)**.\n"
            f"Expires: `{expiry_str}`"
        )


# ==================== /de — REVOKE PREMIUM ====================

@bot.on(
    events.NewMessage(
        pattern=r"/de\s+(\d+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def de(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    if is_premium_user(user_id):
        revoke_premium(user_id)
        await m.reply(f"✅ Revoked premium from **{user_id}**.")
    else:
        await m.reply(f"**{user_id}** is not a premium user.")


# ==================== /premium_users — LIST ALL ====================

@bot.on(
    events.NewMessage(
        pattern="/premium_users",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def premium_users_cmd(m: UpdateNewMessage):
    import time as _time
    from datetime import datetime

    all_users = get_all_premium_users()
    if not all_users:
        return await m.reply("No premium users found.")

    lines = []
    for user_id in all_users:
        try:
            user = await bot.get_entity(int(user_id))
            name = user.first_name
            username = user.username if user.username else "-"
        except Exception:
            name = "Unknown"
            username = "-"

        remaining = get_premium_remaining(int(user_id))
        if remaining == 0:
            status = "❌ Expired"
            revoke_premium(user_id)
            continue
        elif remaining > 9000000:
            status = "♾️ Permanent"
        else:
            days = remaining // 86400
            hours = (remaining % 86400) // 3600
            status = f"⏰ {days}d {hours}h left"

        lines.append(
            f"• {name} (@{username})\n"
            f"  ID: `{user_id}`\n"
            f"  Status: {status}"
        )

    await m.reply(
        f"**Premium Users ({len(lines)}):**\n\n" + "\n\n".join(lines),
        parse_mode="markdown",
    )


# ==================== /demote_all_premium ====================

@bot.on(
    events.NewMessage(
        pattern="/demote_all_premium",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def demote_all_premium(m: UpdateNewMessage):
    db.delete(PREMIUM_SET_KEY)
    db.delete(PREMIUM_EXPIRY_KEY)
    await m.reply("All premium users demoted successfully.")


@bot.on(
    events.NewMessage(
        incoming=True,
        outgoing=False,
        func=lambda message: message.text
        and not message.text.startswith("/")
        and get_urls_from_string(message.text)
        and message.is_private,
    )
)
async def get_message(m: Message):
    asyncio.create_task(handle_message(m))


DL_QUALITY_MAP = {
    "144p": (144, 35), "240p": (240, 31), "360p": (360, 28),
    "480p": (480, 26), "720p": (720, 23), "1080p": (1080, 20),
}


async def handle_message(m: Message):

    url = get_urls_from_string(m.text)
    if not url:
        return await m.reply("Please enter a valid url.")

    # Maintenance mode check
    if is_maintenance():
        return await m.reply("🔧 Bot is currently under maintenance. Please try again later.")

    # Ban check
    if db.sismember(BANNED_USERS_KEY, str(m.sender_id)):
        return await m.reply("🚫 You are banned from using this bot.")

    # Premium users skip cooldown and rate limits
    is_premium = is_premium_user(m.sender_id)

    # Anti-spam cooldown check (skip for premium/admin)
    if not is_premium and not is_admin(m.sender_id):
        cooldown = check_cooldown(m.sender_id)
        if cooldown > 0:
            return await m.reply(f"⏳ Please wait **{cooldown} seconds** before downloading again.")

    # Track active user today
    today_key = f"active_{time.strftime('%Y-%m-%d')}"
    db.incr(today_key)
    db.expire(today_key, 86400)

    # Track total users
    user_set_key = "all_known_users"
    if not db.sismember(user_set_key, str(m.sender_id)):
        db.sadd(user_set_key, str(m.sender_id))
        db.hincrby(STATS_KEY, "total_users", 1)

    # Force join check — channels
    for ch in FORCE_CHANNELS:
        check_if = await is_user_on_chat(bot, ch, m.sender_id)
        if not check_if:
            return await m.reply(f"Please join {ch} then send me the link again.")

    # Force join check — groups
    for gr in FORCE_GROUPS:
        check_if = await is_user_on_chat(bot, gr, m.sender_id)
        if not check_if:
            return await m.reply(f"Please join {gr} then send me the link again.")
    
    hm = await m.reply("Sending you the media wait...")

    count = db.get(f"check_{m.sender_id}")

    # Free user rate limit: 10 downloads per hour
    if not is_premium and not is_admin(m.sender_id):
        if count and int(count) >= 10:
            ttl = db.ttl(f"check_{m.sender_id}")
            ttl_text = convert_seconds(ttl) if ttl and ttl > 0 else "1 hour"
            return await hm.edit(
                f"You've reached your limit (10 videos/hour).\n"
                f"Try again in **{ttl_text}**.\n"
                f"Upgrade to **Premium** for unlimited downloads."
            )

    shorturl = extract_code_from_url(url)
    if not shorturl:
        return await hm.edit("Seems like your link is invalid.")

    files = await get_files(url)
    if not files:
        return await hm.edit("Sorry! API is dead or maybe your link is broken.")

    # Max files per request check
    if len(files) > MAX_FILES_PER_REQUEST and not is_premium:
        return await hm.edit(
            f"⚠️ This link has **{len(files)} files**.\n"
            f"Free users can download max **{MAX_FILES_PER_REQUEST}** files.\n"
            f"Upgrade to **Premium** for unlimited."
        )

    # Set cooldown after successful API call (skip for premium/admin)
    if not is_premium and not is_admin(m.sender_id):
        set_cooldown(m.sender_id)

    # Premium users get all files, free users get only the first one
    files_to_process = files if is_premium else files[:1]
    total = len(files_to_process)

    # Cached forwarding — works for both free and premium users
    fileid = db.get(shorturl)
    if fileid:
        try:
            ids = [int(x) for x in str(fileid).split(",")]
            cached_msgs = await bot.get_messages(PRIVATE_CHAT_ID, ids=ids)
            valid_msgs = [msg for msg in cached_msgs if msg and msg.media]
            if valid_msgs:
                data = files_to_process[0]
                user_tag = get_custom_tag(m.sender_id)
                tag_str = f" [{user_tag}]" if user_tag else ""
                cached_caption = f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{data['size']}**
╟➣𝗙𝗶𝗿𝘀𝗧 𝗡𝗮𝗺𝗲: {escape_markdown(m.sender.first_name)}{tag_str}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: @{escape_markdown(m.sender.username or '-')}
╚═════════════════⍟
         @NTMpro
"""
                if len(valid_msgs) == 1:
                    await bot.send_file(
                        m.chat.id,
                        file=valid_msgs[0].media,
                        caption=cached_caption,
                        supports_streaming=True,
                    )
                else:
                    for cm in valid_msgs:
                        await bot.send_file(
                            m.chat.id,
                            file=cm.media,
                            supports_streaming=True,
                        )
                await hm.delete()
                db.set(
                    f"check_{m.sender_id}",
                    int(count) + 1 if count else 1,
                    ex=3600,
                )
                return
        except Exception as e:
            print(f"Cache forward failed: {e}")

    user_first_name = m.sender.first_name
    user_username = m.sender.username
    cansend = CanSend()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for idx, data in enumerate(files_to_process, start=1):

        # -------- Per-file supported type check --------
        fname_lower = data["file_name"].lower()
        file_ext = "." + fname_lower.rsplit(".", 1)[-1] if "." in fname_lower else ""
        if file_ext not in VIDEO_EXTENSIONS:
            if total == 1:
                supported = ", ".join(VIDEO_EXTENSIONS)
                return await hm.edit(
                    f"Sorry! File type `{file_ext}` is not supported.\nSupported: {supported}"
                )
            await hm.edit(f"Skipping unsupported file: `{data['file_name']}`")
            continue

        # -------- Per-file size check (admins and premium bypass) --------
        if int(data["sizebytes"]) > 524288000 and not is_admin(m.sender_id) and not is_premium:
            if total == 1:
                return await hm.edit(
                    f"Sorry! File is too big. I can download only 500MB and this file is of {data['size']} ."
                )
            await hm.edit(f"Skipping too big file: `{data['file_name']}` ({data['size']})")
            continue

        start_time = time.time()
        label = f"({idx}/{total}) " if total > 1 else ""

        async def progress_bar(current_downloaded, total_downloaded, state="Sending"):

            if not cansend.can_send():
                return
            if total_downloaded == 0:
                return

            bar_length = 20
            percent = min(current_downloaded / total_downloaded, 1.0)
            filled = int(percent * bar_length)
            arrow = "█" * filled
            spaces = "░" * (bar_length - filled)

            elapsed_time = time.time() - start_time
            if elapsed_time < 0.5:
                return

            speed = current_downloaded / elapsed_time if elapsed_time > 0 else 0
            speed_mb = speed / (1024 * 1024)

            remaining = (total_downloaded - current_downloaded) / speed if speed > 0 else 0

            head = f"{state} {label}`{data['file_name']}`"
            bar = f"[{arrow}{spaces}] {percent:.0%}"
            spd = f"Speed: {speed_mb:.1f} MB/s"
            eta = f"ETA: {convert_seconds(remaining)}"
            sz = f"Size: {get_formatted_size(current_downloaded)} / {get_formatted_size(total_downloaded)}"

            await hm.edit(
                f"{head}\n{bar}\n{spd} | {eta}\n{sz}",
                parse_mode="markdown",
            )

        uuid = str(uuid4())
        thumbnail = download_image_to_bytesio(data["thumb"], "thumbnail.png")

        download = await download_file(
            data["direct_link"], os.path.join(DOWNLOAD_DIR, data["file_name"]), progress_bar
        )
        total_time = time.time() - start_time
        if not download:
            if total == 1:
                return await hm.edit(
                    f"Sorry! Download Failed but you can download it from [here]({url}).",
                    parse_mode="markdown",
                )
            await hm.edit(f"Download failed for `{data['file_name']}`")
            continue

        # ---- Add watermark (skip for small/unsupported files) ----
        file_size = os.path.getsize(download)
        fname_lower = data["file_name"].lower()
        # Skip watermark for formats that ffmpeg can't process well
        skip_wm = any(fname_lower.endswith(ext) for ext in [".ts", ".mkv", ".webm", ".flv", ".avi"])
        if file_size > 10240 and not skip_wm:
            wm_result = await asyncio.get_event_loop().run_in_executor(
                None, add_watermark, download
            )
        else:
            wm_result = False

        # ---- Compress if quality specified ----
        dl_quality = getattr(m, '_dl_quality', None)
        if dl_quality and dl_quality in DL_QUALITY_MAP:
            height, crf = DL_QUALITY_MAP[dl_quality]
            compressed_path = download + f".{dl_quality}.mp4"
            await hm.edit(f"Compressing to {dl_quality}...")
            try:
                cmd = [
                    "ffmpeg", "-y", "-i", download,
                    "-vf", f"scale=-2:{height}",
                    "-c:v", "libx264", "-crf", str(crf),
                    "-preset", "fast", "-c:a", "aac", "-b:a", "128k",
                    compressed_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
                if result.returncode == 0 and os.path.isfile(compressed_path):
                    os.replace(compressed_path, download)
            except Exception as e:
                print(f"Compression failed: {e}")
                if os.path.isfile(compressed_path):
                    os.unlink(compressed_path)

        user_tag = get_custom_tag(m.sender_id)
        tag_str = f" [{user_tag}]" if user_tag else ""

        caption = f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{escape_markdown(data['size'])}** 
╟➣𝗗𝗶𝗿𝗲𝗰𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗟𝗶𝗻𝗸 : [Click here]({data['direct_link']})
╟➣𝗙𝗶𝗿𝘀𝗧 𝗡𝗮𝗺𝗲: {escape_markdown(user_first_name)}{tag_str}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: @{escape_markdown(user_username or '-')}
╟➣𝐓𝐨𝐭𝐚𝐥 𝐓𝐢𝐦𝐞 𝐓𝐚𝐤𝐞𝐧: {total_time} sec
╚═════════════════⍟
         @NTMpro
"""

        # ---- Extract video metadata (duration, width, height, thumbnail) ----
        vinfo = get_video_info(download)
        vduration = vinfo.get("duration", 0)
        vwidth = vinfo.get("width", 0)
        vheight = vinfo.get("height", 0)
        vthumb = vinfo.get("thumbnail")
        if vthumb and not thumbnail:
            thumbnail = download_image_to_bytesio(vthumb, "thumb.jpg")

        # ---- Upload via self-hosted Telegram Bot API (2GB / high speed) ----
        sent_id = None
        try:
            api_res = await send_document_via_api(
                TG_API_BASE, BOT_TOKEN, PRIVATE_CHAT_ID, download, caption, data["file_name"], progress_bar,
                duration=vduration, width=vwidth, height=vheight, thumb=vthumb,
            )
            if api_res.get("ok"):
                sent_id = api_res["result"]["message_id"]
                print("Uploaded via custom Bot API, message_id:", sent_id)
            else:
                print("Custom Bot API error:", api_res)
        except Exception as e:
            print("Custom Bot API upload failed:", e)

        # ---- Fallback to Telethon MTProto upload if Bot API path failed ----
        if sent_id is None:
            try:
                file = await bot.send_file(
                    PRIVATE_CHAT_ID,
                    file=download,
                    thumb=thumbnail if thumbnail else None,
                    progress_callback=progress_bar,
                    caption=caption,
                    video=True,
                    supports_streaming=True,
                    duration=vduration,
                    attributes=[],
                    spoiler=True,
                )
                sent_id = file.id
            except Exception as e:
                print("Telethon upload failed:", e)
                try:
                    os.unlink(download)
                except Exception:
                    pass
                if total == 1:
                    return await hm.edit(
                        f"Sorry! Upload Failed but you can download it from [here]({url}).",
                        parse_mode="markdown",
                    )
                await hm.edit(f"Upload failed for `{data['file_name']}`")
                continue

        if sent_id:
            if shorturl:
                existing = db.get(shorturl)
                if existing:
                    db.set(shorturl, f"{existing},{sent_id}")
                else:
                    db.set(shorturl, sent_id)
            db.set(uuid, sent_id)

            # ---- Forward video from PRIVATE_CHAT_ID to user (instant, no re-upload) ----
            fwd_kwargs = dict(
                from_peer=PRIVATE_CHAT_ID,
                id=[sent_id],
                to_peer=m.chat.id,
                drop_author=True,
                background=True,
                drop_media_captions=False,
                with_my_score=True,
            )
            if m.is_group:
                fwd_kwargs["top_msg_id"] = m.id
            try:
                await bot(ForwardMessagesRequest(**fwd_kwargs))
            except Exception as e:
                print("Forward failed:", e)

            # Cleanup download file
            try:
                os.unlink(download)
            except Exception:
                pass

            # Success message
            try:
                await hm.edit("✅ Video sent successfully to your chat!")
            except Exception:
                pass

            # Track download stats
            db.hincrby(STATS_KEY, "total_downloads", 1)

            # Track history
            import json as _json
            history_entry = _json.dumps({
                "file": data["file_name"],
                "size": data["size"],
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            existing_history = db.get(f"history_{m.sender_id}")
            history_list = _json.loads(existing_history) if existing_history else []
            history_list.append(history_entry)
            if len(history_list) > 50:
                history_list = history_list[-50:]
            db.set(f"history_{m.sender_id}", _json.dumps(history_list), ex=2592000)

            db.set(
                f"check_{m.sender_id}",
                int(count) + 1 if count else 1,
                ex=3600,
            )



# Define /cleandownloads command for admins to free VPS storage
@bot.on(
    events.NewMessage(
        pattern="/cleandownloads",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def clean_downloads(m: UpdateNewMessage):
    if not os.path.isdir(DOWNLOAD_DIR):
        return await m.reply("Downloads folder does not exist. Nothing to clean.")

    files = [
        os.path.join(DOWNLOAD_DIR, f)
        for f in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))
    ]

    if not files:
        return await m.reply("Downloads folder is already empty.")

    total_size = sum(os.path.getsize(f) for f in files)

    deleted = 0
    for f in files:
        try:
            os.unlink(f)
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {f}: {e}")

    if deleted:
        return await m.reply(
            f"Cleaned **{deleted}** file(s) and freed **{get_formatted_size(total_size)}** of storage."
        )
    return await m.reply("Could not delete any files. Check permissions.")


# ---- Background cleanup task: auto-delete downloads older than 1 hour ----
CLEANUP_INTERVAL = 3600  # 1 hour in seconds


async def auto_cleanup_downloads():
    """Periodically delete files in DOWNLOAD_DIR older than 1 hour."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            if not os.path.isdir(DOWNLOAD_DIR):
                continue
            now = time.time()
            for filename in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if now - file_mtime > CLEANUP_INTERVAL:
                        try:
                            os.unlink(filepath)
                            print(f"Auto-deleted old file: {filepath}")
                        except Exception as e:
                            print(f"Failed to auto-delete {filepath}: {e}")
        except asyncio.CancelledError:
            break


# ==================== OWNER ONLY: /update ====================

@bot.on(
    events.NewMessage(
        pattern="/update",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def update_bot(m: UpdateNewMessage):
    msg = await m.reply("Checking for updates...")
    try:
        cwd = os.path.dirname(os.path.abspath(__file__))

        # Stash local changes (including config.py) before pulling
        await msg.edit("Saving local changes...")
        subprocess.run(
            ["git", "stash", "push", "-m", "auto-stash before update", "--", "config.py", "README.md"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )

        # Pull latest
        await msg.edit("Pulling latest code from GitHub...")
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, cwd=cwd, timeout=30,
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if result.returncode == 0:
            if "Already up to date" in output:
                # Restore stashed config
                subprocess.run(
                    ["git", "stash", "pop"],
                    capture_output=True, text=True, cwd=cwd, timeout=10,
                )
                await msg.edit("Already up to date! No changes found.")
            else:
                # Restore stashed config
                subprocess.run(
                    ["git", "stash", "pop"],
                    capture_output=True, text=True, cwd=cwd, timeout=10,
                )
                await msg.edit(
                    "Update completed!\n\n"
                    f"`{output}`"
                )
                # Send separate restart message (visible even after restart)
                await m.reply("Restarting bot now...")
                await asyncio.sleep(5)
                os.execl(sys.executable, sys.executable, *sys.argv)
        else:
            # Try to restore stash even on error
            subprocess.run(
                ["git", "stash", "pop"],
                capture_output=True, text=True, cwd=cwd, timeout=10,
            )
            await msg.edit(f"Update failed!\n\n`{errors or output}`")
    except Exception as e:
        await msg.edit(f"Update error: `{e}`")


# ==================== /restart — NORMAL RESTART ====================

@bot.on(
    events.NewMessage(
        pattern="/restart",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def restart_bot(m: UpdateNewMessage):
    msg = await m.reply("Restarting bot...")
    await asyncio.sleep(2)
    os.execl(sys.executable, sys.executable, *sys.argv)


# ==================== /force — FORCE RESTART (KILL + START) ====================

@bot.on(
    events.NewMessage(
        pattern="/force",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def force_restart(m: UpdateNewMessage):
    msg = await m.reply("Force restarting bot...")
    await asyncio.sleep(2)
    os.execl(sys.executable, sys.executable, *sys.argv)


# ==================== OWNER ONLY: /setstorage ====================

@bot.on(
    events.NewMessage(
        pattern=r"/setstorage\s+(-?\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def set_storage(m: UpdateNewMessage):
    match = m.pattern_match
    new_id = int(match.group(1))
    global PRIVATE_CHAT_ID
    PRIVATE_CHAT_ID = new_id
    await m.reply(f"Storage chat updated to `{PRIVATE_CHAT_ID}`.\nFiles will now upload to the new chat.")


# ==================== OWNER ONLY: /setforce ====================

@bot.on(
    events.NewMessage(
        pattern=r"/setforce\s+(channel|group)\s+(\S+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def set_force(m: UpdateNewMessage):
    match = m.pattern_match
    ftype = match.group(1)
    value = match.group(2)
    global FORCE_CHANNELS, FORCE_GROUPS
    if ftype == "channel":
        if value not in FORCE_CHANNELS:
            FORCE_CHANNELS.append(value)
        await m.reply(f"Force channel updated.\nCurrent channels: {FORCE_CHANNELS}")
    elif ftype == "group":
        if value not in FORCE_GROUPS:
            FORCE_GROUPS.append(value)
        await m.reply(f"Force group updated.\nCurrent groups: {FORCE_GROUPS}")


# ==================== OWNER ONLY: /removeforce ====================

@bot.on(
    events.NewMessage(
        pattern=r"/removeforce\s+(channel|group)\s+(\S+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def remove_force(m: UpdateNewMessage):
    match = m.pattern_match
    ftype = match.group(1)
    value = match.group(2)
    global FORCE_CHANNELS, FORCE_GROUPS
    if ftype == "channel":
        if value in FORCE_CHANNELS:
            FORCE_CHANNELS.remove(value)
        await m.reply(f"Force channel removed.\nCurrent channels: {FORCE_CHANNELS}")
    elif ftype == "group":
        if value in FORCE_GROUPS:
            FORCE_GROUPS.remove(value)
        await m.reply(f"Force group removed.\nCurrent groups: {FORCE_GROUPS}")


# ==================== /adcmd — ALL ADMIN & OWNER COMMANDS ====================

@bot.on(
    events.NewMessage(
        pattern="/adcmd",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def admin_commands(m: UpdateNewMessage):
    is_owner = m.sender_id == OWNER_ID

    text = """
┏━━━━━━━━━━⍟
┃ 𝘼𝙙𝙢𝙞𝙣 & 𝙊𝙬𝙣𝙚𝙧 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨
┗━━━━━━━━━━━━━━━━━⍟

**── Premium Management ──**
/pre `<user_id>` `<duration>` — Promote to premium
/de `<user_id>` — Demote from premium
/premium_users — List all premium with expiry
/demote_all_premium — Remove all premium

**Duration:** `1d` `2d` `3d` `5d` `7d` `1w` `2w` `1m` `unlimited`

**── Gift Cards ──**
/gen `<duration>` `[count]` — Generate gift cards
/gclist — List all gift cards
/gcdel `<code>` — Delete a gift card

**── User Management ──**
/ban `<user_id>` — Ban user
/unban `<user_id>` — Unban user
/banned_users — List banned users
/remove `<user_id>` — Remove user rate limit
/broadcast `<message>` — Broadcast to all users
/announce `<minutes>` `<message>` — Scheduled broadcast

**── Bot Management ──**
/stats — Bot statistics
/usage — Disk, RAM, CPU usage
/logs `[count]` — Recent error logs
/backup — Backup Redis data
/setplan `<text>` — Update plan text
/cleandownloads — Clean downloads folder

**── Media Tools ──**
/mp3 — Reply to video → extract audio
/compress `[low|mid]` — Reply to video → compress
/dl `<link>` — Download original quality
/dl `720p` `<link>` — Download + compress 720p
/dl `480p` `<link>` — Download + compress 480p
/folder `<link>` — Download entire folder (premium)
/setthumb — Reply to image → set thumbnail (premium)
/removethumb — Remove custom thumbnail
/lang `<code>` — Set language (en/ne/hi)
"""
    if is_owner:
        text += """
**── Owner Only ──**
/update — Pull latest code & restart bot
/setstorage `<chat_id>` — Update storage chat
/setforce channel `@username` — Add force channel
/setforce group `@username` — Add force group
/removeforce channel `@username` — Remove force channel
/removeforce group `@username` — Remove force group
/panic — 🚨 Emergency stop all services
/resume — Bring bot back online
/maintenance [on/off] — Toggle maintenance mode
/auditlog `[count]` — View admin action log
/maxfiles `<number>` — Set max files per request
/setcooldown `<seconds>` — Set download cooldown

**── Admin Management (Owner) ──**
/addadmin `<user_id>` — Add new admin
/removeadmin `<user_id>` — Remove admin
/adminlist — List all admins
"""

    await m.reply(text, parse_mode="markdown")


# ==================== /history — USER DOWNLOAD HISTORY ====================

@bot.on(
    events.NewMessage(
        pattern="/history",
        incoming=True,
        outgoing=False,
    )
)
async def user_history(m: UpdateNewMessage):
    import json as _json
    raw = db.get(f"history_{m.sender_id}")
    if not raw:
        return await m.reply("No download history yet.")

    history = _json.loads(raw)
    lines = []
    for i, entry in enumerate(reversed(history), 1):
        e = _json.loads(entry)
        lines.append(f"{i}. `{e['file']}` ({e['size']}) — {e['time']}")

    text = f"**Your Download History ({len(history)}):**\n\n" + "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await m.reply(text, parse_mode="markdown")


# ==================== CUSTOM THUMBNAIL — PREMIUM ====================

THUMB_KEY = "custom_thumbs"  # HASH: user_id → thumbnail bytes path

@bot.on(
    events.NewMessage(
        pattern="/setthumb",
        incoming=True,
        outgoing=False,
    )
)
async def set_thumbnail(m: UpdateNewMessage):
    if not is_premium_user(m.sender_id):
        return await m.reply("Premium feature only.\nUse /plan to check plans.")

    if not m.is_reply:
        return await m.reply("Reply to an image with `/setthumb` to set your custom thumbnail.")

    replied = await m.get_message()
    if not replied.photo:
        return await m.reply("Please reply to a **photo/image** only.")

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    thumb_path = os.path.join(DOWNLOAD_DIR, f"thumb_{m.sender_id}.jpg")
    await bot.download_media(replied, thumb_path)
    db.hset(THUMB_KEY, str(m.sender_id), thumb_path)
    await m.reply("✅ Custom thumbnail set!\nIt will be used on your downloads.")


@bot.on(
    events.NewMessage(
        pattern="/removethumb",
        incoming=True,
        outgoing=False,
    )
)
async def remove_thumbnail(m: UpdateNewMessage):
    uid = str(m.sender_id)
    thumb_path = db.hget(THUMB_KEY, uid)
    if thumb_path and os.path.isfile(thumb_path):
        os.unlink(thumb_path)
    db.hdel(THUMB_KEY, uid)
    await m.reply("✅ Custom thumbnail removed.")


def get_user_thumbnail(user_id):
    """Get custom thumbnail path for user, or None."""
    thumb_path = db.hget(THUMB_KEY, str(user_id))
    if thumb_path and os.path.isfile(thumb_path):
        return thumb_path
    return None


# ==================== LANGUAGE SELECTOR ====================

LANG_KEY = "user_lang"  # HASH: user_id → language code

LANGUAGES = {
    "en": "English",
    "ne": "Nepali",
    "hi": "Hindi",
}

LANG_MESSAGES = {
    "en": {
        "welcome": "Welcome! Send me a TeraBox link to download.",
        "processing": "Sending you the media wait...",
        "success": "✅ Video sent successfully to your chat!",
        "download_fail": "Download Failed but you can download it from {link}.",
        "upload_fail": "Upload Failed but you can download it from {link}.",
        "unsupported": "File type `{ext}` is not supported.\nSupported: {formats}",
        "too_big": "Sorry! File is too big. I can download only 500MB and this file is of {size}.",
        "rate_limit": "You've reached your limit (10 videos/hour).\nTry again in {time}.\nUpgrade to Premium for unlimited downloads.",
        "join_required": "Please join {chat} then send me the link again.",
        "invalid_link": "Seems like your link is invalid.",
        "api_error": "Sorry! API is dead or maybe your link is broken.",
        "no_history": "No download history yet.",
        "history_title": "Your Download History ({count}):",
        "thumb_set": "✅ Custom thumbnail set!",
        "thumb_removed": "✅ Custom thumbnail removed.",
        "thumb_premium": "Premium feature only.\nUse /plan to check plans.",
        "thumb_reply_photo": "Please reply to a **photo/image** only.",
        "lang_set": "Language set to {lang}.",
    },
    "ne": {
        "welcome": "स्वागत छ! डाउनलोड गर्न TeraBox लिङ्क पठाउनुहोस्।",
        "processing": "मिडिया पठाइरहेको छ, कृपया पर्खनुहोस्...",
        "success": "✅ भिडियो सफलतापूर्वक तपाईंको च्याटमा पठाइयो!",
        "download_fail": "डाउनलोड असफल तर तपाईंले यहाँबाट डाउनलोड गर्न सक्नुहुन्छ: {link}",
        "upload_fail": "अपलोड असफल तर तपाईंले यहाँबाट डाउनलोड गर्न सक्नुहुन्छ: {link}",
        "unsupported": "फाइल प्रकार `{ext}` समर्थित छैन।\nसमर्थित: {formats}",
        "too_big": "खेद छ! फाइल धेरै ठूलो छ। मैले 500MB सम्म मात्र डाउनलोड गर्न सक्छु र यो फाइल {size} को छ।",
        "rate_limit": "तपाईंको सीमा पुग्यो (१० भिडियो/घण्टा)।\n{time} मा फेरि प्रयास गर्नुहोस्।\nअसीमित डाउनलोडको लागि Premium मा अपग्रेड गर्नुहोस्।",
        "join_required": "कृपया {chat} मा सामेल हुनुहोस् र फेरि लिङ्क पठाउनुहोस्।",
        "invalid_link": "तपाईंको लिङ्क अमान्य जस्तो देखिन्छ।",
        "api_error": "खेद छ! API मृत छ वा तपाईंको लिङ्क टुटेको छ।",
        "no_history": "अझैसम्म डाउनलोड इतिहास छैन।",
        "history_title": "तपाईंको डाउनलोड इतिहास ({count}):",
        "thumb_set": "✅ कस्टम थम्बनेल सेट भयो!",
        "thumb_removed": "✅ कस्टम थम्बनेल हटाइयो।",
        "thumb_premium": "Premium सुविधा मात्र।\nयोजना हेर्न /plan प्रयोग गर्नुहोस्।",
        "thumb_reply_photo": "कृपया **फोटो/तस्बिर** मा मात्र रिप्लाई गर्नुहोस्।",
        "lang_set": "भाषा {lang}} मा सेट भयो।",
    },
    "hi": {
        "welcome": "स्वागत है! डाउनलोड करने के लिए TeraBox लिंक भेजें।",
        "processing": "मीडिया भेज रहे हैं, कृपया प्रतीक्षा करें...",
        "success": "✅ वीडियो सफलतापूर्वक आपके चैट में भेजा गया!",
        "download_fail": "डाउनलोड विफल लेकिन आप यहां से डाउनलोड कर सकते हैं: {link}",
        "upload_fail": "अपलोड विफल लेकिन आप यहां से डाउनलोड कर सकते हैं: {link}",
        "unsupported": "फाइल प्रकार `{ext}` समर्थित नहीं है।\nसमर्थित: {formats}",
        "too_big": "माफ़ करें! फाइल बहुत बड़ी है। मैं केवल 500MB तक डाउनलोड कर सकता हूं और यह फाइल {size} की है।",
        "rate_limit": "आपकी सीमा पूरी हो गई (10 वीडियो/घंटा)।\n{time} में फिर से प्रयास करें।\nअसीमित डाउनलोड के लिए Premium में अपग्रेड करें।",
        "join_required": "कृपया {chat} में शामिल हों और फिर लिंक भेजें।",
        "invalid_link": "आपका लिंक अमान्य लगता है।",
        "api_error": "माफ़ करें! API डेड है या आपका लिंक टूटा है।",
        "no_history": "अभी तक कोई डाउनलोड इतिहास नहीं।",
        "history_title": "आपका डाउनलोड इतिहास ({count}):",
        "thumb_set": "✅ कस्टम थंबनेल सेट हो गया!",
        "thumb_removed": "✅ कस्टम थंबनेल हटा दिया गया।",
        "thumb_premium": "केवल Premium सुविधा।\nप्लान देखने के लिए /plan का उपयोग करें।",
        "thumb_reply_photo": "कृपया केवल **फोटो/तस्वीर** का उत्तर दें।",
        "lang_set": "भाषा {lang} में सेट हो गई।",
    },
}


def get_lang(user_id):
    """Get user language code."""
    return db.get(f"{LANG_KEY}_{user_id}") or "en"


def t(user_id, key, **kwargs):
    """Get translated message for user."""
    lang = get_lang(user_id)
    msg = LANG_MESSAGES.get(lang, LANG_MESSAGES["en"]).get(key, LANG_MESSAGES["en"].get(key, key))
    if kwargs:
        msg = msg.format(**kwargs)
    return msg


@bot.on(
    events.NewMessage(
        pattern=r"/lang(?:\s+(\w+))?",
        incoming=True,
        outgoing=False,
    )
)
async def set_language(m: UpdateNewMessage):
    lang_code = m.pattern_match.group(1)
    if not lang_code or lang_code.lower() not in LANGUAGES:
        lang_list = "\n".join([f"`{k}` — {v}" for k, v in LANGUAGES.items()])
        return await m.reply(
            f"**Select Language:**\n\n{lang_list}\n\nUsage: `/lang ne`"
        )
    lang_code = lang_code.lower()
    db.set(f"{LANG_KEY}_{m.sender_id}", lang_code)
    await m.reply(t(m.sender_id, "lang_set", lang=LANGUAGES[lang_code]))


# ==================== DOWNLOAD — /dl <quality> <link> ====================

@bot.on(
    events.NewMessage(
        pattern=r"/dl(?:\s+(\w+))?\s+(https?://\S+)",
        incoming=True,
        outgoing=False,
    )
)
async def dl_command(m: UpdateNewMessage):
    quality = m.pattern_match.group(1)
    url = m.pattern_match.group(2)

    if not url:
        return await m.reply(
            "Usage:\n"
            "- `/dl <link>` — Original quality\n"
            "- `/dl 720p <link>` — Compress to 720p\n"
            "- `/dl 480p <link>` — Compress to 480p\n\n"
            "Qualities: 144p, 240p, 360p, 480p, 720p, 1080p"
        )

    if quality:
        quality = quality.lower()
        if quality not in DL_QUALITY_MAP:
            q_list = ", ".join(DL_QUALITY_MAP.keys())
            return await m.reply(f"Invalid quality: `{quality}`\nValid: {q_list}")

    # Set text to URL and pass quality info
    m.text = url
    m._dl_quality = quality if quality else None
    await handle_message(m)


# ==================== FOLDER DOWNLOAD ====================

@bot.on(
    events.NewMessage(
        pattern=r"/folder\s+(https?://\S+)",
        incoming=True,
        outgoing=False,
    )
)
async def folder_download(m: UpdateNewMessage):
    url = m.pattern_match.group(1)

    if db.sismember(BANNED_USERS_KEY, str(m.sender_id)):
        return await m.reply("🚫 You are banned from using this bot.")

    if not is_premium_user(m.sender_id):
        return await m.reply("Folder download is a **premium feature**.\nUse /plan to check plans.")

    hm = await m.reply("Fetching folder contents...")

    files = await get_files(url)
    if not files:
        return await hm.edit("Sorry! Could not fetch folder contents.")

    if len(files) == 1:
        # Single file — normal flow
        m.text = url
        return await handle_message(m)

    # Multiple files — download all
    total = len(files)
    is_premium = is_premium_user(m.sender_id)
    user_first_name = m.sender.first_name
    user_username = m.sender.username
    cansend = CanSend()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    sent_ids = []
    for idx, data in enumerate(files, start=1):
        fname_lower = data["file_name"].lower()
        file_ext = "." + fname_lower.rsplit(".", 1)[-1] if "." in fname_lower else ""
        if file_ext not in VIDEO_EXTENSIONS:
            await hm.edit(f"({idx}/{total}) Skipping `{data['file_name']}` (unsupported)")
            continue

        start_time = time.time()
        label = f"({idx}/{total}) "

        async def progress_bar(current_downloaded, total_downloaded, state="Sending"):
            if not cansend.can_send():
                return
            bar_length = 20
            percent = current_downloaded / total_downloaded
            arrow = "█" * int(percent * bar_length)
            spaces = "░" * (bar_length - len(arrow))
            elapsed_time = time.time() - start_time
            speed_mbps = (current_downloaded / elapsed_time / (1024 * 1024)) if elapsed_time > 0 else 0
            try:
                await hm.edit(
                    f"{state} {label}`{data['file_name']}`\n"
                    f"[{arrow + spaces}] {percent:.2%}\n"
                    f"Speed: **{speed_mbps:.2f} MB/s**"
                )
            except Exception:
                pass

        download = await download_file(
            data["direct_link"], os.path.join(DOWNLOAD_DIR, data["file_name"]), progress_bar
        )
        if not download:
            continue

        # Watermark
        await asyncio.get_event_loop().run_in_executor(None, add_watermark, download)

        # Custom thumb for premium
        custom_thumb = get_user_thumbnail(m.sender_id)

        vinfo = get_video_info(download)
        vduration = vinfo.get("duration", 0)
        vwidth = vinfo.get("width", 0)
        vheight = vinfo.get("height", 0)
        vthumb = custom_thumb or vinfo.get("thumbnail")

        caption = f"📁 `{data['file_name']}` ({data['size']})"

        sent_id = None
        try:
            api_res = await send_document_via_api(
                TG_API_BASE, BOT_TOKEN, PRIVATE_CHAT_ID, download, caption, data["file_name"], progress_bar,
                duration=vduration, width=vwidth, height=vheight, thumb=vthumb,
            )
            if api_res.get("ok"):
                sent_id = api_res["result"]["message_id"]
        except Exception:
            pass

        if sent_id is None:
            try:
                file = await bot.send_file(
                    PRIVATE_CHAT_ID, file=download,
                    caption=caption, video=True, supports_streaming=True,
                    duration=vduration, spoiler=True,
                )
                sent_id = file.id
            except Exception:
                pass

        if sent_id:
            sent_ids.append(sent_id)
            # Forward to user
            try:
                await bot(ForwardMessagesRequest(
                    from_peer=PRIVATE_CHAT_ID,
                    id=[sent_id],
                    to_peer=m.chat.id,
                    drop_author=True,
                    background=True,
                ))
            except Exception:
                pass

        try:
            os.unlink(download)
        except Exception:
            pass

    await hm.edit(f"✅ Folder complete! Sent {len(sent_ids)}/{total} files.")


# ==================== BAN SYSTEM ====================

@bot.on(
    events.NewMessage(
        pattern=r"/ban\s+(\d+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def ban_user(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    db.sadd(BANNED_USERS_KEY, user_id)
    await m.reply(f"🚫 Banned user `{user_id}`.")


@bot.on(
    events.NewMessage(
        pattern=r"/unban\s+(\d+)",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def unban_user(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    db.srem(BANNED_USERS_KEY, user_id)
    await m.reply(f"✅ Unbanned user `{user_id}`.")


@bot.on(
    events.NewMessage(
        pattern="/banned_users",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def list_banned(m: UpdateNewMessage):
    banned = db.smembers(BANNED_USERS_KEY)
    if not banned:
        return await m.reply("No banned users.")
    lines = []
    for uid in banned:
        try:
            user = await bot.get_entity(int(uid))
            name = user.first_name
            username = user.username if user.username else "-"
        except Exception:
            name = "Unknown"
            username = "-"
        lines.append(f"• {name} (@{username}) — `{uid}`")
    await m.reply(f"**Banned Users ({len(lines)}):**\n\n" + "\n".join(lines), parse_mode="markdown")


# ==================== USAGE — BOT RESOURCE STATS ====================

@bot.on(
    events.NewMessage(
        pattern="/usage",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def bot_usage(m: UpdateNewMessage):
    import shutil
    import platform

    # Disk
    disk = shutil.disk_usage("/")
    disk_used_gb = round(disk.used / (1024**3), 2)
    disk_total_gb = round(disk.total / (1024**3), 2)
    disk_percent = round((disk.used / disk.total) * 100, 1)

    # RAM
    try:
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    mem[parts[0]] = int(parts[1]) // 1024  # MB
        ram_used = mem.get("MemTotal:", 0) - mem.get("MemAvailable:", 0)
        ram_total = mem.get("MemTotal:", 0)
        ram_percent = round((ram_used / ram_total) * 100, 1) if ram_total else 0
    except Exception:
        ram_used = ram_total = ram_percent = 0

    # Downloads folder
    dl_size = 0
    dl_count = 0
    if os.path.isdir(DOWNLOAD_DIR):
        for f in os.listdir(DOWNLOAD_DIR):
            fp = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fp):
                dl_size += os.path.getsize(fp)
                dl_count += 1
    dl_size_mb = round(dl_size / (1024**2), 2)

    # Uptime
    try:
        with open("/proc/uptime") as f:
            uptime_sec = float(f.read().split()[0])
        hours = int(uptime_sec // 3600)
        mins = int((uptime_sec % 3600) // 60)
        uptime_str = f"{hours}h {mins}m"
    except Exception:
        uptime_str = "N/A"

    text = (
        f"**Bot Resource Usage**\n\n"
        f"**Disk:** {disk_used_gb}GB / {disk_total_gb}GB ({disk_percent}%)\n"
        f"**RAM:** {ram_used}MB / {ram_total}MB ({ram_percent}%)\n"
        f"**Downloads:** {dl_count} files ({dl_size_mb}MB)\n"
        f"**Platform:** {platform.system()} {platform.release()}\n"
        f"**Uptime:** {uptime_str}\n"
    )
    await m.reply(text, parse_mode="markdown")


# ==================== LOGS — RECENT ERRORS ====================

@bot.on(
    events.NewMessage(
        pattern=r"/logs(?:\s+(\d+))?",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def get_logs(m: UpdateNewMessage):
    count = int(m.pattern_match.group(1) or 20)
    count = min(count, 100)
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
        if os.path.isfile(log_path):
            with open(log_path, "r", errors="ignore") as f:
                lines = f.readlines()
            if not lines:
                return await m.reply("Log file is empty.")
            logs = "".join(lines[-count:])
        else:
            return await m.reply("No log file found. Bot must run with:\n`nohup python -u main.py > bot.log 2>&1 &`")
    except Exception as e:
        return await m.reply(f"Error reading logs: `{e}`")

    if len(logs) > 3000:
        logs = logs[-3000:]
    await m.reply(f"```\n{logs}\n```", parse_mode="markdown")


# ==================== BACKUP — REDIS DATA ====================

@bot.on(
    events.NewMessage(
        pattern="/backup",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def backup_redis(m: UpdateNewMessage):
    msg = await m.reply("Backing up Redis data...")
    try:
        backup = {}
        # Premium users
        backup["premium_set"] = list(db.smembers(PREMIUM_SET_KEY))
        backup["premium_expiry"] = db.hgetall(PREMIUM_EXPIRY_KEY)
        # Banned users
        backup["banned_users"] = list(db.smembers(BANNED_USERS_KEY))
        # Gift cards
        backup["gift_cards"] = db.hgetall(GC_REDIS_KEY)
        # Stats
        backup["stats"] = db.hgetall(STATS_KEY)

        backup_path = os.path.join(DOWNLOAD_DIR, "backup.json")
        with open(backup_path, "w") as f:
            json.dump(backup, f, indent=2, default=str)

        await bot.send_file(
            m.chat.id,
            file=backup_path,
            caption=f"**Redis Backup**\nPremium: {len(backup['premium_set'])}\nBanned: {len(backup['banned_users'])}\nGift Cards: {len(backup['gift_cards'])}",
            parse_mode="markdown",
        )
        os.unlink(backup_path)
    except Exception as e:
        await msg.edit(f"Backup failed: `{e}`")


# ==================== STATS — BOT STATISTICS ====================

@bot.on(
    events.NewMessage(
        pattern="/stats",
        incoming=True,
        outgoing=False,
        func=lambda m: is_admin(m.sender_id),
    )
)
async def bot_stats(m: UpdateNewMessage):
    total_downloads = int(db.hget(STATS_KEY, "total_downloads") or 0)
    total_users = int(db.hget(STATS_KEY, "total_users") or 0)
    premium_count = len(db.smembers(PREMIUM_SET_KEY))
    banned_count = len(db.smembers(BANNED_USERS_KEY))
    gc_count = db.hlen(GC_REDIS_KEY)

    # Active today
    today_key = f"active_{time.strftime('%Y-%m-%d')}"
    active_today = int(db.get(today_key) or 0)

    text = (
        f"**Bot Statistics**\n\n"
        f"**Total Downloads:** {total_downloads}\n"
        f"**Total Users:** {total_users}\n"
        f"**Active Today:** {active_today}\n"
        f"**Premium Users:** {premium_count}\n"
        f"**Banned Users:** {banned_count}\n"
        f"**Gift Cards:** {gc_count}\n"
    )
    await m.reply(text, parse_mode="markdown")


# ==================== /setplan — UPDATE PLAN TEXT ====================

@bot.on(
    events.NewMessage(
        pattern=r"/setplan\s+(.*)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def set_plan(m: UpdateNewMessage):
    new_plan = m.pattern_match.group(1)
    db.set("custom_plan_text", new_plan)
    await m.reply(f"Plan text updated:\n\n{new_plan}")


# ==================== AUDIO EXTRACTOR — /mp3 ====================

@bot.on(
    events.NewMessage(
        pattern=r"^/mp3$",
        incoming=True,
        outgoing=False,
    )
)
async def mp3_reply_handler(m: UpdateNewMessage):
    if not m.is_reply:
        return await m.reply(
            "Usage: Reply to a video with `/mp3`\n\n"
            "Steps:\n"
            "1. Send or forward a video\n"
            "2. Reply to it with `/mp3`\n"
            "3. Wait for audio"
        )

    replied = await m.get_reply_message()
    if not replied:
        return await m.reply("Could not find the replied message. Try again.")
    if not replied.media:
        return await m.reply("Replied message has no media.")

    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        return await m.reply("ffmpeg not installed on server.")

    msg = await m.reply("Extracting audio...")
    video_path = None
    audio_path = None
    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        video_path = os.path.join(DOWNLOAD_DIR, f"mp3_{uuid4().hex}.mp4")
        audio_path = video_path.replace(".mp4", ".mp3")

        await bot.download_media(replied, video_path)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-ab", "192k",
            "-ar", "44100", audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0 or not os.path.isfile(audio_path):
            return await msg.edit("Failed to extract audio. The file may not be a valid video.")

        original_size = os.path.getsize(video_path) / (1024 * 1024)
        audio_size = os.path.getsize(audio_path) / (1024 * 1024)

        caption = replied.text or "Audio"
        await bot.send_file(
            m.chat.id,
            file=audio_path,
            caption=f"Audio extracted!\nOriginal: {original_size:.1f}MB -> Audio: {audio_size:.1f}MB",
            voice_note=True,
        )
        await msg.delete()
    except asyncio.TimeoutError:
        await msg.edit("Audio extraction timed out. File too large.")
    except Exception as e:
        await msg.edit(f"Failed: {e}")
    finally:
        for f in [video_path, audio_path]:
            if f:
                try:
                    os.unlink(f)
                except Exception:
                    pass


# ==================== VIDEO COMPRESS — /compress ====================

@bot.on(
    events.NewMessage(
        pattern=r"^/compress(?:\s+(\w+))?$",
        incoming=True,
        outgoing=False,
    )
)
async def compress_reply_handler(m: UpdateNewMessage):
    if not m.is_reply:
        return await m.reply(
            "Usage: Reply to a video with `/compress`\n\n"
            "Options:\n"
            "- `/compress` — Normal compression (720p)\n"
            "- `/compress low` — Heavy compression (480p)\n\n"
            "Example:\n"
            "1. Send a video\n"
            "2. Reply to it with `/compress low`\n"
            "3. Get compressed video"
        )

    quality = (m.pattern_match.group(1) or "mid").lower()
    replied = await m.get_reply_message()
    if not replied:
        return await m.reply("Could not find the replied message. Try again.")
    if not replied.media:
        return await m.reply("Replied message has no media.")

    import shutil as _shutil
    if not _shutil.which("ffmpeg"):
        return await m.reply("ffmpeg not installed on server.")

    crf_map = {"low": 32, "mid": 28, "high": 23}
    crf = crf_map.get(quality, 28)
    res_map = {"low": "854:-2", "mid": "1280:-2", "high": "1920:-2"}
    res = res_map.get(quality, "1280:-2")

    msg = await m.reply(f"Compressing video ({quality})... This may take a while.")
    video_path = None
    out_path = None
    try:
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        video_path = os.path.join(DOWNLOAD_DIR, f"compress_{uuid4().hex}.mp4")
        out_path = video_path.replace(".mp4", "_compressed.mp4")

        await bot.download_media(replied, video_path)

        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"scale={res}",
            "-c:v", "libx264", "-crf", str(crf),
            "-preset", "fast", "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0 or not os.path.isfile(out_path):
            return await msg.edit("Compression failed. The file may not be a valid video.")

        original_size = os.path.getsize(video_path) / (1024 * 1024)
        compressed_size = os.path.getsize(out_path) / (1024 * 1024)
        saved = round(original_size - compressed_size, 2)

        caption = replied.text or "Compressed video"
        await bot.send_file(
            m.chat.id,
            file=out_path,
            caption=f"Compressed!\nOriginal: {original_size:.1f}MB -> Compressed: {compressed_size:.1f}MB\nSaved: {saved:.1f}MB",
            supports_streaming=True,
        )
        await msg.delete()
    except asyncio.TimeoutError:
        await msg.edit("Compression timed out. File too large.")
    except Exception as e:
        await msg.edit(f"Failed: {e}")
    finally:
        for f in [video_path, out_path]:
            if f:
                try:
                    os.unlink(f)
                except Exception:
                    pass


# ==================== AUTO-ANNOUNCE / SCHEDULED BROADCAST ====================

@bot.on(
    events.NewMessage(
        pattern=r"/announce\s+(\d+)\s+(.*)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def scheduled_announce(m: UpdateNewMessage):
    minutes = int(m.pattern_match.group(1))
    text = m.pattern_match.group(2)

    if minutes > 1440:
        return await m.reply("Max 1440 minutes (24 hours).")

    await m.reply(f"Announcement scheduled in {minutes} minute(s).")

    async def delayed_broadcast():
        await asyncio.sleep(minutes * 60)
        try:
            all_users = await bot.get_participants(-1001336746488)
            sent, failed = 0, 0
            for user in all_users:
                try:
                    await bot.send_message(user.id, text)
                    sent += 1
                except Exception:
                    failed += 1
            await m.reply(f"**Announcement sent!**\nSent: {sent}\nFailed: {failed}")
        except Exception as e:
            await m.reply(f"Announcement failed: `{e}`")

    asyncio.create_task(delayed_broadcast())


# ==================== BATCH MULTI-LINK HANDLER ====================

# This is handled in the main get_message — see below


# ==================== /panic — EMERGENCY STOP ====================

@bot.on(
    events.NewMessage(
        pattern="/panic",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def panic_stop(m: UpdateNewMessage):
    db.set(MAINTENANCE_KEY, "1")
    log_audit("PANIC_STOP", m.sender_id, "Emergency stop activated")
    await m.reply(
        "🚨 **EMERGENCY STOP ACTIVATED**\n\n"
        "All download services are now **STOPPED**.\n"
        "Users will see: `Bot under maintenance`\n\n"
        "Use `/resume` to bring bot back online."
    )


# ==================== /resume — BRING BOT BACK ====================

@bot.on(
    events.NewMessage(
        pattern="/resume",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def resume_bot(m: UpdateNewMessage):
    db.delete(MAINTENANCE_KEY)
    log_audit("RESUME", m.sender_id, "Bot resumed from panic/maintenance")
    await m.reply("✅ **Bot is back online!** All services resumed.")


# ==================== /maintenance — TOGGLE MAINTENANCE ====================

@bot.on(
    events.NewMessage(
        pattern=r"/maintenance(?:\s+(on|off))?",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def maintenance_toggle(m: UpdateNewMessage):
    state = m.pattern_match.group(1)
    if state == "on":
        db.set(MAINTENANCE_KEY, "1")
        log_audit("MAINTENANCE_ON", m.sender_id)
        await m.reply("🔧 **Maintenance mode ON**\nUsers will see maintenance message.")
    elif state == "off":
        db.delete(MAINTENANCE_KEY)
        log_audit("MAINTENANCE_OFF", m.sender_id)
        await m.reply("✅ **Maintenance mode OFF**\nBot is back online.")
    else:
        current = is_maintenance()
        if current:
            db.delete(MAINTENANCE_KEY)
            await m.reply("✅ **Maintenance mode OFF**\nBot is back online.")
        else:
            db.set(MAINTENANCE_KEY, "1")
            await m.reply("🔧 **Maintenance mode ON**\nUsers will see maintenance message.")


# ==================== /auditlog — ADMIN ACTION LOG ====================

@bot.on(
    events.NewMessage(
        pattern=r"/auditlog(?:\s+(\d+))?",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def view_audit_log(m: UpdateNewMessage):
    count = int(m.pattern_match.group(1) or 15)
    count = min(count, 50)

    entries = db.lrange(AUDIT_LOG_KEY, 0, count - 1)
    if not entries:
        return await m.reply("No audit log entries found.")

    import json as _json
    lines = []
    for i, entry in enumerate(entries, 1):
        e = _json.loads(entry)
        lines.append(
            f"{i}. `{e['time']}` — **{e['action']}** by `{e['admin']}`"
            + (f"\n   {e['details']}" if e.get('details') else "")
        )

    text = f"**📝 Audit Log (last {len(lines)}):**\n\n" + "\n\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await m.reply(text, parse_mode="markdown")


# ==================== /maxfiles — SET MAX FILES LIMIT ====================

@bot.on(
    events.NewMessage(
        pattern=r"/maxfiles\s+(\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def set_max_files(m: UpdateNewMessage):
    global MAX_FILES_PER_REQUEST
    MAX_FILES_PER_REQUEST = int(m.pattern_match.group(1))
    log_audit("SET_MAX_FILES", m.sender_id, f"Set to {MAX_FILES_PER_REQUEST}")
    await m.reply(f"✅ Max files per request set to **{MAX_FILES_PER_REQUEST}**.")


# ==================== /setcooldown — SET COOLDOWN TIMER ====================

@bot.on(
    events.NewMessage(
        pattern=r"/setcooldown\s+(\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def set_cooldown_timer(m: UpdateNewMessage):
    global DOWNLOAD_COOLDOWN_SECONDS
    DOWNLOAD_COOLDOWN_SECONDS = int(m.pattern_match.group(1))
    log_audit("SET_COOLDOWN", m.sender_id, f"Set to {DOWNLOAD_COOLDOWN_SECONDS}s")
    await m.reply(f"✅ Download cooldown set to **{DOWNLOAD_COOLDOWN_SECONDS} seconds**.")


# ==================== /addadmin — ADD NEW ADMIN ====================

@bot.on(
    events.NewMessage(
        pattern=r"/addadmin\s+(\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def add_new_admin(m: UpdateNewMessage):
    user_id = int(m.pattern_match.group(1))
    if user_id == OWNER_ID:
        return await m.reply("Cannot remove owner from admin.")
    if is_admin(user_id):
        return await m.reply(f"User `{user_id}` is already an admin.")
    add_admin(user_id)
    log_audit("ADD_ADMIN", m.sender_id, f"Added user {user_id}")
    try:
        user = await bot.get_entity(user_id)
        name = user.first_name
        username = user.username or "-"
        await m.reply(
            f"✅ **Admin Added!**\n\n"
            f"**Name:** {name}\n"
            f"**Username:** @{username}\n"
            f"**ID:** `{user_id}`"
        )
    except Exception:
        await m.reply(f"✅ Admin `{user_id}` added (user not found for name).")


# ==================== /removeadmin — REMOVE ADMIN ====================

@bot.on(
    events.NewMessage(
        pattern=r"/removeadmin\s+(\d+)",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def remove_existing_admin(m: UpdateNewMessage):
    user_id = int(m.pattern_match.group(1))
    if user_id == OWNER_ID:
        return await m.reply("Cannot remove owner from admin.")
    if user_id in ADMINS:
        return await m.reply(
            f"❌ Cannot remove `{user_id}` — they are a **config admin**.\n"
            f"Edit config.py to remove them."
        )
    if not db.sismember(DYNAMIC_ADMINS_KEY, str(user_id)):
        return await m.reply(f"User `{user_id}` is not an admin.")
    remove_admin(user_id)
    log_audit("REMOVE_ADMIN", m.sender_id, f"Removed user {user_id}")
    await m.reply(f"✅ Admin `{user_id}` removed.")


# ==================== /adminlist — LIST ALL ADMINS ====================

@bot.on(
    events.NewMessage(
        pattern="/adminlist",
        incoming=True,
        outgoing=False,
        from_users=[OWNER_ID],
    )
)
async def list_admins(m: UpdateNewMessage):
    lines = []
    # Config admins
    for uid in ADMINS:
        try:
            user = await bot.get_entity(uid)
            name = user.first_name
            username = user.username or "-"
            lines.append(f"• {name} (@{username}) — `{uid}` 🔒 Config")
        except Exception:
            lines.append(f"• Unknown — `{uid}` 🔒 Config")
    # Dynamic admins
    dynamic = db.smembers(DYNAMIC_ADMINS_KEY)
    for uid in dynamic:
        uid_int = int(uid)
        if uid_int in ADMINS:
            continue
        try:
            user = await bot.get_entity(uid_int)
            name = user.first_name
            username = user.username or "-"
            lines.append(f"• {name} (@{username}) — `{uid}` ⚡ Dynamic")
        except Exception:
            lines.append(f"• Unknown — `{uid}` ⚡ Dynamic")

    if not lines:
        return await m.reply("No admins found.")

    await m.reply(
        f"**👥 All Admins ({len(lines)}):**\n\n" + "\n".join(lines) +
        f"\n\n🔒 = Config admin | ⚡ = Bot-added admin",
        parse_mode="markdown",
    )


# Start the cleanup task before running the bot
cleanup_task = bot.loop.create_task(auto_cleanup_downloads())

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
cleanup_task.cancel()
