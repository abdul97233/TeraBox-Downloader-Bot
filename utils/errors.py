"""Centralized user-facing error messages.

Technical details stay in logs; users only see clean texts.
Usage: await send_user_error(m_or_event, "api_unavailable")
"""

ERRORS = {
    "invalid_link": "❌ Unable to process this link.\n\nPossible reasons:\n• Link expired\n• File unavailable\n• TeraBox service temporarily unavailable\n\nPlease try again later.",
    "unsupported_link": "❌ This link type is not supported.\nPlease send a valid TeraBox link.",
    "file_not_found": "❌ File not found.\nIt may have been deleted or the link expired.",
    "expired_link": "❌ This link has expired.\nPlease generate a fresh link and try again.",
    "api_unavailable": "❌ Unable to process this link.\n\nPossible reasons:\n• Link expired\n• File unavailable\n• TeraBox service temporarily unavailable\n\nPlease try again later.",
    "download_timeout": "❌ Download timed out.\nThe server took too long to respond. Please try again later.",
    "download_failed": "❌ Download failed.\nPlease try again in a moment.",
    "upload_failed": "❌ Upload to Telegram failed.\nPlease try again in a moment.",
    "file_too_large": "❌ File is too big.\nFree users can download up to 500MB per file.",
    "unsupported_file": "❌ This file type is not supported.",
    "media_failed": "❌ Media processing failed.\nThe file may be corrupted.",
    "no_audio": "❌ This file does not contain an audio track.",
    "cancelled": "❌ Download cancelled successfully.",
    "no_active_job": "ℹ️ You don't have any active downloads.",
    "server_error": "❌ Temporary server error.\nPlease try again in a moment.",
    "cache_unavailable": "❌ Cached copy is no longer available.\nDownloading a fresh copy instead.",
}


async def send_user_error(target, kind, via="reply", **kwargs):
    """Send a clean error message.

    via="reply" -> target.reply(text)  (for events / new messages)
    via="edit"  -> target.edit(text)   (for an existing status message)
    Falls back to the other method, then to answer(alert).
    """
    text = ERRORS.get(kind, ERRORS["server_error"])
    try:
        if kwargs:
            text = text.format(**kwargs)
    except Exception:
        pass
    methods = ("edit", "reply") if via == "edit" else ("reply", "edit")
    for name in methods:
        try:
            fn = getattr(target, name, None)
            if callable(fn):
                return await fn(text)
        except Exception:
            pass
    try:
        if hasattr(target, "answer"):
            await target.answer(text, alert=True)
    except Exception:
        pass
    return None
