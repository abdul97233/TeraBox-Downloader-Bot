import logging
log = logging.getLogger(__name__)
import asyncio
import re
from urllib.parse import parse_qs, urlparse

import aiohttp

from config import TERABOX_API_TEMPLATE, TERABOX_FALLBACK_API_TEMPLATE
from tools import get_formatted_size


# ---------------- URL VALIDATION ---------------- #

def check_url_patterns(url):
    patterns = [
        r"terabox\.com",
        r"terabox\.app",
        r"terabox\.fun",
        r"terabox\.best",
        r"terabox\.ap",
        r"terabox\.club",
        r"terabox\.click",
        r"teraboxapp\.com",
        r"teraboxlink\.com",
        r"teraboxlinke\.com",
        r"teraboxshare\.com",
        r"teraboxsharefile\.com",
        r"teraboxurl\.com",
        r"teraboxfree\.com",
        r"terasharelink\.com",
        r"terasharefile\.com",
        r"terashareus\.com",
        r"terafileshare\.com",
        r"tera1024box\.com",
        r"1024tera\.com",
        r"1024tera\.co",
        r"1024terabox\.com",
        r"1024-terabox\.com",
        r"4funbox\.com",
        r"4funbox\.co",
        r"4funbox\.in",
        r"mirrobox\.com",
        r"nephobox\.com",
        r"freeterabox\.com",
        r"momerybox\.com",
        r"tibibox\.com",
        r"gibibox\.com",
        r"pebibox\.com",
        r"fancybox\.in",
        r"bestclouddrive\.com",
        r"dubox\.com",
        r"playduo\.link",
        r"theteraboxmod\.app",
    ]

    for pattern in patterns:
        if re.search(pattern, url):
            return True

    return False


def get_urls_from_string(string: str) -> list[str]:
    pattern = r"(https?://\S+)"
    urls = re.findall(pattern, string)
    urls = [url.rstrip(").,;:!?") for url in urls]
    urls = [url for url in urls if check_url_patterns(url)]
    if not urls:
        return []
    return urls[0]


def extract_surl_from_url(url: str) -> str | None:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    surl = query_params.get("surl", [])
    return surl[0] if surl else False


# ---------------- API SETTINGS ---------------- #

# API endpoint template is imported from config (TERABOX_API_TEMPLATE)


# ---------------- RETRY WRAPPER ---------------- #

async def retry_request(method, url, attempts=3, delay=2, **kwargs):
    """Async retry wrapper for GET requests.

    4xx (except 429) fail fast — retrying a dead link is pointless.
    Backoff grows per attempt to avoid hammering a struggling API.
    URLs are never logged (may carry authkey); only status codes.
    """
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15)
    for i in range(1, attempts + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **kwargs) as resp:
                    if resp.status in (200, 302):
                        resp._text = await resp.text()
                        resp._json = None
                        return resp
                    if resp.status == 429:
                        log.info(f"[Retry {i}] HTTP 429 (rate limited)")
                    elif 400 <= resp.status < 500:
                        log.info(f"[Retry {i}] HTTP {resp.status} (fail fast, no retry)")
                        return None
                    else:
                        log.info(f"[Retry {i}] HTTP {resp.status}")
        except Exception as e:
            from utils.logx import safe_exc
            log.info(f"[Retry {i}] Error: {safe_exc(e)}")
        await asyncio.sleep(delay * i)
    return None


# ---------------- MAIN API HANDLER ---------------- #

async def _fetch_files_from_api(api_template: str, url: str, _api_name="api"):
    """Helper: fetch files from a single API template.

    Never logs URLs, tokens, or raw responses — only api name, status,
    latency and short error classes.
    """
    import time as _time
    from utils.logx import api_log_started, api_log_ok, api_log_failed, safe_exc
    api_url = api_template.format(url=url)
    api_log_started(log, _api_name)
    t0 = _time.monotonic()
    latency = lambda: int((_time.monotonic() - t0) * 1000)

    res = await retry_request("GET", api_url, attempts=2, delay=2)
    if not res:
        api_log_failed(log, _api_name, status=None, latency_ms=latency(), error="unreachable after retries")
        return False

    try:
        data = await res.json()
    except Exception as e:
        api_log_failed(log, _api_name, status=res.status, latency_ms=latency(), error=f"bad response: {safe_exc(e, 60)}")
        return False

    if not isinstance(data, dict) or not data.get("ok"):
        api_log_failed(log, _api_name, status=res.status, latency_ms=latency(), error="ok=false")
        return False

    files = data.get("files")
    if not files:
        api_log_failed(log, _api_name, status=res.status, latency_ms=latency(), error="empty file list")
        return False

    result = []
    for f in files:
        fast_link = f.get("download_url")
        if not fast_link:
            continue
        try:
            size_bytes = int(f.get("size", 0))
        except (TypeError, ValueError):
            size_bytes = 0
        result.append({
            "file_name": f.get("filename") or "file",
            "size": f.get("size_readable") or get_formatted_size(size_bytes),
            "sizebytes": size_bytes,
            "thumb": None,
            "direct_link": fast_link,
            "link": fast_link,
            "expires_in": f.get("expires_in", ""),
        })

    if not result:
        api_log_failed(log, _api_name, status=res.status, latency_ms=latency(), error="no usable links")
        return False

    api_log_ok(log, _api_name, status=res.status, latency_ms=latency())
    try:
        log.info(f"API files: count={len(result)}")
    except Exception:
        pass
    return result


async def get_files(url: str):
    """Async: Fetch files via primary API, fallback to secondary if it fails."""
    # Try primary API first
    result = await _fetch_files_from_api(TERABOX_API_TEMPLATE, url, _api_name="primary")
    if result:
        return result

    # Fallback to secondary API
    log.info("Primary API failed, trying fallback API...")
    result = await _fetch_files_from_api(TERABOX_FALLBACK_API_TEMPLATE, url, _api_name="fallback")
    if result:
        log.info("Primary failed, fallback ok")
        return result

    return False


async def get_data(url: str):
    """Async: Fetch the FIRST Terabox file only."""
    files = await get_files(url)
    if not files:
        return False
    return files[0]


async def get_fallback_files(url: str):
    """Async: Fetch files via fallback API ONLY (fresh alternate dl URLs).

    Used to retry a download whose primary direct_link 502s.
    """
    return await _fetch_files_from_api(TERABOX_FALLBACK_API_TEMPLATE, url, _api_name="fallback")
