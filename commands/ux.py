"""UX helpers + thin command wiring.

Pure logic only — no imports from main.py (avoids circular imports).
"""

import asyncio
import re

from telethon import Button, events

BROADCAST_CHUNK = 50
PREVIEW_LIMIT = 3
EXPIRY_SOON_MIN = 60


def giftcard_buttons(codes):
    """One-click /redeem buttons. Returns Telethon Button rows."""
    rows = []
    for c in list(codes or [])[:25]:
        code = str(c).strip().upper()
        if not code:
            continue
        rows.append([Button.inline(f"[gift] {code}", data=f"redeem_{code}"[:64])])
    return rows


def _fname(f):
    return f.get("file_name") or f.get("filename") or "file"


def _fsize(f):
    return f.get("size") or f.get("size_readable") or ""


def build_preview_text(files, limit=PREVIEW_LIMIT):
    """Folder preview: first `limit` files + '...and N more'."""
    files = list(files or [])
    if not files:
        return "No files found."
    total = len(files)
    lines = [f"**Preview — {total} file(s)**", ""]
    for i, f in enumerate(files[:limit], 1):
        lines.append(f"{i}. `{_fname(f)}` — **{_fsize(f)}**")
    if total > limit:
        lines.append(f"...and {total - limit} more.")
    lines.append("Send /quick <link> to download the first file.")
    return "\n".join(lines)


