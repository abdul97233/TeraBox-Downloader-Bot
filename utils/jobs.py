"""Job registry + cancellable FFmpeg.

Single process design (bot runs one event loop):
- ACTIVE: in-memory job_id -> {task, procs, files, cancel event, msg}
- Redis HASH jobs:active:{uid}: job_id -> JSON (survives nothing, but lets
  /cancel list jobs even if memory was rebuilt; source of truth = memory).

Cancellation: set event -> cancel task -> SIGKILL procs -> delete partial
files -> drop Redis state. Safe to call repeatedly (idempotent).
"""

import asyncio
import contextlib
import json as _json
import os as _os
import subprocess as _sp
import time as _time
import uuid as _uuid

ACTIVE = {}
_ACTIVE_LOCK = None


def _lock():
    global _ACTIVE_LOCK
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    if _ACTIVE_LOCK is None:
        _ACTIVE_LOCK = asyncio.Lock()
    return _ACTIVE_LOCK


def _job_key(user_id):
    return f"jobs:active:{int(user_id)}"


def ffmpeg_run(cmd, timeout=300, job=None):
    """Blocking FFmpeg runner (call via run_in_executor).

    Registers the Popen on job["procs"] so /cancel can kill it.
    Raises asyncio.CancelledError on cancel, TimeoutError on timeout.
    Returns (returncode, stdout, stderr).
    """
    cancel_event = None
    procs = None
    if isinstance(job, dict):
        cancel_event = job.get("cancel")
        procs = job.get("procs")
    try:
        proc = _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.PIPE)
    except Exception as e:
        raise RuntimeError(f"ffmpeg start failed: {e}")
    if isinstance(procs, list):
        procs.append(proc)
    dying = False
    try:
        start = _time.monotonic()
        while True:
            if cancel_event is not None:
                try:
                    if cancel_event.is_set():
                        dying = True
                        raise asyncio.CancelledError()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            rc = proc.poll()
            if rc is not None:
                try:
                    out, err = proc.communicate(timeout=5)
                except Exception:
                    out, err = b"", b""
                return rc, _b2s(out), _b2s(err)
            if _time.monotonic() - start > timeout:
                dying = True
                raise TimeoutError(f"ffmpeg timed out after {timeout}s")
            _time.sleep(0.2)
    finally:
        try:
            if dying and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        try:
            if isinstance(procs, list) and proc in procs:
                procs.remove(proc)
        except Exception:
            pass


def _b2s(b):
    try:
        return b.decode("utf-8", "ignore") if isinstance(b, (bytes, bytearray)) else str(b or "")
    except Exception:
        return ""


def _flag_set(ev):
    try:
        return bool(ev.is_set())
    except Exception:
        return False


def register_job(db, user_id, label, msg=None):
    """Register current task as a job. Returns job dict."""
    job_id = _uuid.uuid4().hex[:12]
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    try:
        loop = asyncio.get_running_loop()
        cancel_event = asyncio.Event()
    except RuntimeError:
        loop = None
        cancel_event = None
    job = {"id": job_id, "user_id": int(user_id), "label": str(label or "job")[:80],
           "task": task, "loop": loop, "procs": [], "files": [],
           "cancel": cancel_event, "msg": msg, "started": _time.time()}
    ACTIVE[job_id] = job
    try:
        db.hset(_job_key(user_id), job_id, _json.dumps(
            {"label": job["label"], "started": int(job["started"])}))
    except Exception:
        pass
    return job


def unregister_job(db, user_id, job_id):
    ACTIVE.pop(job_id, None)
    try:
        db.hdel(_job_key(user_id), job_id)
    except Exception:
        pass


def sweep_finished(db):
    """Drop finished tasks from memory + Redis (hourly safety net). Returns count."""
    dropped = 0
    for jid, job in list(ACTIVE.items()):
        try:
            task = job.get("task")
            if task is not None and task.done():
                ACTIVE.pop(jid, None)
                try:
                    db.hdel(_job_key(job.get("user_id", 0)), jid)
                except Exception:
                    pass
                dropped += 1
        except Exception:
            pass
    return dropped


