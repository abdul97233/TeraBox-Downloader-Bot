"""Telegram-based config editor (no restart needed).

Edits a small whitelist of runtime settings. Secrets (tokens, API keys,
Redis password) are NEVER editable here. All deps via ctx:
  db, is_admin, log_audit, get_runtime (-> dict), set_runtime (key, value).
"""

EDITABLE = {
    "MAX_FILES_PER_REQUEST": (1, 50),
    "DOWNLOAD_COOLDOWN_SECONDS": (0, 300),
    "PARALLEL_DOWNLOADS": (1, 10),
}


def parse_config_set(text):
    """Parse '/configset KEY VALUE' -> (KEY, VALUE) or (None, usage)."""
    parts = (text or "").split()
    if len(parts) != 3:
        return None, "**Usage:** `/configset <KEY> <VALUE>`"
    _, key, value = parts
    key = key.strip().upper()
    if key not in EDITABLE:
        return None, f"Unknown key. Editable: `{', '.join(sorted(EDITABLE))}`"
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return None, f"`{key}` must be an integer."
    lo, hi = EDITABLE[key]
    if not (lo <= ivalue <= hi):
        return None, f"`{key}` must be between {lo} and {hi}."
    return (key, ivalue), ""


def build_config_view_text(runtime):
    lines = ["**Runtime Config**", ""]
    for key in sorted(EDITABLE):
        lo, hi = EDITABLE[key]
        lines.append(f"`{key}` = **{runtime.get(key, '?')}** (range {lo}-{hi})")
    lines += ["", "Edit with `/configset <KEY> <VALUE>` (admin only)."]
    return "\n".join(lines)


def register(bot, ctx):
    from telethon import events
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    log_audit = ctx["log_audit"]
    get_runtime = ctx["get_runtime"]
    set_runtime = ctx["set_runtime"]

    @bot.on(events.NewMessage(pattern=r"^/configview$", incoming=True, outgoing=False,
                              func=lambda m: is_admin(m.sender_id)))
    async def _configview(m):
        try:
            runtime = get_runtime()
        except Exception:
            runtime = {}
        await m.reply(build_config_view_text(runtime or {}), parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/configset(?:\s+(.*))?$", incoming=True, outgoing=False,
                              func=lambda m: is_admin(m.sender_id)))
    async def _configset(m):
        parsed, err = parse_config_set(m.text)
        if err:
            return await m.reply(err, parse_mode="markdown")
        key, value = parsed
        try:
            ok, msg = set_runtime(key, value)
        except Exception as e:
            return await m.reply(f"Failed: `{e}`")
        if ok:
            try:
                db.hset("config_overrides", key, value)
            except Exception:
                pass
            try:
                log_audit("CONFIGSET", m.sender_id, f"{key}={value}")
            except Exception:
                pass
            return await m.reply(f"Updated `{key}` = **{value}** (live, no restart).", parse_mode="markdown")
        await m.reply(msg or "Failed to apply.", parse_mode="markdown")