def _expiry_minutes(v):
    """Parse an expires_in value to minutes (float) or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) / 60.0 if v > 0 else None
    s = str(v).strip().lower()
    if not s or s in ("0", "none", "null", "never", "permanent", "unlimited", "inf", "infinite"):
        return None
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s) / 60.0
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(d(?:ays?)?|h(?:ours?|rs?)?|m(?:in(?:utes?)?)?|s(?:ec(?:onds?)?)?)", s):
        found = True
        n, u = float(num), unit[0]
        total += n * 1440 if u == "d" else n * 60 if u == "h" else n if u == "m" else n / 60
    if found:
        return total
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def build_expiry_warning(expires_in_text):
    """Warn when a download link expires soon (<=60 minutes)."""
    mins = _expiry_minutes(expires_in_text)
    if mins is None or mins > EXPIRY_SOON_MIN:
        return ""
    return (f"Link expires soon (~{int(mins)} min left — {expires_in_text}). "
            "Download now before it expires!")


def broadcast_split(all_user_ids, text, chunk_size=BROADCAST_CHUNK):
    """Chunk user ids for safe broadcast. Pure: no sending."""
    try:
        n = int(chunk_size)
        cs = n if n > 0 else BROADCAST_CHUNK
    except Exception:
        cs = BROADCAST_CHUNK
    ids = []
    for u in (all_user_ids or []):
        try:
            ids.append(int(getattr(u, "id", u)))
        except Exception:
            continue
    ids = list(dict.fromkeys(ids))
    return [ids[i:i + cs] for i in range(0, len(ids), cs)] if ids else []


def _ctx(ctx, key, default=None):
    try:
        if isinstance(ctx, dict):
            return ctx.get(key, default)
    except Exception:
        pass
    return getattr(ctx, key, default)


async def _auto_redeem_button(e, bot, ctx):
    """One-click gift-card button tapped: redeem immediately for the tapper.

    Confirms via DM (no thread spam). Falls back to a reply only if DM fails.
    """
    try:
        code = e.data.decode(errors="ignore").split("redeem_", 1)[1].strip().upper()
    except Exception:
        code = ""
    if not code:
        try:
            await e.answer("Invalid code.", alert=True)
        except Exception:
            pass
        return
    redeem_fn = ctx.get("redeem_code_fn") if isinstance(ctx, dict) else getattr(ctx, "redeem_code_fn", None)
    if redeem_fn is None:
        try:
            await e.answer("Redeem unavailable.", alert=True)
        except Exception:
            pass
        return
    try:
        ok, text, info = await redeem_fn(int(e.sender_id), code)
    except Exception as ex:
        try:
            await e.answer(f"Failed: {ex}", alert=True)
        except Exception:
            pass
        return
    try:
        await e.answer("Redeemed!" if ok else "Failed", alert=False)
    except Exception:
        pass
    if ok and info:
        try:
            notify = ctx.get("notify_redeem") if isinstance(ctx, dict) else getattr(ctx, "notify_redeem", None)
            if callable(notify):
                await notify(int(e.sender_id), info)
        except Exception:
            pass
    try:
        await bot.send_message(int(e.sender_id), text, parse_mode="markdown")
    except Exception:
        try:
            await e.reply(text)
        except Exception:
            pass


def register(bot, ctx):
    """Wire /quick, /preview, /broadcast + gift-card buttons."""
    db = _ctx(ctx, "db")
    owner_id = _ctx(ctx, "OWNER_ID")
    get_files_fn = _ctx(ctx, "get_files")
    download_single = _ctx(ctx, "download_single")
    get_all_users = _ctx(ctx, "get_all_users")

    @bot.on(events.NewMessage(pattern=r"/quick\s+(\S+)", incoming=True, outgoing=False))
    async def _quick(m):
        link = m.pattern_match.group(1).strip()
        if not get_files_fn or not download_single:
            return await m.reply("Quick-download is not configured.")
        files = await get_files_fn(link)
        if not files:
            return await m.reply("Sorry! API is dead or link is broken.")
        f = files[0]
        w = build_expiry_warning(f.get("expires_in", ""))
        if len(files) > 1:
            await m.reply(f"Single-file mode: downloading 1 of {len(files)} files." + (f"\n\n{w}" if w else ""))
        elif w:
            await m.reply(w)
        try:
            await download_single(m, f)
        except TypeError:
            await download_single(m)

    @bot.on(events.NewMessage(pattern=r"/preview\s+(\S+)", incoming=True, outgoing=False))
    async def _preview(m):
        link = m.pattern_match.group(1).strip()
        if not get_files_fn:
            return await m.reply("Preview is not configured.")
        files = await get_files_fn(link)
        if not files:
            return await m.reply("Sorry! API is dead or link is broken.")
        text = build_preview_text(files)
        w = build_expiry_warning(files[0].get("expires_in", ""))
        await m.reply(text + (f"\n\n{w}" if w else ""), parse_mode="markdown")

    @bot.on(events.CallbackQuery(pattern=rb"redeem_"))
    async def _redeem_btn(e):
        await _auto_redeem_button(e, bot, ctx)

    @bot.on(events.NewMessage(pattern="/broadcast", incoming=True, outgoing=False))
    async def _broadcast(m):
        if owner_id is None or int(m.sender_id) != int(owner_id):
            return await m.reply("Owner only.")
        text = (m.text or "").split("/broadcast", 1)[1].strip() if "/broadcast" in (m.text or "") else ""
        if not text:
            return await m.reply("**Usage:** `/broadcast <message>`")
        if not get_all_users:
            return await m.reply("Broadcast source not configured.")
        res = get_all_users()
        if hasattr(res, "__await__"):
            res = await res
        ids = []
        for u in (res or []):
            try:
                ids.append(int(getattr(u, "id", u)))
            except Exception:
                continue
        chunks = broadcast_split(ids, text)
        status = await m.reply(f"Broadcasting to {len(ids)} users...")
        sent = failed = 0
        for ch in chunks:
            for uid in ch:
                try:
                    await bot.send_message(uid, text)
                    sent += 1
                except Exception:
                    failed += 1
            await asyncio.sleep(0.5)
        try:
            db.incr("stats:broadcasts")
        except Exception:
            pass
        await status.edit(f"**Broadcast Complete**\nTotal: **{len(ids)}**\nSent: **{sent}**\nFailed: **{failed}**", parse_mode="markdown")
