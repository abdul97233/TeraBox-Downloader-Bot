"""Referral system — NTM-style deep links + modern UI + self-redeem.

Link format: https://t.me/BOT?start=ref_NTM-{tg_id}
Redis namespace: ref:*
"""

import asyncio
import time as _time

from telethon import Button, events

# Tier thresholds: successful referrals -> reward days.
TIERS = [(5, 1), (10, 3), (25, 7)]

REMINDERS = (
    (3 * 86400, "reminder_3d", "3 days"),
    (1 * 86400, "reminder_1d", "1 day"),
)


def _code_for(user_id):
    """ref_NTM-{tg_id} — simple, unique, human-readable."""
    return f"ref_NTM-{int(user_id)}"


def _resolve_code(db, code):
    """Parse ref_NTM-{tg_id} -> user_id (int) or None."""
    try:
        if code.startswith("ref_NTM-"):
            uid = int(code.split("ref_NTM-", 1)[1])
            if uid > 0:
                return uid
    except Exception:
        pass
    return None


def record_referral(db, referrer_id, new_user_id):
    """Record a referral on /start. Returns True if new attribution."""
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
        db.hincrby("ref:ok", str(referrer_id), 1)
        return True
    except Exception:
        return False


def get_stats(db, user_id):
    """Return (invited, successful, next_tier, days_to_next)."""
    try:
        invited = db.scard(f"ref:invited:{user_id}") or 0
    except Exception:
        invited = 0
    try:
        ok = int(db.hget("ref:ok", str(user_id)) or 0)
    except Exception:
        ok = 0
    for threshold, days in TIERS:
        if ok < threshold:
            return invited, ok, threshold, days
    return invited, ok, None, None


def get_reward_for(count):
    """Return total reward days for a given successful count (cumulative)."""
    total = 0
    for threshold, days in TIERS:
        if count >= threshold:
            total = days
    return total


def check_and_grant_reward(db, user_id, grant_premium_fn):
    """Check if user hit a new tier and grant. Returns (granted, days)."""
    try:
        ok = int(db.hget("ref:ok", str(user_id)) or 0)
    except Exception:
        return False, 0
    last = int(db.hget("ref:last_reward", str(user_id)) or 0)
    for threshold, days in TIERS:
        if ok >= threshold and threshold > last:
            try:
                grant_premium_fn(int(user_id), days)
                db.hset("ref:last_reward", str(user_id), threshold)
                return True, days
            except Exception:
                return False, 0
    return False, 0


def parse_start_referral(text):
    """Extract ref code from '/start ref_NTM-xxx'. Returns code or None."""
    try:
        parts = str(text or "").split()
        if len(parts) >= 2 and parts[1].startswith("ref_"):
            return parts[1]
    except Exception:
        pass
    return None


def _progress_bar(current, target, length=8):
    """Visual progress bar: ████░░░░."""
    filled = min(current, target)
    ratio = filled / target if target else 0
    bar_len = int(ratio * length)
    return "█" * bar_len + "░" * (length - bar_len)


