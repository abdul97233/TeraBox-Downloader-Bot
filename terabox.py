import re
from urllib.parse import parse_qs, urlparse

import requests

from tools import get_formatted_size


# ---------------- URL VALIDATION ---------------- #

def check_url_patterns(url):
    patterns = [
        r"ww\.mirrobox\.com",
        r"www\.nephobox\.com",
        r"freeterabox\.com",
        r"www\.freeterabox\.com",
        r"1024tera\.com",
        r"4funbox\.co",
        r"www\.4funbox\.com",
        r"mirrobox\.com",
        r"nephobox\.com",
        r"terabox\.app",
        r"terabox\.com",
        r"www\.terabox\.ap",
        r"www\.terabox\.com",
        r"www\.1024tera\.co",
        r"www\.momerybox\.com",
        r"teraboxapp\.com",
        r"momerybox\.com",
        r"tibibox\.com",
        r"www\.tibibox\.com",
        r"www\.teraboxapp\.com",
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


# ---------------- AURIXS API DOWNLOADER ---------------- #

AURIXS_API_TEMPLATE = (
    "https://api.ntm.com/api/terabox?key=NMTPASS&url={url}"
)


def get_data(url: str):
    """
    Fetch download metadata using Aurixs Terabox API.
    """

    api_url = AURIXS_API_TEMPLATE.format(url=url)

    print("\nREQUESTING API:", api_url)

    try:
        res = requests.get(api_url, timeout=25)
    except Exception as e:
        print("API request failed:", e)
        return False

    print("API STATUS:", res.status_code)

    if res.status_code != 200:
        return False

    try:
        data = res.json()
    except Exception as e:
        print("JSON parse error:", e)
        return False

    print("API RAW RESPONSE:", data)

    # Ensure required fields exist
    if not data.get("directlink"):
        print("Missing direct link in API response")
        return False

    size_bytes = int(data.get("sizebytes", 0))

    fast_link = data.get("directlink")
    print("FAST LINK:", fast_link)

    # --- Resolve redirect to final CDN URL (required for Telegram) --- #
    try:
        head = requests.head(fast_link, allow_redirects=True, timeout=25)
        real_direct_url = head.url
    except Exception as e:
        print("Redirect resolve failed:", e)
        real_direct_url = fast_link

    print("FINAL CDN URL:", real_direct_url)

    # --- Return structure expected by main.py --- #
    return {
        "file_name": data.get("file_name"),
        "size": data.get("size") or get_formatted_size(size_bytes),
        "sizebytes": size_bytes,
        "thumb": data.get("thumb"),

        # resolved direct file url
        "direct_link": real_direct_url,

        # extra fields (safe to keep)
        "link": fast_link,
    }