def list_jobs(db, user_id):
    """Live jobs for a user: memory first, Redis as fallback listing."""
    live = [j for j in ACTIVE.values() if j.get("user_id") == int(user_id)]
    if live:
        return [{"id": j["id"], "label": j.get("label", "job"),
                 "started": j.get("started", 0)} for j in live]
    try:
        raw = db.hgetall(_job_key(user_id)) or {}
    except Exception:
        return []
    out = []
    for jid, payload in raw.items():
        try:
            info = _json.loads(payload)
        except Exception:
            info = {}
        out.append({"id": jid, "label": info.get("label", "job"),
                    "started": info.get("started", 0), "stale": True})
    return out


def request_cancel(db, user_id, job_id=None, cancel_all=False):
    """Cancel one/all jobs. Returns list of (job_id, label, status).

    status: cancelled | already-gone | no-such-job
    """
    jobs = [j for j in ACTIVE.values() if j.get("user_id") == int(user_id)]
    if job_id and not cancel_all:
        jobs = [j for j in jobs if j["id"] == job_id]
        if not jobs:
            return [(job_id, "", "no-such-job")]
    results = []
    for job in jobs:
        jid = job["id"]
        label = job.get("label", "job")
        try:
            ev = job.get("cancel")
            if ev is not None:
                try:
                    if ev.loop is not None and ev.loop.is_closed():
                        pass
                    else:
                        ev.set()
                except Exception:
                    try:
                        ev.set()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            task = job.get("task")
            if task is not None and not task.done():
                try:
                    task.cancel()
                except Exception:
                    pass
        except Exception:
            pass
        for proc in list(job.get("procs") or []):
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        for path in list(job.get("files") or []):
            try:
                if path and _os.path.isfile(path):
                    _os.unlink(path)
            except Exception:
                pass
        try:
            release_inflight(db, job.get("shorturl"))
        except Exception:
            pass
        try:
            if job.get("shorturl"):
                db.delete(f"dl:wait:{job.get('shorturl')}")
        except Exception:
            pass
        ACTIVE.pop(jid, None)
        try:
            db.hdel(_job_key(user_id), jid)
        except Exception:
            pass
        try:
            msg = job.get("msg")
            if msg is not None:
                coro = msg.edit("❌ Download cancelled successfully.")
                try:
                    loop = job.get("loop")
                    if loop is not None and loop.is_running():
                        asyncio.run_coroutine_threadsafe(coro, loop)
                except Exception:
                    pass
        except Exception:
            pass
        results.append((jid, label, "cancelled"))
    return results


@contextlib.asynccontextmanager
async def job_scope(db, user_id, label, msg=None):
    """Async CM: register on enter, unregister on exit (any reason)."""
    job = register_job(db, user_id, label, msg=msg)
    try:
        yield job
    finally:
        unregister_job(db, user_id, job["id"])


# ---- in-flight dedup (same file requested twice at once) ----

def claim_inflight(db, shorturl, ttl=600):
    """True if WE won the download right; False if someone else holds it."""
    if not shorturl:
        return True
    try:
        return bool(db.set(f"dl:inflight:{shorturl}", "1", nx=True, ex=int(ttl)))
    except Exception:
        return True


def release_inflight(db, shorturl):
    if not shorturl:
        return
    try:
        db.delete(f"dl:inflight:{shorturl}")
    except Exception:
        pass


def add_waiter(db, shorturl, chat_id, ttl=900):
    if not shorturl:
        return
    try:
        db.rpush(f"dl:wait:{shorturl}", int(chat_id))
        db.expire(f"dl:wait:{shorturl}", int(ttl))
    except Exception:
        pass


