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
    """Async retry wrapper for GET requests."""
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=15)
    for i in range(1, attempts + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, **kwargs) as resp:
                    if resp.status in (200, 302):
                        resp._text = await resp.text()
                        resp._json = None
                        return resp
                    log.info(f"[Retry {i}] HTTP {resp.status}")
        except Exception as e:
            log.info(f"[Retry {i}] Error:", e)
        await asyncio.sleep(delay)
    return None


# ---------------- MAIN API HANDLER ---------------- #

async def _fetch_files_from_api(api_template: str, url: str):
    """Helper: fetch files from a single API template."""
    api_url = api_template.format(url=url)
    log.info(f"\nREQUESTING API: {api_url}")

    res = await retry_request("GET", api_url, attempts=2, delay=2)
    if not res:
        log.info("API failed after retries")
        return False

    log.info(f"API STATUS: {res.status}")

    try:
        data = await res.json()
    except Exception as e:
        log.info(f"JSON parse error: {e}")
        return False

    log.info(f"API RAW RESPONSE: {data}")

    if not data.get("ok"):
        log.info("API returned ok=false")
        return False

    files = data.get("files")
    if not files:
        log.info("No files in API response")
        return False

    result = []
    for f in files:
        fast_link = f.get("download_url")
        if not fast_link:
            continue
        size_bytes = int(f.get("size", 0))
        result.append({
            "file_name": f.get("filename"),
            "size": f.get("size_readable") or get_formatted_size(size_bytes),
            "sizebytes": size_bytes,
            "thumb": None,
            "direct_link": fast_link,
            "link": fast_link,
        })

    if not result:
        log.info("No valid download urls in API response")
        return False

    return result


async def get_files(url: str):
    """Async: Fetch files via primary API, fallback to secondary if it fails."""
    # Try primary API first
    result = await _fetch_files_from_api(TERABOX_API_TEMPLATE, url)
    if result:
        return result

    # Fallback to secondary API
    log.info("\nPrimary API failed, trying fallback API...")
    result = await _fetch_files_from_api(TERABOX_FALLBACK_API_TEMPLATE, url)
    if result:
        return result

    return False


async def get_data(url: str):
    """Async: Fetch the FIRST Terabox file only."""
    files = await get_files(url)
    if not files:
        return False
    return files[0]
