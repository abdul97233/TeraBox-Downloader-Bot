"""Safe logging helpers — secrets NEVER reach bot.log.

Use redact_url() for any URL and the api_* helpers for API call logs.
"""

import re as _re

_SECRET_KEYS = ("authkey", "auth_key", "token", "apikey", "api_key",
                "key", "secret", "password", "passwd", "auth")


def redact_url(url):
    """Strip query params and credentials: keep scheme://host/path only."""
    try:
        s = str(url or "")
        if not s:
            return "-"
        s = _re.sub(r"^(\w+://[^/]+).*", r"\1/[REDACTED]", s)
        return s
    except Exception:
        return "[REDACTED]"


def safe_exc(e, limit=200):
    """Exception text with any embedded URLs redacted."""
    try:
        text = str(e or "error")
    except Exception:
        text = "error"
    try:
        text = _re.sub(r"https?://\S+", lambda m: redact_url(m.group(0)), text)
    except Exception:
        pass
    return text[:limit]


def api_log_started(log, api="primary"):
    log.info(f"API request started | api={api} | url=[REDACTED]")


def api_log_ok(log, api="primary", status=200, latency_ms=0):
    log.info(f"API request ok | api={api} | status={status} | latency={int(latency_ms)}ms")


def api_log_failed(log, api="primary", status=None, latency_ms=0, error=""):
    log.info(f"API request failed | api={api} | status={status} | "
             f"latency={int(latency_ms)}ms | error={safe_exc(error, 120)}")
