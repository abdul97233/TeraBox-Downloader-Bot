"""Advanced Telegram config editor (no restart, no secrets).

Secrets (tokens, API keys, passwords, IDs) are NEVER editable here —
attempting them returns an explicit refusal. API templates live under
/setapi + /reloadconfig.

Single source of truth: SPECS. main.py imports SPECS + validate and owns
applying values to live globals.
"""

import re as _re

SECTIONS = ("Limits", "Uploads", "Watermark", "Force Join", "Maintenance")

SPECS = {
    "MAX_FILES_PER_REQUEST": {
        "section": "Limits", "kind": "int", "min": 1, "max": 50,
        "desc": "Max files processed per link (premium).",
    },
    "DOWNLOAD_COOLDOWN_SECONDS": {
        "section": "Limits", "kind": "int", "min": 0, "max": 300,
        "desc": "Cooldown between links for free users (0 = off).",
    },
    "PARALLEL_DOWNLOADS": {
        "section": "Limits", "kind": "int", "min": 1, "max": 10,
        "desc": "How many files download at once.",
    },
    "CLEANUP_INTERVAL": {
        "section": "Maintenance", "kind": "int", "min": 600, "max": 86400,
        "desc": "Auto-delete downloads older than N seconds.",
    },
    "TG_API_BASE": {
        "section": "Uploads", "kind": "url",
        "desc": "Self-hosted Telegram Bot API base URL.",
    },
    "DOWNLOAD_DIR": {
        "section": "Uploads", "kind": "dirname",
        "desc": "Local folder for downloads.",
    },
    "WATERMARK_TEXT": {
        "section": "Watermark", "kind": "wtext",
        "desc": "Watermark text (1-40 chars, no quotes).",
    },
    "FORCE_CHANNELS": {
        "section": "Force Join", "kind": "csv",
        "desc": "Channels users must join (comma-separated).",
    },
    "FORCE_GROUPS": {
        "section": "Force Join", "kind": "csv",
        "desc": "Groups users must join (comma-separated).",
    },
}

BLOCKED = {
    "BOT_TOKEN", "API_ID", "API_HASH", "HOST", "PORT", "PASSWORD",
    "PRIVATE_CHAT_ID", "OWNER_ID", "ADMINS", "TERABOX_API_TOKEN",
    "TERABOX_API_BASE", "TERABOX_FALLBACK_API_BASE",
    "TERABOX_API_TEMPLATE", "TERABOX_FALLBACK_API_TEMPLATE",
}

_TOKEN_RE = _re.compile(r"^(?:@[\w]{3,64}|-100\d{5,32})$")


def validate_config_value(key, raw):
    """Validate + coerce a value. Returns (ok, value, err)."""
    key = str(key or "").strip().upper()
    if key in BLOCKED:
        hint = "/setapi" if "TERABOX" in key else "config.py on the server"
        return False, None, f"`{key}` is protected — edit via {hint}."
    spec = SPECS.get(key)
    if spec is None:
        return False, None, f"Unknown key. Editable: `{', '.join(sorted(SPECS))}`"
    kind = spec["kind"]
    try:
        if kind == "int":
            v = int(str(raw).strip())
            if not (spec["min"] <= v <= spec["max"]):
                return False, None, f"`{key}` must be {spec['min']}-{spec['max']}."
            return True, v, ""
        if kind == "url":
            v = str(raw).strip().rstrip("/")
            if not v.startswith("http") or len(v) > 200 or " " in v:
                return False, None, f"`{key}` must be an http(s) URL."
            return True, v, ""
        if kind == "dirname":
            v = str(raw).strip()
            if (not v or len(v) > 64 or v.startswith("/") or ".." in v
                    or not _re.fullmatch(r"[\w][\w.\-]*", v)):
                return False, None, f"`{key}` must be a simple folder name."
            return True, v, ""
        if kind == "wtext":
            v = str(raw).strip()
            if not v or len(v) > 40 or "'" in v or "\n" in v:
                return False, None, f"`{key}` must be 1-40 chars, no quotes."
            return True, v, ""
        if kind == "csv":
            items = [p.strip() for p in str(raw).split(",") if p.strip()]
            if not items or len(items) > 20:
                return False, None, f"`{key}` needs 1-20 entries."
            for t in items:
                if not _TOKEN_RE.match(t):
                    return False, None, f"Bad entry `{t}` (use @name or -100id)."
            return True, items, ""
    except Exception as e:
        return False, None, f"Invalid value: `{e}`"
    return False, None, "Unsupported type."


def parse_config_set(text):
    """Parse '/configset KEY VALUE...' -> (KEY, raw_value) or (None, err)."""
    parts = (text or "").split(None, 2)
    if len(parts) != 3:
        return None, "**Usage:** `/configset <KEY> <VALUE>`"
    key = parts[1].strip().upper()
    if key in BLOCKED:
        return None, f"`{key}` is protected and can never be edited from Telegram."
    if key not in SPECS:
        return None, f"Unknown key. Editable: `{', '.join(sorted(SPECS))}`"
    return (key, parts[2]), ""


def _fmt_value(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) or "-"
    return str(v)


def build_config_view_text(runtime):
    lines = ["**Runtime Config**", ""]
    for section in SECTIONS:
        keys = [k for k, s in SPECS.items() if s["section"] == section]
        if not keys:
            continue
        lines.append(f"__{section}__")
        for key in keys:
            lines.append(f"`{key}` = **{_fmt_value((runtime or {}).get(key, '?'))}**")
        lines.append("")
    lines.append("Edit: `/configset <KEY> <VALUE>` · Reset: `/configreset <KEY>` (admin only).")
    return "\n".join(lines)


def register(bot, ctx):
    from telethon import events
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    log_audit = ctx["log_audit"]
    get_runtime = ctx["get_runtime"]
    set_runtime = ctx["set_runtime"]
    reset_runtime = ctx.get("reset_runtime")

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
        key, raw = parsed
        ok, value, verr = validate_config_value(key, raw)
        if not ok:
            return await m.reply(verr, parse_mode="markdown")
        try:
            applied, msg = set_runtime(key, value)
        except Exception as e:
            return await m.reply(f"Failed: `{e}`")
        if applied:
            try:
                store = ",".join(value) if isinstance(value, list) else str(value)
                db.hset("config_overrides", key, store)
            except Exception:
                pass
            try:
                log_audit("CONFIGSET", m.sender_id, f"{key}={store}")
            except Exception:
                pass
            return await m.reply(f"Updated `{key}` = **{store}** (live, no restart).", parse_mode="markdown")
        await m.reply(msg or "Failed to apply.", parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/configreset(?:\s+(\S+))?$", incoming=True, outgoing=False,
                              func=lambda m: is_admin(m.sender_id)))
    async def _configreset(m):
        if reset_runtime is None:
            return await m.reply("Reset not wired.")
        arg = (m.pattern_match.group(1) or "").strip().upper()
        if not arg:
            return await m.reply("**Usage:** `/configreset <KEY>`", parse_mode="markdown")
        if arg in BLOCKED or arg not in SPECS:
            return await m.reply(f"Unknown or protected key: `{arg}`")
        try:
            ok, msg = reset_runtime(arg)
        except Exception as e:
            return await m.reply(f"Failed: `{e}`")
        if ok:
            try:
                db.hdel("config_overrides", arg)
            except Exception:
                pass
            try:
                log_audit("CONFIGRESET", m.sender_id, arg)
            except Exception:
                pass
            return await m.reply(f"`{arg}` reset to default ({msg}).", parse_mode="markdown")
        await m.reply(msg or "Failed to reset.", parse_mode="markdown")
