"""Full backup + restore pack (/backup, /restore).

Covers every key family the bot owns. Restore MERGES (backup values are
added/overwrite; nothing is flushed). No main.py imports.
"""

SETS = ["premium_users", "banned_users", "dynamic_admins", "all_known_users"]
HASHES = ["premium_expiry", "custom_tags", "gift_cards", "gc_tags",
          "gc_used", "bot_stats", "config_overrides"]
HASH_PREFIXES = ["user_stats_"]
STRINGS = ["storage_chat_id", "maintenance_mode", "maintenance_mode:reason",
           "stats:broadcasts", "stats:boot_count"]
STRING_PREFIXES = ["history_", "gc_redeemed_"]
LISTS = ["audit_log"]
ZSETS = ["link_counts"]


def _scan(db, match):
    try:
        return list(db.scan_iter(match, count=500))
    except Exception:
        return []


def collect_backup(db):
    """Snapshot everything into a JSON-serializable dict."""
    data = {"sets": {}, "hashes": {}, "strings": {}, "lists": {}, "zsets": {}}
    for key in SETS:
        try:
            data["sets"][key] = sorted(db.smembers(key) or [])
        except Exception:
            pass
    for key in HASHES:
        try:
            data["hashes"][key] = dict(db.hgetall(key) or {})
        except Exception:
            pass
    for prefix in HASH_PREFIXES:
        for key in _scan(db, f"{prefix}*"):
            try:
                data["hashes"][key] = dict(db.hgetall(key) or {})
            except Exception:
                pass
    for key in STRINGS:
        try:
            val = db.get(key)
            if val is not None:
                data["strings"][key] = val
        except Exception:
            pass
    for prefix in STRING_PREFIXES:
        for key in _scan(db, f"{prefix}*"):
            try:
                val = db.get(key)
                if val is not None:
                    data["strings"][key] = val
            except Exception:
                pass
    for key in LISTS:
        try:
            data["lists"][key] = list(db.lrange(key, 0, -1) or [])
        except Exception:
            pass
    for key in ZSETS:
        try:
            data["zsets"][key] = [[m, s] for m, s in (db.zrange(key, 0, -1, withscores=True) or [])]
        except Exception:
            pass
    return data


def summarize_backup(data):
    """Counts per section for captions/confirmations."""
    try:
        return {
            "sets": sum(len(v) for v in (data.get("sets") or {}).values()),
            "hashes": sum(len(v) for v in (data.get("hashes") or {}).values()),
            "strings": len(data.get("strings") or {}),
            "lists": sum(len(v) for v in (data.get("lists") or {}).values()),
            "zsets": sum(len(v) for v in (data.get("zsets") or {}).values()),
        }
    except Exception:
        return {}


def build_backup_caption(summary):
    s = summary or {}
    return (
        "**Redis Backup**\n"
        f"Sets: {s.get('sets', 0)} | Hashes: {s.get('hashes', 0)} | "
        f"Strings: {s.get('strings', 0)} | Lists: {s.get('lists', 0)} | "
        f"ZSets: {s.get('zsets', 0)}\n"
        "Restore: reply to this file with `/restore`"
    )


def apply_restore(db, data):
    """Merge a backup dict back into Redis. Returns counts dict."""
    counts = {"sets": 0, "hashes": 0, "strings": 0, "lists": 0, "zsets": 0}
    if not isinstance(data, dict):
        raise ValueError("Backup file is not a JSON object.")
    for key, members in (data.get("sets") or {}).items():
        for member in members or []:
            try:
                db.sadd(key, member)
                counts["sets"] += 1
            except Exception:
                pass
    for key, mapping in (data.get("hashes") or {}).items():
        for field, value in (mapping or {}).items():
            try:
                db.hset(key, field, value)
                counts["hashes"] += 1
            except Exception:
                pass
    for key, value in (data.get("strings") or {}).items():
        try:
            db.set(key, value)
            counts["strings"] += 1
        except Exception:
            pass
    for key, items in (data.get("lists") or {}).items():
        try:
            db.delete(key)
            if items:
                db.rpush(key, *items)
                counts["lists"] += len(items)
        except Exception:
            pass
    for key, pairs in (data.get("zsets") or {}).items():
        for member, score in (pairs or []):
            try:
                db.zadd(key, {member: float(score)})
                counts["zsets"] += 1
            except Exception:
                pass
    return counts


def register(bot, ctx):
    import json as _json
    import os as _os
    from telethon import events
    db = ctx["db"]
    owner_id = ctx.get("OWNER_ID")
    download_dir = ctx.get("download_dir", "downloads")

    def _owner(m):
        try:
            return owner_id is not None and int(m.sender_id) == int(owner_id)
        except Exception:
            return False

    @bot.on(events.NewMessage(pattern=r"^/backup$", incoming=True, outgoing=False))
    async def _backup(m):
        if not _owner(m):
            return
        msg = await m.reply("Backing up Redis data...")
        try:
            data = collect_backup(db)
            summary = summarize_backup(data)
            try:
                _os.makedirs(download_dir, exist_ok=True)
            except Exception:
                pass
            path = _os.path.join(download_dir, "backup.json")
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(data, f, indent=2, default=str)
            await bot.send_file(
                m.chat.id, file=path,
                caption=build_backup_caption(summary), parse_mode="markdown",
            )
            try:
                _os.unlink(path)
            except Exception:
                pass
            await msg.delete()
        except Exception as e:
            await msg.edit(f"Backup failed: `{e}`")

    @bot.on(events.NewMessage(pattern=r"^/restore$", incoming=True, outgoing=False))
    async def _restore(m):
        if not _owner(m):
            return
        if not m.is_reply:
            return await m.reply("Reply to a backup `.json` file with `/restore`.")
        try:
            replied = await m.get_reply_message()
            if not replied or not replied.document:
                return await m.reply("Reply to a backup `.json` file with `/restore`.")
            path = await bot.download_media(replied, file=download_dir + "/")
        except Exception as e:
            return await m.reply(f"Could not download file: `{e}`")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            counts = apply_restore(db, data)
        except Exception as e:
            return await m.reply(f"Restore failed: `{e}`")
        finally:
            try:
                _os.unlink(path)
            except Exception:
                pass
        await m.reply(
            "**Restore complete (merged).**\n"
            f"Sets: {counts['sets']} | Hashes: {counts['hashes']} | "
            f"Strings: {counts['strings']} | Lists: {counts['lists']} | "
            f"ZSets: {counts['zsets']}\n"
            "Restart the bot if values look stale.",
            parse_mode="markdown",
        )