def _tier_text(ok):
    """Build tier status with progress bars."""
    lines = []
    for i, (threshold, days) in enumerate(TIERS):
        prev = TIERS[i - 1][0] if i > 0 else 0
        segment = threshold - prev
        in_segment = max(0, min(ok, threshold) - prev)
        bar = _progress_bar(in_segment, segment, 8)
        check = "✅" if ok >= threshold else "⬜"
        label = f"{threshold} referrals"
        lines.append(f"{check} `{bar}` {label} → {days}d Premium")
    return "\n".join(lines)


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

    @bot.on(events.NewMessage(pattern=r"^/(ref|refer|referral)$", incoming=True, outgoing=False))
    async def _referral(m):
        user_id = m.sender_id
        code = _code_for(user_id)
        try:
            me = await bot.get_me()
            username = me.username or "YourBot"
        except Exception:
            username = "YourBot"

        invited, ok, next_tier, days_to_next = get_stats(db, user_id)
        link = f"https://t.me/{username}?start={code}"

        if next_tier:
            need = next_tier - ok
            tier_text = f"Next tier: **{need} more** referral(s) → {days_to_next}d Premium"
        else:
            tier_text = "🏆 **All tiers unlocked!**"

        text = (
            "┏━━━━━━━━━━━━━━━━━⍟\n"
            "┃  👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗦𝘆𝘀𝘁𝗲𝗺\n"
            "┗━━━━━━━━━━━━━━━━━━━━━⍟\n\n"
            f"📎 Your referral link:\n`{link}`\n\n"
            f"👥 Invited: **{invited}**\n"
            f"✅ Successful: **{ok}**\n\n"
            f"{_tier_text(ok)}\n\n"
            f"{tier_text}\n\n"
            "💡 Share your link — when someone joins, you earn points!\n"
            "🎁 Hit a tier to unlock Premium rewards."
        )

        # Check if there's a reward to claim
        granted, days = check_and_grant_reward(db, user_id, grant_premium)
        if granted:
            text += f"\n\n🎉 **Congratulations!** You just earned **{days} days Premium!**"

        buttons = [
            [Button.url("📤 Share Link", f"https://t.me/share/url?url={link}")],
            [
                Button.inline("🏆 Claim Reward", data="ref_claim"),
                Button.inline("📊 Full Stats", data="ref_fullstats"),
            ],
            [Button.inline("◀️ Back", data="menu_main")],
        ]
        await m.reply(text, parse_mode="markdown", buttons=buttons)

    @bot.on(events.CallbackQuery(data=b"ref_claim"))
    async def _ref_claim(e):
        granted, days = check_and_grant_reward(db, e.sender_id, grant_premium)
        if granted:
            text = f"🎉 **Reward Claimed!**\n\nYou received **{days} days Premium!**\n\nEnjoy your benefits!"
        else:
            invited, ok, next_tier, days_to_next = get_stats(db, e.sender_id)
            if next_tier:
                need = next_tier - ok
                text = f"⏳ No reward to claim yet.\n\nYou need **{need} more** referral(s) to reach the next tier ({days_to_next}d Premium)."
            else:
                text = "🏆 You've already claimed all available rewards!"
        await e.answer(text[:200], alert=True)

    @bot.on(events.CallbackQuery(data=b"ref_fullstats"))
    async def _ref_fullstats(e):
        invited, ok, next_tier, days_to_next = get_stats(db, e.sender_id)
        last = int(db.hget("ref:last_reward", str(e.sender_id)) or 0)
        earned = get_reward_for(ok)

        text = (
            "┏━━━━━━━━━━━━━━━━━⍟\n"
            "┃  📊 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗦𝘁𝗮𝘁𝘀\n"
            "┗━━━━━━━━━━━━━━━━━━━━━⍟\n\n"
            f"👥 Total invited: **{invited}**\n"
            f"✅ Successful: **{ok}**\n"
            f"🎁 Rewards earned: **{earned} days** Premium\n"
            f"📌 Last tier claimed: **{last}** referrals\n\n"
            f"{_tier_text(ok)}"
        )
        buttons = [[Button.inline("◀️ Back", data="menu_referral")]]
        await e.edit(text, parse_mode="markdown", buttons=buttons)

    @bot.on(events.CallbackQuery(data=b"menu_referral"))
    async def cb_referral_menu(e):
        user_id = e.sender_id
        code = _code_for(user_id)
        try:
            me = await bot.get_me()
            username = me.username or "YourBot"
        except Exception:
            username = "YourBot"

        invited, ok, next_tier, days_to_next = get_stats(db, user_id)
        link = f"https://t.me/{username}?start={code}"

        if next_tier:
            need = next_tier - ok
            tier_text = f"Next: **{need} more** → {days_to_next}d Premium"
        else:
            tier_text = "🏆 **All tiers unlocked!**"

        text = (
            "┏━━━━━━━━━━━━━━━━━⍟\n"
            "┃  👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀\n"
            "┗━━━━━━━━━━━━━━━━━━━━━⍟\n\n"
            f"`{link}`\n\n"
            f"👥 Invited: **{invited}** | ✅ Successful: **{ok}**\n\n"
            f"{_tier_text(ok)}\n\n"
            f"{tier_text}"
        )
        buttons = [
            [Button.url("📤 Share", f"https://t.me/share/url?url={link}")],
            [
                Button.inline("🏆 Claim", data="ref_claim"),
                Button.inline("📊 Stats", data="ref_fullstats"),
            ],
            [Button.inline("◀️ Back", data="menu_main")],
        ]
        await e.edit(text, parse_mode="markdown", buttons=buttons)

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
