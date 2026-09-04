import asyncio
import os
import re
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import aiohttp
import cv2
import requests
from telethon import TelegramClient


VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".3gp", ".ts", ".vob", ".ogv", ".mts", ".m2ts", ".divx", ".asf", ".rm", ".rmvb")


def get_video_info(file_path: str) -> dict:
    """Extract duration, width, height and thumbnail from a video file using OpenCV."""
    info = {"duration": 0, "width": 0, "height": 0, "thumbnail": None}
    try:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return info
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = int(frames / fps) if fps > 0 else 0
        # Generate thumbnail at 10% of video
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frames * 0.1))
        ret, frame = cap.read()
        thumb_path = None
        if ret:
            thumb_path = os.path.join(os.path.dirname(file_path), "thumb.jpg")
            cv2.imwrite(thumb_path, frame)
        cap.release()
        info = {"duration": duration, "width": w, "height": h, "thumbnail": thumb_path}
    except Exception as e:
        print(f"get_video_info error: {e}")
    return info


def escape_markdown(text: str) -> str:
    """Escape Telegram legacy Markdown special characters (V1)."""
    if text is None:
        return ""
    return re.sub(r"([_*\[\]()~`>#+\-=|{}\\])", r"\\\1", str(text))


class _ProgressFileWrapper:
    """Wraps a file object so requests calls `callback(read_bytes, total)`
    as data is read during an upload."""

    def __init__(self, fileobj, callback, total, loop):
        self._f = fileobj
        self._cb = callback
        self._total = total
        self._loop = loop
        self._read = 0

    def __len__(self):
        return self._total

    def read(self, size=-1):
        data = self._f.read(size)
        if data:
            self._read += len(data)
            if self._cb:
                try:
                    asyncio.run_coroutine_threadsafe(
                        self._cb(self._read, self._total), self._loop
                    )
                except Exception:
                    pass
        return data


def _bot_api_send(base_url, token, chat_id, file_path, caption, filename, progress_callback=None, loop=None,
                   duration=0, width=0, height=0, thumb=None):
    """Upload a local file to a chat via the Telegram Bot HTTP API.

    Video files are sent with sendVideo so Telegram renders them as
    playable media (with streaming) instead of a generic document/file.
    """
    ext = os.path.splitext(filename)[1].lower()
    is_video = ext in VIDEO_EXTENSIONS

    if is_video:
        endpoint = "sendVideo"
        file_field = "video"
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown",
            "supports_streaming": "true",
            "spoiler": "true",
        }
        if duration:
            data["duration"] = str(duration)
        if width:
            data["width"] = str(width)
        if height:
            data["height"] = str(height)
    else:
        endpoint = "sendDocument"
        file_field = "document"
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown",
        }

    url = f"{base_url.rstrip('/')}/bot{token}/{endpoint}"
    total = os.path.getsize(file_path)

    files_dict = {}
    with open(file_path, "rb") as raw:
        wrapped = _ProgressFileWrapper(raw, progress_callback, total, loop)
        files_dict[file_field] = (filename, wrapped)
        if thumb and is_video and os.path.isfile(thumb):
            files_dict["thumb"] = ("thumb.jpg", open(thumb, "rb"), "image/jpeg")
        try:
            resp = requests.post(url, files=files_dict, data=data, timeout=1800)
        except Exception as e:
            return {"ok": False, "description": str(e)}
        finally:
            if "thumb" in files_dict:
                files_dict["thumb"][1].close()

    try:
        return resp.json()
    except Exception:
        return {"ok": False, "description": resp.text[:500]}


