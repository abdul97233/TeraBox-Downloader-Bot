"""Referral system (deep links) + premium expiry reminders.

Redis namespace `ref:*`. No main.py imports — everything via ctx.
"""

import asyncio
import secrets as _secrets
import time as _time

from telethon import Button, events

# Successful referrals -> reward days Premium (cumulative thresholds).
TIERS = {5: 1, 10: 3, 25: 7}

REMINDERS = (
    (3 * 86400, "reminder_3d", "3 days"),
    (1 * 86400, "reminder_1d", "1 day"),
)


def get_or_create_code(db, user_id):
    """Stable unique code per user."""
    try:
        code = db.hget("ref:code", str(user_id))
    except Exception:
        code = None
    if code:
        return code
    for _ in range(5):
        code = f"REF-{int(user_id) % 100000:05d}-{_secrets.token_hex(2).upper()}"
        try:
            if db.hsetnx("ref:code_by_code", code, str(user_id)):
                break
        except Exception:
            break
    else:
        code = f"REF-{int(user_id)}"
    try:
        db.hset("ref:code", str(user_id), code)
        db.hset("ref:code_by_code", code, str(user_id))
    except Exception:
        pass
    return code


def record_referral_start(db, referrer_id, new_user_id):
    """Attribute a /start to a referrer. Returns True if recorded."""
    try:
        referrer_id, new_user_id = int(referrer_id), int(new_user_id)
    except Exception:
        return False
    if referrer_id == new_user_id:
        return False
    try:
        if db.exists(f"ref:by:{new_user_id}"):
            return False
        db.set(f"ref:by:{new_user_id}", referrer_id)
        db.sadd(f"ref:invited:{referrer_id}", new_user_id)
        return True
    except Exception:
        return False


def credit_activation(db, new_user_id, grant_premium_fn):
    """Called once on a referred user's first successful download.

    Returns (rewarded: bool, referrer_id, total, days).
    """
    try:
        new_user_id = int(new_user_id)
    except Exception:
        return False, None, 0, 0
    try:
        if not db.set(f"ref:activated:{new_user_id}", "1", nx=True):
            return False, None, 0, 0
    except Exception:
        return False, None, 0, 0
    try:
        referrer = db.get(f"ref:by:{new_user_id}")
    except Exception:
        referrer = None
    if not referrer:
        return False, None, 0, 0
    try:
        total = int(db.hincrby("ref:ok", str(referrer), 1))
    except Exception:
        return False, referrer, 0, 0
    days = TIERS.get(total, 0)
    if days:
        try:
            grant_premium_fn(int(referrer), days)
        except Exception:
            return False, referrer, total, 0
        return True, referrer, total, days
    return False, referrer, total, 0


def parse_start_referral(text):
    """Extract referrer user id from '/start ref_CODE'. Returns code or None."""
    try:
        parts = str(text or "").split()
        if len(parts) >= 2 and parts[1].startswith("ref_"):
            return parts[1][len("ref_"):]
    except Exception:
        pass
    return None


async def referral_sweep_once(bot, db):
    """Send 3d/1d/expiry reminders. Returns counts dict."""
    sent = {"d3": 0, "d1": 0, "expired": 0}
    try:
        all_exp = db.hgetall("premium_expiry") or {}
    except Exception:
        return sent
    now = int(_time.time())
    for uid, exp in all_exp.items():
        try:
            remaining = int(exp) - now
        except Exception:
            continue
        if remaining <= 0:
            try:
                if db.set(f"reminder_expired:{uid}", "1", nx=True):
                    try:
                        await bot.send_message(
                            int(uid),
                            "⭐ Premium Reminder\n\nYour Premium access has expired.\n\nDon't lose your Premium benefits.",
                            buttons=[[Button.inline("Renew Premium", data="renew_info")]],
                        )
                        sent["expired"] += 1
                    except Exception:
                        pass
            except Exception:
                pass
            continue
        for window, flag, label in sorted(REMINDERS):
            if 0 < remaining <= window:
                try:
                    fresh = db.set(f"{flag}:{uid}", "1", nx=True, ex=window + 86400)
                except Exception:
                    fresh = False
                if fresh:
                    try:
                        await bot.send_message(
                            int(uid),
                            "⭐ Premium Reminder\n\n"
                            f"Your Premium access expires in {label}.\n\n"
                            "Don't lose your Premium benefits.",
                            buttons=[[Button.inline("Renew Premium", data="renew_info")]],
                        )
                        sent["d3" if "3d" in flag else "d1"] += 1
                    except Exception:
                        pass
                break
    return sent


async def reminder_loop(bot, db, interval_hours=1):
    while True:
        try:
            await asyncio.sleep(float(interval_hours) * 3600)
        except asyncio.CancelledError:
            break
        except Exception:
            break
        try:
            await referral_sweep_once(bot, db)
        except Exception:
            pass


def reset_reminder_state(db, user_id):
    for flag in ("reminder_3d", "reminder_1d", "reminder_expired"):
        try:
            db.delete(f"{flag}:{user_id}")
        except Exception:
            pass


def register(bot, ctx):
    db = ctx["db"]
    grant_premium = ctx["grant_premium"]

    @bot.on(events.NewMessage(pattern=r"^/referral$", incoming=True, outgoing=False))
    async def _referral(m):
        code = get_or_create_code(db, m.sender_id)
        try:
            me = await bot.get_me()
            username = me.username or "YourBot"
        except Exception:
            username = "YourBot"
        try:
            invited = db.scard(f"ref:invited:{m.sender_id}")
        except Exception:
            invited = 0
        try:
            ok = int((db.hget("ref:ok", str(m.sender_id)) or 0))
        except Exception:
            ok = 0
        await m.reply(
            "👥 Your Referral System\n\n"
            "Your referral link:\n\n"
            f"https://t.me/{username}?start=ref_{code}\n\n"
            f"Invited users: {invited}\n"
            f"Successful referrals: {ok}\n"
            "Rewards earned: 5 referrals → 1 day Premium\n"
            "10 → 3 days, 25 → 7 days"
        )

    @bot.on(events.NewMessage(pattern=r"^/refstats$", incoming=True, outgoing=False,
                              func=lambda m: ctx["is_admin"](m.sender_id)))
    async def _refstats(m):
        try:
            codes = db.hlen("ref:code")
        except Exception:
            codes = 0
        try:
            ok_map = db.hgetall("ref:ok") or {}
            activated = sum(int(v or 0) for v in ok_map.values())
        except Exception:
            activated = 0
        top = []
        try:
            for uid, n in (ok_map or {}).items():
                top.append((uid, int(n or 0)))
            top.sort(key=lambda x: x[1], reverse=True)
        except Exception:
            top = []
        lines = [f"Codes issued: {codes}", f"Activated referrals: {activated}", ""]
        for uid, n in top[:5]:
            lines.append(f"`{uid}` — {n}")
        await m.reply("**Referral Stats**\n\n" + "\n".join(lines), parse_mode="markdown")

    @bot.on(events.CallbackQuery(data=b"renew_info"))
    async def _renew_info(e):
        try:
            await e.answer("See plans below.", alert=False)
        except Exception:
            pass
        try:
            await e.reply("⭐ Renew Premium\n\nUse /plan to check plans or contact an admin to renew.")
        except Exception:
            pass
