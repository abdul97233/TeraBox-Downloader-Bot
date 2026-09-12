"""Personal download statistics (/mystats). No main.py imports."""

from telethon import events

from tools import get_formatted_size


def _num(h, *keys):
    for k in keys:
        try:
            v = int(h.get(k, 0) or 0)
            if v:
                return v
        except Exception:
            pass
    return 0


def register(bot, ctx):
    db = ctx["db"]
    is_premium_user = ctx["is_premium_user"]

    @bot.on(events.NewMessage(pattern=r"^/mystats$", incoming=True, outgoing=False))
    async def _mystats(m):
        uid = m.sender_id
        try:
            h = db.hgetall(f"user_stats_{uid}") or {}
        except Exception:
            h = {}
        attempts = _num(h, "attempts")
        success = _num(h, "success", "total")
        failed = _num(h, "failed", max(attempts - success, 0))
        try:
            storage = get_formatted_size(int(h.get("storage", 0) or 0))
        except Exception:
            storage = "0 B"
        try:
            audio = int(h.get("audio", 0) or 0)
        except Exception:
            audio = 0
        try:
            video = int(h.get("video", 0) or 0)
        except Exception:
            video = 0
        last = h.get("last_activity", "Never") or "Never"
        try:
            member = db.get(f"member_since:{uid}") or "?"
        except Exception:
            member = "?"
        try:
            premium = "Active" if is_premium_user(uid) else "Free"
        except Exception:
            premium = "?"
        if not attempts and not success:
            return await m.reply(
                "📊 Your Statistics\n\nNo completed downloads yet.\n\nStart by sending a TeraBox link."
            )
        await m.reply(
            "📊 Your Statistics\n\n"
            f"Files: {success}\n"
            f"Data downloaded: {storage}\n\n"
            f"Successful: {success}\n"
            f"Failed: {failed}\n"
            f"Audio conversions: {audio}\n"
            f"Video conversions: {video}\n\n"
            f"Premium: {premium}\n"
            f"Member since: {member}"
        )
