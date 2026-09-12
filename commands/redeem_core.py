"""Shared gift-card redeem core.

Used by BOTH /redeem (main.py) and one-click gift buttons (commands/ux.py)
so tapping a button does exactly what typing /redeem does. No main.py
imports — all dependencies are explicit arguments.
"""

import time as _time
from datetime import datetime as _datetime


def identity_block(first_name, last_name, username, user_id):
    """Who-redeemed block appended to user confirmations."""
    try:
        full = f"{first_name or ''} {last_name or ''}".strip() or "-"
    except Exception:
        full = "-"
    try:
        uname = f"@{username}" if username else "@-"
    except Exception:
        uname = "@-"
    return f"\n\nRedeemed by: {full} ({uname})\nID: `{user_id}`"


async def redeem_code(*, db, gc_key, gc_tags_key, gc_used_key,
                      code, user_id,
                      grant_premium_fn, set_tag_fn, is_premium_fn):
    """Redeem a gift card. Never raises. Returns (ok, user_text, info).

    info is {"code", "days", "tag"} on success, else None.
    """
    code = str(code or "").strip().upper()
    try:
        if db.get(f"gc_redeemed_{user_id}") and is_premium_fn(user_id):
            return (False,
                    "You have already redeemed a gift card and your premium is still active.\n"
                    "Each user can only redeem **1 gift card** while premium is active.\n"
                    "Wait for expiry or contact admin.",
                    None)
    except Exception:
        pass

    try:
        days_str = db.hget(gc_key, code)
    except Exception:
        days_str = None
    if not days_str:
        return False, "Invalid or already used gift card.", None

    try:
        days = int(days_str)
    except Exception:
        return False, "Invalid or already used gift card.", None

    try:
        tag = db.hget(gc_tags_key, code) or ""
    except Exception:
        tag = ""
    try:
        db.hdel(gc_key, code)
    except Exception:
        pass
    try:
        db.hdel(gc_tags_key, code)
    except Exception:
        pass
    try:
        db.hset(gc_used_key, code, f"{user_id}:{int(_time.time())}:{days}")
    except Exception:
        pass
    try:
        db.set(f"gc_redeemed_{user_id}", "1")
    except Exception:
        pass
    if tag:
        try:
            set_tag_fn(user_id, tag)
        except Exception:
            pass

    tag_info = f"\nTag: **{tag}**" if tag else ""
    try:
        grant_premium_fn(user_id, 99999 if days == 0 else days)
    except Exception as e:
        return False, f"Card accepted but premium failed: `{e}`", None

    if days == 0:
        text = (f"Gift card redeemed!\n\n"
                f"**Premium: Unlimited**\n"
                f"Duration: Permanent (never expires){tag_info}")
    else:
        expiry = int(_time.time()) + (days * 86400)
        expiry_str = _datetime.fromtimestamp(expiry).strftime("%d %b %Y, %I:%M %p")
        text = (f"Gift card redeemed!\n\n"
                f"**Premium: {days} day(s)**\n"
                f"Expires: `{expiry_str}`{tag_info}")
    return True, text, {"code": code, "days": days, "tag": tag}
