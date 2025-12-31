import re
import time
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


# ---------------- API SETTINGS ---------------- #

NTM_API_TEMPLATE = (
    "https://api.NTM.com/api/terabox?key=NTMPASS&url={url}"
)


# ---------------- RETRY WRAPPER ---------------- #

def retry_request(method, url, attempts=3, delay=2, **kwargs):
    """
    Generic retry wrapper for GET / HEAD requests
    """

    for i in range(1, attempts + 1):
        try:
            resp = requests.request(method, url, timeout=25, **kwargs)

            # Accept 200 and 302 for redirect cases
            if resp.status_code in (200, 302):
                return resp

            print(f"[Retry {i}] HTTP {resp.status_code}")

        except Exception as e:
            print(f"[Retry {i}] Error:", e)

        time.sleep(delay)

    return None


# ---------------- MAIN API HANDLER ---------------- #

def get_data(url: str):
    """
    Fetch Terabox file data via Aurixs API
    Includes retry for API + redirect resolution
    """

    api_url = AURIXS_API_TEMPLATE.format(url=url)

    print("\nREQUESTING API:", api_url)

    # -------- Retry API Call -------- #
    res = retry_request("GET", api_url, attempts=3, delay=2)

    if not res:
        print("API failed after retries")
        return False

    print("API STATUS:", res.status_code)

    # -------- Decode JSON -------- #
    try:
        data = res.json()
    except Exception as e:
        print("JSON parse error:", e)
        return False

    print("API RAW RESPONSE:", data)

    # -------- Validate Fields -------- #
    fast_link = data.get("directlink")
    if not fast_link:
        print("Missing direct link in API response")
        return False

    size_bytes = int(data.get("sizebytes", 0))

    print("FAST LINK:", fast_link)

    # -------- Resolve Redirect (Retry) -------- #
    head = retry_request(
        "HEAD",
        fast_link,
        attempts=3,
        delay=2,
        allow_redirects=True
    )

    if head:
        real_direct_url = head.url
    else:
        print("Redirect resolve failed — using fast link fallback")
        real_direct_url = fast_link

    print("FINAL CDN URL:", real_direct_url)

    # -------- Return structure expected by main.py -------- #
    return {
        "file_name": data.get("file_name"),
        "size": data.get("size") or get_formatted_size(size_bytes),
        "sizebytes": size_bytes,
        "thumb": data.get("thumb"),

        # final resolved downloadable url
        "direct_link": real_direct_url,

        # backup link
        "link": fast_link,
    }