async def send_document_via_api(base_url, token, chat_id, file_path, caption, filename, progress_callback=None,
                                 duration=0, width=0, height=0, thumb=None):
    """Async wrapper around the Bot API upload (runs in a thread)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _bot_api_send, base_url, token, chat_id, file_path, caption, filename, progress_callback, loop,
        duration, width, height, thumb
    )


def check_url_patterns(url: str) -> bool:
    """
    Check if the given URL matches any of the known URL patterns for code hosting services.

    Parameters:
    url (str): The URL to be checked.

    Returns:
    bool: True if the URL matches a known pattern, False otherwise.
    """
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


def extract_code_from_url(url: str) -> str | None:
    """
    Extracts the code from a URL.

    Parameters:
        url (str): The URL to extract the code from.

    Returns:
        str: The extracted code, or None if the URL does not contain a code.
    """
    pattern1 = r"/s/(\w+)"
    pattern2 = r"surl=(\w+)"

    match = re.search(pattern1, url)
    if match:
        return match.group(1)

    match = re.search(pattern2, url)
    if match:
        return match.group(1)

    return None


def get_urls_from_string(string: str) -> str | None:
    """
    Extracts all URLs from a given string.

    Parameters:
        string (str): The input string.

    Returns:
        str: The first URL found in the input string, or None if no URLs were found.
    """
    pattern = r"(https?://\S+)"
    urls = re.findall(pattern, string)
    urls = [url for url in urls if check_url_patterns(url)]
    if not urls:
        return
    return urls[0]


def extract_surl_from_url(url: str) -> str:
    """
    Extracts the surl from a URL.

    Parameters:
        url (str): The URL to extract the surl from.

    Returns:
        str: The extracted surl, or None if the URL does not contain a surl.
    """
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    surl = query_params.get("surl", [])

    if surl:
        return surl[0]
    else:
        return False


def get_formatted_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        size = size_bytes / (1024 * 1024 * 1024)
        unit = "GB"
    elif size_bytes >= 1024 * 1024:
        size = size_bytes / (1024 * 1024)
        unit = "MB"
    elif size_bytes >= 1024:
        size = size_bytes / 1024
        unit = "KB"
    else:
        size = size_bytes
        unit = "b"
    return f"{size:.2f} {unit}"


def convert_seconds(seconds: int) -> str:
    """
    Convert seconds into a human-readable format.

    Parameters:
        seconds (int): The number of seconds to convert.

    Returns:
        str: The seconds converted to a human-readable format.
    """
    seconds = int(seconds)
    hours = seconds // 3600
    remaining_seconds = seconds % 3600
    minutes = remaining_seconds // 60
    remaining_seconds_final = remaining_seconds % 60

    if hours > 0:
        return f"{hours}h:{minutes}m:{remaining_seconds_final}s"
    elif minutes > 0:
        return f"{minutes}m:{remaining_seconds_final}s"
    else:
        return f"{remaining_seconds_final}s"


async def is_user_on_chat(bot: TelegramClient, chat_id: int, user_id: int) -> bool:
    """
    Check if a user is present in a specific chat.

    Parameters:
        bot (TelegramClient): The Telegram client instance.
        chat_id (int): The ID of the chat.
        user_id (int): The ID of the user.

    Returns:
        bool: True if the user is present in the chat, False otherwise.
    """
    try:
        check = await bot.get_permissions(chat_id, user_id)
        return check
    except:
        return False


async def download_file(
    url: str,
    filename: str,
    callback=None,
) -> str | bool:
    try:
        timeout = aiohttp.ClientTimeout(total=600, connect=15, sock_read=60)
        connector = aiohttp.TCPConnector(
            limit=10, force_close=False,
            ttl_dns_cache=300, keepalive_timeout=60,
            enable_cleanup_closed=True,
        )
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://terabox.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": '"Chromium";v="125", "Google Chrome";v="125"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
        async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
            async with session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                if total > 0:
                    with open(filename, "wb") as f:
                        f.truncate(total)
                with open(filename, "r+b" if total > 0 else "wb") as file:
                    async for chunk in response.content.iter_chunked(2097152):
                        file.write(chunk)
                        downloaded += len(chunk)
                        if callback:
                            await callback(downloaded, total, "Downloading")
        return filename

    except asyncio.TimeoutError:
        print(f"Download timeout for {url}")
        return False
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False


def download_image_to_bytesio(url: str, filename: str) -> BytesIO | None:
    """
    Downloads an image from a URL and returns it as a BytesIO object.

    Args:
        url (str): The URL of the image to download.
        filename (str): The filename to save the image as.

    Returns:
        BytesIO: The image data as a BytesIO object, or None if the download failed.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            image_bytes = BytesIO(response.content)
            image_bytes.name = filename
            return image_bytes
        else:
            return None
    except:
        return None
