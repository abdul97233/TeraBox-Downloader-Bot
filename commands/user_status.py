"""User-status (/mystatus) logic.

Pure functions only — no ``main.py`` imports, so this module can grow into
the future home of the handler without circular imports.
"""

from datetime import datetime as _datetime


def fetch_user_stats(db, user_id):
    try:
        data = db.hgetall(f"user_stats_{user_id}")
        if data:
            return {
                "downloads": int(data.get("total", 0)),
                "storage": int(data.get("storage", 0)),
                "last_activity": data.get("last_activity", "Never"),
            }
    except Exception:
        pass
    return {"downloads": 0, "storage": 0, "last_activity": "Never"}


def premium_status_text(premium_expiry_raw, is_premium):
    if premium_expiry_raw:
        try:
            expiry = _datetime.fromtimestamp(float(premium_expiry_raw))
            days_left = (expiry - _datetime.now()).days
            return f"Premium expires in {max(days_left, 0)} days"
        except Exception:
            return "Premium active (no expiry set)"
    return "Premium active" if is_premium else "Free user"


def build_mystatus_text(*, first_name, username, is_premium,
                        premium_expiry_raw, tag, stats, format_size_fn):
    storage = format_size_fn(stats["storage"])
    tag_info = f"Tag: **{tag}**" if tag else "No custom tag"
    return (
        f"**Your Status**\n\n"
        f"**Premium:** {premium_status_text(premium_expiry_raw, is_premium)}\n"
        f"{tag_info}\n"
        f"**Download Stats:**\n"
        f"• Total downloads: **{stats['downloads']}**\n"
        f"• Total storage: **{storage}**\n"
        f"• Last activity: **{stats['last_activity']}**\n\n"
        f"Use /plan to check premium plans, /tag to manage your tag."
    )