def pop_waiters(db, shorturl):
    if not shorturl:
        return []
    try:
        ids = db.lrange(f"dl:wait:{shorturl}", 0, -1) or []
    except Exception:
        return []
    try:
        db.delete(f"dl:wait:{shorturl}")
    except Exception:
        pass
    out = []
    for i in ids:
        try:
            out.append(int(i))
        except Exception:
            pass
    return out


# ---- Download Queue System (v2 — rewritten from scratch) ----
#
# Model:
# - Per-user Redis LIST  q:items:{uid}  — compact JSON items in FIFO order
# - Redis SET            q:users       — user_ids that have queued items (stats)
# - Redis STRING         queue:paused:{uid} — pause flag (same key as legacy)
# - Backwards compatible: legacy items under queue:user:{uid} are migrated
#   to the new key on first touch; old item shape (user_id/job_id/status)
#   is parsed tolerantly everywhere.

QUEUE_MAX_PER_USER = 100
QUEUE_MAX_RETRIES = 3
QUEUE_USERS_KEY = "q:users"  # set of user_ids with queued items (stats)


class QueueHold(Exception):
    """Raised to stop queue draining (rate limit hit / maintenance). Item stays queued."""


def _user_queue_key(user_id):
    return f"q:items:{int(user_id)}"


_LEGACY_QUEUE_KEY = "queue:user:{uid}"
_PAUSE_KEY = "queue:paused:"


def _migrate_legacy(db, user_id):
    """Move old queue:user:{uid} items into q:items:{uid}. Best effort."""
    try:
        legacy_key = _LEGACY_QUEUE_KEY.format(uid=int(user_id))
        legacy = db.lrange(legacy_key, 0, -1) or []
        if legacy:
            key = _user_queue_key(user_id)
            new_items = db.lrange(key, 0, -1) or []
            if not new_items:
                for raw in legacy:
                    db.rpush(key, raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
                db.sadd(QUEUE_USERS_KEY, str(int(user_id)))
            db.delete(legacy_key)
    except Exception:
        pass


def _make_queue_item(url, label, retries):
    try:
        return _json.dumps(
            {
                "id": _uuid.uuid4().hex[:10],
                "url": str(url),
                "label": str(label or "Download")[:100],
                "retries": int(retries or 0),
                "added": round(_time.time(), 2),
            },
            ensure_ascii=False,
        )
    except Exception:
        return None


def _parse_queue_item(raw):
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "ignore")
        item = _json.loads(raw)
        if not isinstance(item, dict) or not item.get("url"):
            return None
        item.setdefault("retries", item.get("retry_count", 0) or 0)
        item.setdefault("label", "Download")
        item.setdefault("id", _uuid.uuid4().hex[:10])
        return item
    except Exception:
        return None


def enqueue_download(db, user_id, url, label="Download", retries=0, retry_count=None,
                     front=False, dedupe=True):
    """Queue a download for a user. Returns (ok, position).

    - dedupe: skip if the same URL is already pending for this user
    - front: push to the head of the queue (used for requeued failures)
    """
    try:
        user_id = int(user_id)
        if retry_count is not None:
            retries = int(retry_count)
        _migrate_legacy(db, user_id)
        key = _user_queue_key(user_id)
        items = db.lrange(key, 0, -1) or []
        if len(items) >= QUEUE_MAX_PER_USER:
            return False, 0
        if dedupe:
            import tools as _tools
            url_norm = str(url).split("?")[0]
            try:
                url_code = _tools.extract_code_from_url(url) or None
            except Exception:
                url_code = None
            for raw in items:
                it = _parse_queue_item(raw)
                if not it:
                    continue
                if str(it.get("url", "")).split("?")[0] == url_norm:
                    return False, 0
                if url_code:
                    try:
                        if url_code == (_tools.extract_code_from_url(it.get("url", "")) or None):
                            return False, 0
                    except Exception:
                        pass
        item = _make_queue_item(url, label, retries)
        if not item:
            return False, 0
        if front:
            db.lpush(key, item)
        else:
            db.rpush(key, item)
        db.sadd(QUEUE_USERS_KEY, str(int(user_id)))
        position = len(db.lrange(key, 0, -1) or [])
        return True, position
    except Exception:
        return False, 0


