"""Maintenance / log / API-template commands.

PURE logic — no imports from main.py. All dependencies via ctx:
  db, is_admin, log_audit, maintenance_key, log_file, apply_api_templates
"""

import os


def set_maintenance(db, key, on, reason=""):
    """Set maintenance on/off. Stores reason at key+':reason'."""
    on = bool(on)
    if on:
        db.set(key, "1")
        if reason:
            db.set(f"{key}:reason", reason)
        else:
            try:
                db.delete(f"{key}:reason")
            except Exception:
                pass
    else:
        try:
            db.delete(key)
        except Exception:
            pass
        try:
            db.delete(f"{key}:reason")
        except Exception:
            pass
    return on


def get_maintenance(db, key):
    """Return (is_on: bool, reason: str)."""
    try:
        is_on = db.get(key) == "1"
    except Exception:
        is_on = False
    try:
        reason = db.get(f"{key}:reason") or ""
    except Exception:
        reason = ""
    if not isinstance(reason, str):
        reason = str(reason)
    return is_on, reason


def rotate_log(log_path, max_bytes=5_000_000, keep=3):
    """Size-based rotation: log -> log.1 .. log.keep."""
    if not log_path:
        return "Logrotate failed: empty log path."
    try:
        if not os.path.exists(log_path):
            return f"Log file not found: {log_path}"
        size = os.path.getsize(log_path)
        if size < max_bytes:
            return f"No rotation needed ({size} bytes < {max_bytes} bytes): {log_path}"
        keep = max(int(keep), 1)
        try:
            if os.path.exists(f"{log_path}.{keep}"):
                os.unlink(f"{log_path}.{keep}")
        except Exception:
            pass
        for i in range(keep, 1, -1):
            src, dst = f"{log_path}.{i - 1}", f"{log_path}.{i}"
            try:
                if os.path.exists(src):
                    if os.path.exists(dst):
                        os.unlink(dst)
                    os.rename(src, dst)
            except Exception:
                pass
        try:
            if os.path.exists(log_path):
                if os.path.exists(f"{log_path}.1"):
                    os.unlink(f"{log_path}.1")
                os.rename(log_path, f"{log_path}.1")
            open(log_path, "w", encoding="utf-8").close()
        except Exception:
            pass
        return f"Rotated {log_path} ({size} bytes), kept {keep} file(s)."
    except Exception as e:
        return f"Logrotate failed: {e}"


async def auto_rotate_loop(log_path, interval_hours=24, max_bytes=5_000_000, keep=3):
    """Background task: rotate bot.log when oversized (runs forever)."""
    import asyncio as _aio
    import time as _t
    while True:
        try:
            await _aio.sleep(float(interval_hours) * 3600)
        except Exception:
            break
        try:
            import os as _os
            if _os.path.exists(log_path) and _os.path.getsize(log_path) >= max_bytes:
                rotate_log(log_path, max_bytes, keep)
        except Exception:
            pass
        _ = _t.time()


def start_auto_rotate(bot_loop, log_path, interval_hours=24, max_bytes=5_000_000, keep=3):
    """Schedule the auto-rotate loop on an existing event loop."""
    return bot_loop.create_task(auto_rotate_loop(log_path, interval_hours, max_bytes, keep))


def _short(t, n=160):
    t = "-" if t is None else str(t)
    return t if len(t) <= n else t[:n] + "..."


def build_config_reload_text(new_values):
    """Report reloaded templates. No config import; values passed in."""
    vals = new_values or {}
    return ("Reloaded API templates without restart.\n"
            f"Primary: `{_short(vals.get('primary'))}`\n"
            f"Fallback: `{_short(vals.get('fallback'))}`")


def _persist_endpoints(db, lb):
    """Persist API endpoints list to Redis as JSON."""
    import json
    endpoints = []
    for ep in lb.endpoints:
        endpoints.append({
            "name": ep.name,
            "template": ep.template,
        })
    try:
        db.set("api_endpoints", json.dumps(endpoints))
    except Exception:
        pass


