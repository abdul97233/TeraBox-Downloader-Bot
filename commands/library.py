"""Searchable library: every upload indexed, /search serves from storage.

No main.py imports. Storage chat passed via ctx (callable supported).
"""

import json as _json
import re as _re

from telethon import Button, events

INDEX_KEY = "lib:index"
SESSION_TTL = 300
MAX_RESULTS = 8


def normalize_name(name):
    """desi_Maal (2024) 720p.mp4 -> 'desi maal 2024 720p'."""
    try:
        s = str(name or "").lower()
        s = _re.sub(r"\.[a-z0-9]{2,5}$", "", s.strip())
        s = _re.sub(r"[^a-z0-9]+", " ", s)
        return _re.sub(r"\s+", " ", s).strip()
    except Exception:
        return ""


def index_file(db, storage_mid, file_name, size_str="", sizebytes=0):
    """Add one upload to the index. Idempotent per message id."""
    norm = normalize_name(file_name)
    if not norm:
        return False
    try:
        raw = db.hget(INDEX_KEY, norm)
        entries = _json.loads(raw) if raw else []
    except Exception:
        entries = []
    try:
        mid = int(storage_mid)
    except Exception:
        return False
    if any(e.get("mid") == mid for e in entries):
        return True
    entries.append({"mid": mid, "name": str(file_name)[:120],
                    "size": str(size_str or "?"), "bytes": int(sizebytes or 0)})
    entries = entries[-5:]
    try:
        db.hset(INDEX_KEY, norm, _json.dumps(entries))
        return True
    except Exception:
        return False


def drop_entry(db, norm, mid):
    try:
        raw = db.hget(INDEX_KEY, norm)
        entries = _json.loads(raw) if raw else []
        kept = [e for e in entries if e.get("mid") != mid]
        if kept:
            db.hset(INDEX_KEY, norm, _json.dumps(kept))
        else:
            db.hdel(INDEX_KEY, norm)
    except Exception:
        pass


def search_index(db, query, limit=MAX_RESULTS):
    """AND-match first, OR fallback. Returns [{mid, name, size, norm}]."""
    qtokens = normalize_name(query).split()
    if not qtokens:
        return []
    try:
        all_items = db.hgetall(INDEX_KEY) or {}
    except Exception:
        return []
    scored = []
    for norm, raw in all_items.items():
        try:
            entries = _json.loads(raw)
        except Exception:
            continue
        etokens = set(str(norm).split())
        hits = sum(1 for t in qtokens if t in etokens)
        if not hits:
            continue
        for e in entries:
            scored.append((hits == len(qtokens), hits, e, norm))
    scored.sort(key=lambda r: (r[0], r[1]), reverse=True)
    if scored and not scored[0][0]:
        pass
    out = []
    for full, hits, e, norm in scored:
        if not full and out:
            break
        out.append({"mid": e.get("mid"), "name": e.get("name", "?"),
                    "size": e.get("size", "?"), "norm": norm})
        if len(out) >= limit:
            break
    return out


def _session_key(uid):
    return f"lib:search:{int(uid)}"


def register(bot, ctx):
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    owner_id = ctx.get("OWNER_ID")
    storage = ctx.get("storage_chat")

    def _storage():
        try:
            return storage() if callable(storage) else storage
        except Exception:
            return None

    @bot.on(events.NewMessage(pattern=r"^/search(?:\s+(.*))?$", incoming=True, outgoing=False))
    async def _search(m):
        q = (m.pattern_match.group(1) or "").strip()
        if not q:
            return await m.reply("**Usage:** `/search <movie or file name>`")
        results = search_index(db, q)
        if not results:
            return await m.reply(f"No library hits for `{q}`.\nSend the TeraBox link to download it fresh.")
        try:
            db.set(_session_key(m.sender_id), _json.dumps(results), ex=SESSION_TTL)
        except Exception:
            pass
        buttons = [[Button.inline(f"📥 {r['name'][:40]} ({r['size']})", data=f"lib_{i}")]
                   for i, r in enumerate(results)]
        buttons.append([Button.inline("Close", data="lib_close")])
        await m.reply(f"**Library hits for `{q}`:**", parse_mode="markdown", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"lib_"))
    async def _lib_btn(e):
        try:
            data = e.data.decode(errors="ignore")
        except Exception:
            data = ""
        if data == "lib_close":
            try:
                await e.delete()
            except Exception:
                pass
            return
        if not data.startswith("lib_"):
            return
        try:
            idx = int(data.split("lib_", 1)[1])
        except Exception:
            try:
                await e.answer("Invalid selection.", alert=True)
            except Exception:
                pass
            return
        try:
            raw = db.get(_session_key(e.sender_id))
            results = _json.loads(raw) if raw else []
        except Exception:
            results = []
        if not results or idx >= len(results):
            try:
                await e.answer("Expired — /search again.", alert=True)
            except Exception:
                pass
            return
        r = results[idx]
        store = _storage()
        try:
            check = await bot.get_messages(store, ids=[int(r["mid"])]) if store else []
        except Exception:
            check = []
        alive = check and (check.media if not isinstance(check, list) else any(mm and mm.media for mm in check))
        if not alive:
            drop_entry(db, r.get("norm", ""), r.get("mid"))
            try:
                await e.answer("Removed stale entry — resend the link to fetch fresh.", alert=True)
            except Exception:
                pass
            return
        from telethon.tl.functions.messages import ForwardMessagesRequest
        try:
            await bot(ForwardMessagesRequest(
                from_peer=store, id=[int(r["mid"])],
                to_peer=int(e.sender_id), drop_author=True, background=True,
            ))
            try:
                db.hincrby("bot_stats", "lib_hits", 1)
            except Exception:
                pass
            try:
                await e.answer("Sent from library!", alert=False)
            except Exception:
                pass
        except Exception:
            try:
                await e.answer("Delivery failed — try again.", alert=True)
            except Exception:
                pass

    @bot.on(events.NewMessage(pattern=r"^/reindex$", incoming=True, outgoing=False))
    async def _reindex(m):
        try:
            allowed = (owner_id is not None and int(m.sender_id) == int(owner_id)) or bool(is_admin(m.sender_id))
        except Exception:
            allowed = False
        if not allowed:
            return
        store = _storage()
        if not store:
            return await m.reply("Storage chat not configured.")
        try:
            from tools import get_formatted_size as _fmt
        except Exception:
            _fmt = lambda b: str(b)
        status = await m.reply("Indexing storage chat... (this takes a while)")
        added, scanned = 0, 0
        try:
            async for msg in bot.iter_messages(store, limit=2000):
                scanned += 1
                try:
                    fname, fsize = None, 0
                    try:
                        if msg.file and msg.file.name:
                            fname = msg.file.name
                            fsize = int(msg.file.size or 0)
                    except Exception:
                        pass
                    if not fname:
                        try:
                            cap = msg.text or ""
                            mm = _re.search(r"𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚:\s*`([^`]+)`", cap)
                            if mm:
                                fname = mm.group(1)
                        except Exception:
                            pass
                    if fname and msg.id:
                        if index_file(db, msg.id, fname, _fmt(fsize), fsize):
                            added += 1
                except Exception:
                    pass
                if scanned % 200 == 0:
                    try:
                        await status.edit(f"Indexing... {scanned} scanned, {added} new.")
                    except Exception:
                        pass
        except Exception as e:
            return await status.edit(f"Reindex failed: `{e}`")
        await status.edit(f"✅ Library ready: {scanned} scanned, {added} new entries.\nTry /search <name>.")
