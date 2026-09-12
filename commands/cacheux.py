"""Duplicate/cache prompt: [Send Cached File] / [Download Again]. No main.py imports."""

import json as _json

from telethon import Button, events

PENDING_TTL = 600


def _pending_key(user_id, shorturl):
    return f"cache:pending:{int(user_id)}:{shorturl}"


def register(bot, ctx):
    db = ctx["db"]
    get_custom_tag = ctx["get_custom_tag"]
    escape_markdown = ctx["escape_markdown"]
    storage_chat = ctx.get("storage_chat")
    if callable(storage_chat):
        try:
            storage_chat = storage_chat()
        except Exception:
            storage_chat = None

    def _caption(data, first_name, username, tag):
        tag_str = f" ({tag})" if tag else ""
        return f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data.get('file_name', 'file')}`
╟➣𝙎𝙞𝙯𝙚: **{data.get('size', '?')}**
╟➣𝗙𝗶𝗿𝘀𝗧 𝗡𝗮𝗺𝗲: {escape_markdown(first_name)}{tag_str}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: @{escape_markdown(username or '-')}
╚═════════════════⍟
         @NTMpro
"""

    @bot.on(events.CallbackQuery(pattern=rb"cx_send:"))
    async def _cx_send(e):
        try:
            shorturl = e.data.decode(errors="ignore").split("cx_send:", 1)[1]
        except Exception:
            shorturl = ""
        try:
            raw = db.get(_pending_key(e.sender_id, shorturl))
        except Exception:
            raw = None
        if not raw:
            try:
                await e.answer("Expired — resend the link.", alert=True)
            except Exception:
                pass
            return
        try:
            payload = _json.loads(raw)
            ids = [int(x) for x in payload.get("ids", [])]
        except Exception:
            ids = []
        try:
            chat_id = payload.get("chat_id", e.sender_id)
        except Exception:
            chat_id = e.sender_id
        # Re-validate: stale entries are purged, never sent
        _STORAGE = storage_chat
        if _STORAGE is None:
            try:
                from main import PRIVATE_CHAT_ID as _STORAGE
            except Exception:
                _STORAGE = None
        try:
            cached = await bot.get_messages(_STORAGE, ids=ids) if (_STORAGE and ids) else []
        except Exception:
            cached = []
        valid = [mm for mm in (cached or []) if mm and mm.media]
        if not valid:
            try:
                db.delete(shorturl)
            except Exception:
                pass
            try:
                db.delete(_pending_key(e.sender_id, shorturl))
            except Exception:
                pass
            try:
                await e.edit("❌ Cached copy is no longer available.\nDownloading a fresh copy instead.\n\nPlease resend the link.")
            except Exception:
                pass
            return
        try:
            tag = get_custom_tag(int(e.sender_id))
        except Exception:
            tag = ""
        try:
            me = await bot.get_entity(int(e.sender_id))
            fn, un = me.first_name or "-", me.username or "-"
        except Exception:
            fn, un = "-", "-"
        data = {"file_name": payload.get("file_name", "file"), "size": payload.get("size", "?")}
        try:
            if len(valid) == 1:
                await bot.send_file(int(e.sender_id), file=valid[0].media,
                                    caption=_caption(data, fn, un, tag), supports_streaming=True)
            else:
                for cm in valid:
                    await bot.send_file(int(e.sender_id), file=cm.media, supports_streaming=True)
            try:
                db.hincrby("bot_stats", "total_downloads", 1)
            except Exception:
                pass
            try:
                db.hincrby(f"user_stats_{int(e.sender_id)}", "total", 1)
            except Exception:
                pass
            try:
                await e.edit("✅ Cached file sent!")
            except Exception:
                pass
        except Exception:
            try:
                await e.answer("Send failed — resend the link.", alert=True)
            except Exception:
                pass
        finally:
            try:
                db.delete(_pending_key(e.sender_id, shorturl))
            except Exception:
                pass

    @bot.on(events.CallbackQuery(pattern=rb"cx_again:"))
    async def _cx_again(e):
        try:
            shorturl = e.data.decode(errors="ignore").split("cx_again:", 1)[1]
        except Exception:
            shorturl = ""
        try:
            db.delete(shorturl)
        except Exception:
            pass
        try:
            db.delete(_pending_key(e.sender_id, shorturl))
        except Exception:
            pass
        try:
            await e.edit("Cache cleared — resend the link to download a fresh copy.")
        except Exception:
            pass
