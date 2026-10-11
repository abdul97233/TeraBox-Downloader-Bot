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


# ---- Download Queue System ----

QUEUE_KEY = "download_queue"
QUEUE_POSITION_KEY = "queue:position"  # user_id -> position

def enqueue_download(db, user_id, url, label="Download"):
    """Add a download to the user's queue. Returns queue position (1-based)."""
    try:
        user_id = int(user_id)
        job_id = _uuid.uuid4().hex[:12]
        queue_item = _json.dumps({
            "job_id": job_id,
            "user_id": user_id,
            "url": url,
            "label": label,
            "status": "pending",
            "added": _time.time(),
        })
        # Add to user's queue (list)
        pos = db.rpush(f"queue:user:{user_id}", queue_item)
        # Also add to global queue for admin view
        db.zadd(QUEUE_KEY, {queue_item: _time.time()})
        return pos
    except Exception:
        return 0

def dequeue_download(db, user_id):
    """Remove and return the next pending download for user."""
    try:
        item = db.lpop(f"queue:user:{user_id}")
        if item:
            # Remove from global queue
            db.zrem(QUEUE_KEY, item)
            return _json.loads(item)
        return None
    except Exception:
        return None

def get_queue(db, user_id):
    """Get all items in user's queue."""
    try:
        items = db.lrange(f"queue:user:{user_id}", 0, -1) or []
        queue = []
        for i, item in enumerate(items):
            try:
                q = _json.loads(item)
                q["position"] = i + 1
                queue.append(q)
            except Exception:
                pass
        return queue
    except Exception:
        return []

def get_queue_position(db, user_id):
    """Get current position of user's active download (0 if none)."""
    try:
        queue = get_queue(db, user_id)
        return len(queue)
    except Exception:
        return 0

def pause_queue(db, user_id):
    """Pause queue by setting a flag."""
    try:
        db.set(f"queue:paused:{user_id}", "1", ex=86400)
        return True
    except Exception:
        return False

def resume_queue(db, user_id):
    """Resume queue by removing pause flag."""
    try:
        db.delete(f"queue:paused:{user_id}")
        return True
    except Exception:
        return False

def is_queue_paused(db, user_id):
    """Check if queue is paused."""
    try:
        return bool(db.get(f"queue:paused:{user_id}"))
    except Exception:
        return False

def remove_from_queue(db, user_id, job_id):
    """Remove a specific job from queue by job_id."""
    try:
        items = db.lrange(f"queue:user:{user_id}", 0, -1) or []
        for item in items:
            try:
                q = _json.loads(item)
                if q.get("job_id") == job_id:
                    db.lrem(f"queue:user:{user_id}", 1, item)
                    db.zrem(QUEUE_KEY, item)
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False

def clear_queue(db, user_id):
    """Clear all items from user's queue."""
    try:
        items = db.lrange(f"queue:user:{user_id}", 0, -1) or []
        for item in items:
            db.zrem(QUEUE_KEY, item)
        db.delete(f"queue:user:{user_id}")
        return True
    except Exception:
        return False

def get_global_queue_stats(db):
    """Get global queue statistics for admin dashboard."""
    try:
        total = db.zcard(QUEUE_KEY)
        # Get unique users in queue
        users = set()
        items = db.zrange(QUEUE_KEY, 0, -1) or []
        for item in items:
            try:
                q = _json.loads(item)
                users.add(q.get("user_id"))
            except Exception:
                pass
        return {"total_queued": total, "users_waiting": len(users)}
    except Exception:
        return {"total_queued": 0, "users_waiting": 0}