def dequeue_download(db, user_id):
    """Pop the oldest pending download for a user. Returns item dict or None."""
    try:
        user_id = int(user_id)
        _migrate_legacy(db, user_id)
        key = _user_queue_key(user_id)
        raw = db.lpop(key)
        if raw is None:
            try:
                # queue drained: drop user from stats set
                if not (db.lrange(key, 0, -1) or []):
                    db.srem(QUEUE_USERS_KEY, str(int(user_id)))
            except Exception:
                pass
            return None
        item = _parse_queue_item(raw)
        if item is None:
            raw2 = db.lpop(key)
            item = _parse_queue_item(raw2) if raw2 is not None else None
            if item is None:
                return None
        return item
    except Exception:
        return None


def queue_size(db, user_id):
    """Number of pending items for a user."""
    try:
        _migrate_legacy(db, user_id)
        return len(db.lrange(_user_queue_key(user_id), 0, -1) or []) or 0
    except Exception:
        return 0


def get_queue(db, user_id):
    """All pending items for a user, each with a 1-based position."""
    try:
        user_id = int(user_id)
        _migrate_legacy(db, user_id)
        items = db.lrange(_user_queue_key(user_id), 0, -1) or []
        out = []
        for i, raw in enumerate(items):
            it = _parse_queue_item(raw)
            if it:
                it["position"] = i + 1
                out.append(it)
        return out
    except Exception:
        return []


def pause_queue(db, user_id):
    try:
        db.set(f"{_PAUSE_KEY}{int(user_id)}", "1", ex=86400)
        return True
    except Exception:
        return False


def resume_queue(db, user_id):
    try:
        db.delete(f"{_PAUSE_KEY}{int(user_id)}")
        return True
    except Exception:
        return False


def is_queue_paused(db, user_id):
    try:
        flag = db.get(f"{_PAUSE_KEY}{int(user_id)}")
        if isinstance(flag, (bytes, bytearray)):
            flag = flag.decode()
        return bool(flag)
    except Exception:
        return False


def remove_from_queue(db, user_id, ident):
    """Remove a specific job by item id OR 1-based position number."""
    try:
        user_id = int(user_id)
        key = _user_queue_key(user_id)
        items = db.lrange(key, 0, -1) or []
        parsed = [(i, raw, _parse_queue_item(raw)) for i, raw in enumerate(items)]
        target_idx = None
        ident_s = str(ident).strip()
        if ident_s.isdigit():
            pos = int(ident_s)
            if 1 <= pos <= len(parsed):
                target_idx = pos - 1
        else:
            for i, _raw, it in parsed:
                if it and str(it.get("id")) == ident_s:
                    target_idx = i
                    break
        if target_idx is None:
            return False
        _, raw, _it = parsed[target_idx]
        db.lrem(key, 1, raw)
        return True
    except Exception:
        return False


def clear_queue(db, user_id):
    try:
        db.delete(_user_queue_key(user_id))
        db.delete(f"{_PAUSE_KEY}{int(user_id)}")
        try:
            db.srem(QUEUE_USERS_KEY, str(int(user_id)))
        except Exception:
            pass
        return True
    except Exception:
        return False


def get_global_queue_stats(db):
    """Global queue statistics for the admin dashboard."""
    try:
        users = db.smembers(QUEUE_USERS_KEY) or []
        total = 0
        waiters = 0
        for u in users:
            try:
                uid = u.decode() if isinstance(u, (bytes, bytearray)) else u
                n = len(db.lrange(_user_queue_key(uid), 0, -1) or [])
                if n > 0:
                    total += n
                    waiters += 1
                else:
                    db.srem(QUEUE_USERS_KEY, uid)
            except Exception:
                pass
        return {"total_queued": total, "users_waiting": waiters}
    except Exception:
        return {"total_queued": 0, "users_waiting": 0}
