"""Analytics commands (/stats, /userstats, /apihealth, /errors).

Pure logic + thin Telethon handlers. NO imports from main.py
(avoids circular imports). All runtime deps come via register(bot, ctx).
ctx keys: db, is_admin, get_formatted_size, api_templates (+optional log_path).
"""
import asyncio
import os
import time

import aiohttp
from telethon import events

STATS_KEY = "bot_stats"
USER_STATS_PREFIX = "user_stats_"
CUSTOM_TAGS_KEY = "custom_tags"
DEFAULT_LOG = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bot.log")
)


LINK_COUNTS_KEY = "link_counts"  # ZSET: link-id -> downloads


def track_download(db, user_id, size_bytes, link=None, ok=True):
    """Record one download attempt: attempts always; success adds total/storage.

    Keeps legacy `total` (= successes) so existing readers keep working.
    """
    try:
        ukey = f"{USER_STATS_PREFIX}{int(user_id)}"
        size = int(size_bytes or 0)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            db.hincrby(ukey, "attempts", 1)
        except Exception:
            pass
        if ok:
            db.hincrby(ukey, "total", 1)
            try:
                db.hincrby(ukey, "success", 1)
            except Exception:
                pass
            if size > 0:
                db.hincrby(ukey, "storage", size)
            db.hset(ukey, "last_activity", now)
            db.hincrby(STATS_KEY, "total_downloads", 1)
            if link:
                try:
                    db.zincrby(LINK_COUNTS_KEY, 1, str(link)[:120])
                except Exception:
                    pass
                try:
                    db.zremrangebyrank(LINK_COUNTS_KEY, 0, -501)
                except Exception:
                    pass
        else:
            try:
                db.hincrby(ukey, "failed", 1)
            except Exception:
                pass
        return True
    except Exception:
        return False


def get_top_links(db, limit=3):
    """Return [(link_id, count)] most downloaded links."""
    try:
        rows = db.zrevrange(LINK_COUNTS_KEY, 0, int(limit) - 1, withscores=True)
        return [(str(link), int(score)) for link, score in (rows or [])]
    except Exception:
        return []


def _coerce_top(top_users, limit=5):
    rows = []
    for u in (top_users or [])[:limit]:
        if isinstance(u, (list, tuple)) and len(u) >= 3:
            rows.append((str(u[0]), int(u[1]), u[2]))
        elif isinstance(u, (list, tuple)) and len(u) >= 2:
            rows.append((str(u[0]), int(u[1]), ""))
        elif isinstance(u, dict):
            uid = u.get("user_id", u.get("id", "?"))
            n = u.get("downloads", u.get("total", 0))
            rows.append((str(uid), int(n), u.get("name", "")))
    return rows


async def resolve_user_names(bot, user_ids):
    """Map user IDs to 'Full Name (@username)'. Failures map to ''."""
    out = {}
    for uid in user_ids or []:
        try:
            u = await bot.get_entity(int(uid))
            name = (u.first_name or "").strip()
            if getattr(u, "last_name", None):
                name = f"{name} {u.last_name}".strip()
            if getattr(u, "username", None):
                name = f"{name} (@{u.username})".strip()
            out[str(uid)] = name
        except Exception:
            out[str(uid)] = ""
    return out


def build_stats_text(global_stats, top_users, top_links=None):
    """Pure /stats formatter."""
    g = global_stats or {}
    dl = int(g.get("total_downloads", 0) or 0)
    users = int(g.get("total_users", 0) or 0)
    lines = ["**Bot Statistics**", "",
             f"**Total Downloads:** {dl}",
             f"**Total Users:** {users}"]
    for k, label in (("active_today", "Active Today"), ("premium_count", "Premium Users"),
                     ("banned_count", "Banned Users"), ("gift_cards", "Gift Cards")):
        if k in g and g[k] is not None:
            lines.append(f"**{label}:** {g[k]}")
    lines += ["", "**Top 5 Users:**"]
    rows = _coerce_top(top_users)
    if not rows:
        lines.append("_No user data yet._")
    else:
        for i, (uid, n, name) in enumerate(rows, 1):
            who = f"{name} `{uid}`" if name else f"`{uid}`"
            lines.append(f"{i}. {who} — {n} downloads")
    links = list(top_links or [])
    if links:
        lines += ["", "**Popular Links:**"]
        for i, (link, n) in enumerate(links[:3], 1):
            lines.append(f"{i}. `{link}` — {n} downloads")
    return "\n".join(lines)


def _fmt_size(n):
    n = int(n or 0)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n:.2f} b"


def build_userstats_text(user_id, stats, premium_text, tag):
    """Pure per-user formatter."""
    s = stats or {}
    dl = s.get("downloads", s.get("total", 0))
    try:
        dl = int(dl or 0)
    except Exception:
        dl = 0
    try:
        storage = _fmt_size(int(s.get("storage", 0) or 0))
    except Exception:
        storage = "0.00 b"
    last = s.get("last_activity", "Never")
    tag_line = f"Tag: **{tag}**" if tag else "No custom tag"
    return (f"**User Stats — `{user_id}`**\n\n"
            f"**Premium:** {premium_text or 'N/A'}\n{tag_line}\n"
            f"**Downloads:** {dl}\n**Storage:** {storage}\n"
            f"**Last activity:** {last}")


HEALTH_PROBE_LINK = "https://www.terabox.com/s/1healthcheck"