def register(bot, ctx):
    from telethon import events
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    log_audit = ctx["log_audit"]
    maintenance_key = ctx["maintenance_key"]
    log_file = ctx["log_file"]
    apply_api_templates = ctx.get("apply_api_templates")

    async def _deny(m):
        await m.reply("Not authorized.")

    @bot.on(events.NewMessage(pattern=r"^/maintenance(?:\s+(on|off))?(?:\s+(.*))?$"))
    async def _maintenance(m):
        if not is_admin(m.sender_id):
            return await _deny(m)
        arg = (m.pattern_match.group(1) or "").lower()
        reason = (m.pattern_match.group(2) or "").strip()
        if not arg:
            is_on, cur = get_maintenance(db, maintenance_key)
            txt = f"Maintenance is **{'ON' if is_on else 'OFF'}**"
            return await m.reply(txt + (f"\nReason: {cur}" if cur else ""))
        is_on = set_maintenance(db, maintenance_key, arg == "on", reason)
        try:
            log_audit(f"MAINTENANCE_{arg.upper()}", m.sender_id, reason)
        except Exception:
            pass
        await m.reply(f"Maintenance **{'ON' if is_on else 'OFF'}**" + (f"\nReason: {reason}" if reason else ""))

    @bot.on(events.NewMessage(pattern=r"^/logrotate$"))
    async def _logrotate(m):
        if not is_admin(m.sender_id):
            return await _deny(m)
        text = rotate_log(log_file)
        try:
            log_audit("LOGROTATE", m.sender_id, text[:200])
        except Exception:
            pass
        await m.reply(text)

    @bot.on(events.NewMessage(pattern=r"^/setapi(?:\s+(.*))?$"))
    async def _setapi(m):
        if not is_admin(m.sender_id):
            return await _deny(m)

        args = (m.pattern_match.group(1) or "").strip()

        # No args: show current endpoints + usage
        if not args:
            lines = ["**API Endpoints (Load Balanced)**", ""]
            try:
                from utils.loadbalancer import get_balancer
                lb = get_balancer()
                if lb:
                    for i, ep in enumerate(lb.endpoints, 1):
                        state = "🟢" if ep.healthy and not ep.is_circuit_open() else "🔴"
                        rate = f"{ep.success_rate:.0f}%"
                        lines.append(f"{state} `{i}.` **{ep.name}** — {rate} success, {ep.avg_latency_ms}ms avg")
                    lines.append(f"\n**Active:** {lb.active_count()}/{len(lb.endpoints)}")
            except Exception:
                lines.append("_Load balancer not initialized_")

            lines += [
                "",
                "**Commands:**",
                "`/setapi add <name> <url> [token]` — Add endpoint",
                "`/setapi remove <name>` — Remove endpoint",
                "`/setapi edit <name> <url> [token]` — Update endpoint",
                "`/setapi list` — Show all endpoints",
                "`/reloadconfig` — Rebuild load balancer",
            ]
            return await m.reply("\n".join(lines), parse_mode="markdown")

        parts = args.split()
        action = parts[0].lower()

        # --- list ---
        if action == "list":
            try:
                from utils.loadbalancer import get_balancer
                lb = get_balancer()
                if not lb:
                    return await m.reply("Load balancer not initialized.")
                lines = ["**API Endpoints:**", ""]
                for i, ep in enumerate(lb.endpoints, 1):
                    state = "🟢" if ep.healthy and not ep.is_circuit_open() else "🔴"
                    lines.append(f"{state} `{ep.name}`\n   URL: `{ep.template.split('?')[0]}`\n   Success: {ep.success_rate:.1f}% | Avg: {ep.avg_latency_ms}ms | Requests: {ep.request_count}")
                return await m.reply("\n".join(lines), parse_mode="markdown")
            except Exception as e:
                return await m.reply(f"Error: `{e}`")

        # --- add ---
        if action == "add":
            if len(parts) < 3:
                return await m.reply("**Usage:** `/setapi add <name> <url> [token]`", parse_mode="markdown")
            name = parts[1]
            url = parts[2].rstrip("/")
            token = parts[3] if len(parts) > 3 else ""
            if not url.startswith("http"):
                return await m.reply("URL must start with http(s).", parse_mode="markdown")
            try:
                from utils.loadbalancer import get_balancer, build_balancer
                import terabox as _tb
                lb = get_balancer()
                if not lb:
                    return await m.reply("Load balancer not initialized.")
                # Check duplicate name
                if any(ep.name == name for ep in lb.endpoints):
                    return await m.reply(f"Endpoint `{name}` already exists. Use `/setapi edit`.", parse_mode="markdown")
                # Build template
                if token:
                    template = f"{url}?authkey={token}&url={{url}}"
                else:
                    template = f"{url}?url={{url}}"
                # Add to list
                from utils.loadbalancer import APIEndpoint
                lb.endpoints.append(APIEndpoint(name, template))
                # Persist
                _persist_endpoints(db, lb)
                # Audit
                try:
                    log_audit("SETAPI_ADD", m.sender_id, f"{name}={url}")
                except Exception:
                    pass
                return await m.reply(f"✅ Added `{name}` → `{url}`\n**Active:** {lb.active_count()}/{len(lb.endpoints)}", parse_mode="markdown")
            except Exception as e:
                return await m.reply(f"Error: `{e}`")

        # --- remove ---
        if action == "remove":
            if len(parts) < 2:
                return await m.reply("**Usage:** `/setapi remove <name>`", parse_mode="markdown")
            name = parts[1]
            try:
                from utils.loadbalancer import get_balancer
                import terabox as _tb
                lb = get_balancer()
                if not lb:
                    return await m.reply("Load balancer not initialized.")
                # Don't remove if only 1 endpoint left
                if len(lb.endpoints) <= 1:
                    return await m.reply("Cannot remove the last endpoint.", parse_mode="markdown")
                # Find and remove
                idx = None
                for i, ep in enumerate(lb.endpoints):
                    if ep.name == name:
                        idx = i
                        break
                if idx is None:
                    return await m.reply(f"Endpoint `{name}` not found.", parse_mode="markdown")
                lb.endpoints.pop(idx)
                _persist_endpoints(db, lb)
                try:
                    log_audit("SETAPI_REMOVE", m.sender_id, name)
                except Exception:
                    pass
                return await m.reply(f"✅ Removed `{name}`\n**Active:** {lb.active_count()}/{len(lb.endpoints)}", parse_mode="markdown")
            except Exception as e:
                return await m.reply(f"Error: `{e}`")

        # --- edit ---
        if action == "edit":
            if len(parts) < 3:
                return await m.reply("**Usage:** `/setapi edit <name> <url> [token]`", parse_mode="markdown")
            name = parts[1]
            url = parts[2].rstrip("/")
            token = parts[3] if len(parts) > 3 else ""
            if not url.startswith("http"):
                return await m.reply("URL must start with http(s).", parse_mode="markdown")
            try:
                from utils.loadbalancer import get_balancer
                import terabox as _tb
                lb = get_balancer()
                if not lb:
                    return await m.reply("Load balancer not initialized.")
                # Find endpoint
                ep = None
                for e in lb.endpoints:
                    if e.name == name:
                        ep = e
                        break
                if not ep:
                    return await m.reply(f"Endpoint `{name}` not found.", parse_mode="markdown")
                # Update
                if token:
                    ep.template = f"{url}?authkey={token}&url={{url}}"
                else:
                    ep.template = f"{url}?url={{url}}"
                # Reset health on edit
                ep.circuit_open_until = 0
                ep.healthy = True
                ep.consecutive_fails = 0
                _persist_endpoints(db, lb)
                try:
                    log_audit("SETAPI_EDIT", m.sender_id, f"{name}={url}")
                except Exception:
                    pass
                return await m.reply(f"✅ Updated `{name}` → `{url}`", parse_mode="markdown")
            except Exception as e:
                return await m.reply(f"Error: `{e}`")

        # Legacy: /setapi primary|fallback <url_template>
        if action in ("primary", "fallback"):
            tpl = args.split(None, 1)[1] if len(parts) > 1 else ""
            if "{url}" not in tpl or not tpl.startswith("http"):
                return await m.reply("Usage: `/setapi <primary|fallback> <url_template>`\nTemplate must start with http and contain `{url}`.")
            slot = action
            try:
                db.set(f"api_template:{slot}", tpl)
            except Exception:
                pass
            applied = None
            if callable(apply_api_templates):
                try:
                    applied = apply_api_templates(**{slot: tpl})
                except Exception as e:
                    return await m.reply(f"Saved but apply failed: `{e}`")
            try:
                log_audit("SETAPI", m.sender_id, f"{slot}={tpl[:120]}")
            except Exception:
                pass
            if isinstance(applied, dict):
                return await m.reply(build_config_reload_text(applied))
            await m.reply(f"Saved `{slot}` template (live apply deferred).\n`{tpl[:160]}`")

        # Unknown action
        await m.reply("**Usage:**\n`/setapi` — show endpoints\n`/setapi add|remove|edit ...` — manage\n`/setapi primary|fallback <tpl>` — legacy", parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/reloadconfig$"))
    async def _reloadconfig(m):
        if not is_admin(m.sender_id):
            return await _deny(m)
        if not callable(apply_api_templates):
            return await m.reply("Reload not wired: `apply_api_templates` missing.")
        try:
            new_values = apply_api_templates()
        except Exception as e:
            return await m.reply(f"Reload failed: `{e}`")
        try:
            log_audit("RELOADCONFIG", m.sender_id, str(new_values)[:200])
        except Exception:
            pass
        await m.reply(build_config_reload_text(new_values if isinstance(new_values, dict) else {}))
