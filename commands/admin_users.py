"""Admin user-management commands.

PURE logic + register pattern. No imports from main.py (avoids circular imports).
All Redis/functions are injected via ``ctx`` / explicit args.
"""
import re as _re
import time as _time
from datetime import datetime as _datetime

from telethon import events

BANNED_KEY = "banned_users"
EXPIRY_KEY = "premium_expiry"
TAGS_KEY = "custom_tags"


def parse_id_list(raw):
    """'123, 456 789' -> [123, 456, 789] (deduped, order-preserved)."""
    if not raw:
        return []
    parts = _re.split(r"[\s,;]+", str(raw).strip())
    ids, seen = [], set()
    for p in parts:
        if p.isdigit() and int(p) not in seen:
            seen.add(int(p))
            ids.append(int(p))
    return ids


def parse_days(raw):
    """'30' -> 30, else None. Rejects 0/negative/non-numeric."""
    try:
        d = int(str(raw).strip())
        return d if d > 0 else None
    except (ValueError, TypeError):
        return None


def build_user_lookup_text(*, user_id, name="-", username="-",
                           is_banned=False, is_premium=False,
                           remaining=0, tag=""):
    status = "Banned" if is_banned else "Active"
    if is_premium:
        prem = "Permanent" if remaining > 9000000 else f"Premium ({remaining // 86400}d {(remaining % 86400) // 3600}h left)"
    else:
        prem = "Free"
    tag_line = f"Tag: **{tag}**" if tag else "No tag"
    return (f"**User `{user_id}`**\n{name} (@{username})\n"
            f"• Status: {status}\n• {prem}\n• {tag_line}")


def apply_mass_tags(ids, tag, set_tag_fn):
    """Apply ``tag`` to ``ids`` via injected ``set_tag_fn(uid, tag)``."""
    ok, failed = [], []
    for uid in ids or []:
        try:
            set_tag_fn(int(uid), tag)
            ok.append(int(uid))
        except Exception:
            failed.append(uid)
    return {"ok": ok, "failed": failed, "tag": tag}


def build_renew_result(user_id, days, was_premium, expiry_ts=None):
    """Pure text builder for /renew and /addpremium replies."""
    if expiry_ts:
        exp = _datetime.fromtimestamp(expiry_ts).strftime("%d %b %Y, %I:%M %p")
        verb = "renewed" if was_premium else "granted"
        return f"**{user_id}** {verb} for **{days} day(s)**.\nExpires: `{exp}`"
    return f"**{user_id}** premium for **{days} day(s)**."


def _admin_only(ctx):
    is_admin = ctx["is_admin"]
    return lambda m: bool(m.sender_id and is_admin(m.sender_id))


