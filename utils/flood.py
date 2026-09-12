"""FloodWait-aware helpers. No third-party imports (detect by class name)."""

import asyncio as _asyncio
import time as _time

from telethon.tl.functions.messages import ForwardMessagesRequest

_flood_until = 0.0


def edits_blocked():
    try:
        return _time.time() < _flood_until
    except Exception:
        return False


def note_flood(seconds, cap=300):
    """Back off ALL progress edits account-wide for a while."""
    global _flood_until
    try:
        secs = int(seconds or 0)
    except Exception:
        secs = 0
    if secs <= 0:
        return
    try:
        _flood_until = max(_flood_until, _time.time() + min(secs, int(cap)))
    except Exception:
        pass


def _is_flood(e):
    return type(e).__name__ == "FloodWaitError"


def _secs(e, default=30):
    try:
        return max(int(getattr(e, "seconds", default) or default), 1)
    except Exception:
        return default


async def safe_edit(msg, text, **kw):
    """Best-effort edit. Returns True/False, never raises."""
    if edits_blocked():
        return False
    try:
        await msg.edit(text, **kw)
        return True
    except Exception as e:
        if _is_flood(e):
            note_flood(_secs(e))
        return False


async def patient_edit(msg, text, max_wait=60, **kw):
    """Edit with one bounded retry. Returns True/False, never raises."""
    try:
        await msg.edit(text, **kw)
        return True
    except Exception as e:
        if not _is_flood(e):
            return False
        note_flood(_secs(e))
        try:
            await _asyncio.sleep(min(_secs(e), int(max_wait)))
        except Exception:
            return False
        try:
            await msg.edit(text, **kw)
            return True
        except Exception as e2:
            if _is_flood(e2):
                note_flood(_secs(e2))
            return False


async def patient_forward(bot, max_wait=120, **kw):
    """Forward with one bounded retry. Returns True/False, never raises
    (CancelledError still propagates so /cancel keeps working)."""
    try:
        await bot(ForwardMessagesRequest(**kw))
        return True
    except Exception as e:
        if not _is_flood(e):
            return False
        try:
            await _asyncio.sleep(min(_secs(e), int(max_wait)))
        except Exception:
            return False
        try:
            await bot(ForwardMessagesRequest(**kw))
            return True
        except Exception:
            return False