async def check_api_health(api_templates, timeout=10):
    """Async health probe using aiohttp directly.

    Probes with a dummy link (bare `url=` gets rejected with 400 even when
    the server is fine). Any response below 500 means the server is
    reachable; 5xx/timeout means down.
    """
    out = {}
    items = api_templates.items() if isinstance(api_templates, dict) else enumerate(api_templates or [])
    t = aiohttp.ClientTimeout(total=timeout, connect=10, sock_read=10)
    async with aiohttp.ClientSession(timeout=t) as sess:
        for name, tpl in items:
            if isinstance(tpl, str) and "{url}" in tpl:
                url = tpl.replace("{url}", HEALTH_PROBE_LINK)
            else:
                url = str(tpl)
            key = str(name)
            t0 = time.monotonic()
            try:
                async with sess.get(url) as r:
                    ms = int((time.monotonic() - t0) * 1000)
                    if r.status in (200, 302):
                        state = "UP"
                    elif r.status < 500:
                        state = "REACHABLE"
                    else:
                        state = "DOWN"
                    out[key] = {"ok": r.status < 500, "state": state,
                                "latency_ms": ms, "status": r.status}
            except Exception:
                out[key] = {"ok": False, "state": "DOWN",
                            "latency_ms": int((time.monotonic() - t0) * 1000), "status": None}
    return out


def get_recent_errors(log_path, n=15):
    """Tail log_path, keep ERROR/Failed lines."""
    try:
        n = max(1, min(int(n or 15), 100))
        with open(log_path, "r", errors="ignore") as f:
            lines = f.readlines()
        hits = [ln.rstrip("\n") for ln in lines
                if ("ERROR" in ln or "Error" in ln or "Failed" in ln
                    or "failed" in ln or "Traceback" in ln)]
        return hits[-n:] if hits else []
    except Exception:
        return []


def register(bot, ctx):
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    api_templates = ctx.get("api_templates", {})
    log_path = ctx.get("log_path", DEFAULT_LOG)

    @bot.on(events.NewMessage(pattern="/stats", incoming=True, outgoing=False,
                              func=lambda m: is_admin(m.sender_id)))
    async def _stats(m):
        try:
            g = {"total_downloads": int(db.hget(STATS_KEY, "total_downloads") or 0),
                 "total_users": int(db.hget(STATS_KEY, "total_users") or 0)}
        except Exception:
            g = {"total_downloads": 0, "total_users": 0}
        try:
            g["active_today"] = int(db.get(f"active_{time.strftime('%Y-%m-%d')}") or 0)
        except Exception:
            pass
        try:
            g["premium_count"] = len(db.smembers("premium_users"))
        except Exception:
            pass
        try:
            g["banned_count"] = len(db.smembers("banned_users"))
        except Exception:
            pass
        try:
            g["gift_cards"] = db.hlen("gift_cards")
        except Exception:
            pass
        top = []
        try:
            for k in db.scan_iter(f"{USER_STATS_PREFIX}*", count=200):
                try:
                    h = db.hgetall(k)
                    uid = k.split("_")[-1]
                    top.append((uid, int(h.get("total", 0) or 0)))
                except Exception:
                    continue
            top.sort(key=lambda x: x[1], reverse=True)
        except Exception:
            top = []
        top5 = top[:5]
        try:
            names = await resolve_user_names(bot, [u for u, _ in top5])
        except Exception:
            names = {}
        top5 = [(u, n, names.get(str(u), "")) for u, n in top5]
        await m.reply(build_stats_text(g, top5, get_top_links(db, 3)), parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/userstats(?:\s+(\d+))?", incoming=True,
                              outgoing=False, func=lambda m: is_admin(m.sender_id)))
    async def _userstats(m):
        arg = m.pattern_match.group(1)
        target = int(arg) if arg else m.sender_id
        try:
            h = db.hgetall(f"{USER_STATS_PREFIX}{target}") or {}
            stats = {"downloads": int(h.get("total", 0) or 0),
                     "storage": int(h.get("storage", 0) or 0),
                     "last_activity": h.get("last_activity", "Never")}
        except Exception:
            stats = {"downloads": 0, "storage": 0, "last_activity": "Never"}
        try:
            tag = db.hget(CUSTOM_TAGS_KEY, str(target))
        except Exception:
            tag = None
        await m.reply(build_userstats_text(target, stats, "N/A", tag),
                      parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/apihealth$", incoming=True, outgoing=False,
                              func=lambda m: is_admin(m.sender_id)))
    async def _apihealth(m):
        res = await check_api_health(api_templates, timeout=10)
        if not res:
            return await m.reply("No API templates configured.")
        lines = ["**API Health**", ""]
        for name, r in res.items():
            state = r.get("state", "UP" if r["ok"] else "DOWN")
            lines.append(f"{state} **{name}**: ok={r['ok']} "
                         f"status={r['status']} {r['latency_ms']}ms")
        lines += ["", "_UP = healthy | REACHABLE = server alive (probe link rejected) | DOWN = failing_"]
        await m.reply("\n".join(lines), parse_mode="markdown")

    @bot.on(events.NewMessage(pattern=r"^/errors(?:\s+(\d+))?", incoming=True,
                              outgoing=False, func=lambda m: is_admin(m.sender_id)))
    async def _errors(m):
        n = int(m.pattern_match.group(1) or 15)
        errs = await asyncio.get_event_loop().run_in_executor(
            None, get_recent_errors, log_path, n)
        if not errs:
            return await m.reply("No errors found in log.")
        txt = "\n".join(errs)[-3000:]
        await m.reply(f"```\n{txt}\n```", parse_mode="markdown")