def register(bot, ctx):
    db = ctx["db"]
    is_premium_user = ctx["is_premium_user"]
    grant_premium, revoke_premium = ctx["grant_premium"], ctx["revoke_premium"]
    set_custom_tag = ctx["set_custom_tag"]
    clear_tag = ctx["clear_tag"]
    get_custom_tag = ctx["get_custom_tag"]
    adm = _admin_only(ctx)

    @bot.on(events.NewMessage(pattern=r"/finduser\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _finduser(m):
        uid = m.pattern_match.group(1)
        try:
            banned = bool(db.sismember(BANNED_KEY, str(uid)))
        except Exception:
            banned = False
        prem = bool(is_premium_user(uid))
        rem = 0
        try:
            exp = db.hget(EXPIRY_KEY, str(uid))
            rem = max(int(exp or 0) - int(_time.time()), 0) if prem else 0
        except Exception:
            pass
        try:
            tag = get_custom_tag(int(uid)) or ""
        except Exception:
            tag = ""
        try:
            u = await bot.get_entity(int(uid))
            name, username = u.first_name or "-", u.username or "-"
        except Exception:
            name, username = "Unknown", "-"
        await m.reply(build_user_lookup_text(user_id=uid, name=name, username=username,
                                             is_banned=banned, is_premium=prem, remaining=rem, tag=tag))

    @bot.on(events.NewMessage(pattern=r"/ban\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _ban(m):
        uid = m.pattern_match.group(1)
        db.sadd(BANNED_KEY, str(uid))
        await m.reply(f"Banned user `{uid}`.")

    @bot.on(events.NewMessage(pattern=r"/unban\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _unban(m):
        uid = m.pattern_match.group(1)
        db.srem(BANNED_KEY, str(uid))
        await m.reply(f"Unbanned user `{uid}`.")

    @bot.on(events.NewMessage(pattern=r"/addpremium\s+(\d+)\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _addprem(m):
        uid, days = m.pattern_match.group(1), parse_days(m.pattern_match.group(2))
        if days is None:
            return await m.reply("**Usage:** `/addpremium <id> <days>`")
        grant_premium(int(uid), days)
        await m.reply(build_renew_result(uid, days, False, int(_time.time()) + days * 86400))

    @bot.on(events.NewMessage(pattern=r"/delpremium\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _delprem(m):
        uid = m.pattern_match.group(1)
        if is_premium_user(uid):
            revoke_premium(int(uid))
            await m.reply(f"Revoked premium from **{uid}**.")
        else:
            await m.reply(f"**{uid}** is not a premium user.")

    @bot.on(events.NewMessage(pattern=r"/renew\s+(\d+)\s+(\d+)", incoming=True, outgoing=False, func=adm))
    async def _renew(m):
        uid, days = m.pattern_match.group(1), parse_days(m.pattern_match.group(2))
        if days is None:
            return await m.reply("**Usage:** `/renew <id> <days>`")
        was = bool(is_premium_user(uid))
        grant_premium(int(uid), days)
        await m.reply(build_renew_result(uid, days, was, int(_time.time()) + days * 86400))

    @bot.on(events.NewMessage(pattern=r"/masstag\s+([\d,\s;]+)\s+(.+)", incoming=True, outgoing=False, func=adm))
    async def _masstag(m):
        ids = parse_id_list(m.pattern_match.group(1))
        tag = m.pattern_match.group(2).strip()
        if not ids or not tag:
            return await m.reply("**Usage:** `/masstag <id1,id2..> <tag>`")
        r = apply_mass_tags(ids, tag, set_custom_tag)
        await m.reply(f"Tagged {len(r['ok'])}/{len(ids)} as **{tag}**." + (f"\nFailed: {r['failed']}" if r["failed"] else ""))

    @bot.on(events.NewMessage(pattern=r"/gcheck\s+(\S+)", incoming=True, outgoing=False, func=adm))
    async def _gcheck(m):
        code = m.pattern_match.group(1).strip().upper()
        try:
            days = db.hget("gift_cards", code)
        except Exception:
            days = None
        try:
            tag = db.hget("gc_tags", code)
        except Exception:
            tag = None
        try:
            used = db.hget("gc_used", code)
        except Exception:
            used = None
        if used:
            parts = str(used).split(":")
            who = parts[0] if len(parts) > 0 else "?"
            return await m.reply(f"`{code}` — **USED** by `{who}`." + (f"\nTag: **{tag}**" if tag else ""))
        if days is None:
            return await m.reply(f"`{code}` — invalid or unknown.")
        label = f"{days} day(s)" if str(days) != "0" else "Permanent"
        await m.reply(f"`{code}` — **VALID** ({label})." + (f"\nTag: **{tag}**" if tag else ""))

    @bot.on(events.NewMessage(pattern=r"/untag\s+([\d,\s;]+)", incoming=True, outgoing=False, func=adm))
    async def _untag(m):
        ids = parse_id_list(m.pattern_match.group(1))
        if not ids:
            return await m.reply("**Usage:** `/untag <id1,id2..>`")
        ok, failed = [], []
        for uid in ids:
            try:
                clear_tag(int(uid))
                ok.append(uid)
            except Exception:
                failed.append(uid)
        await m.reply(f"Untagged {len(ok)}/{len(ids)}." + (f"\nFailed: {failed}" if failed else ""))
