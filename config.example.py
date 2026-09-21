# ================== TELEGRAM API CONFIG ==================
# Get these from https://my.telegram.org/apps
API_ID = 12345678
API_HASH = "YOUR_API_HASH_HERE"

# Bot token from @BotFather
BOT_TOKEN = "1234567890:ABCdefGhIjKlMnOpQrStUvWxYz"


# ================== REDIS DATABASE CONFIG ==================

# Redis Host / Port / Password
HOST = "localhost"
PORT = 6379
PASSWORD = None   # Set to None if Redis has no password


# ================== BOT SETTINGS ==================

# Private storage chat where files are uploaded
# Use your private channel / chat ID (must be integer)
PRIVATE_CHAT_ID = -1001234567890

# Folder where downloaded videos are stored on the VPS
DOWNLOAD_DIR = "downloads"


# ================== ADMIN & OWNER ==================

# Owner — only this user can run /update, /setstorage, /panic, /addadmin
OWNER_ID = 123456789

# Admin user IDs (MUST be integers)
# Owner is automatically admin
ADMINS = [
    123456789,
]


# ================== FORCE JOIN CHANNELS & GROUPS ==================

# Users must join these before using the bot
# Use username (e.g. "@your_channel") or chat ID (e.g. -1001234567890)
FORCE_CHANNELS = [
    "@your_channel",
]

FORCE_GROUPS = [
    "@your_group",
]


# ================== TERA BOX API ==================

# API Endpoints — load-balanced across all entries
# Add more endpoints here. No code changes needed.
# Health-aware round-robin with circuit breaker distributes load automatically.
API_ENDPOINTS = [
    {
        "name": "api-1",          # Friendly name for logs /apihealth
        "url": "https://your-primary-api.com/",
        "token": "your_api_token",
    },
    {
        "name": "api-2",
        "url": "https://your-secondary-api.com/",
        "token": "your_api_token",
    },
    # Add more as needed:
    # {"name": "api-3", "url": "https://...", "token": "..."},
]

# Self-hosted Telegram Bot API server (replaces https://api.telegram.org)
# Enables high-speed uploads up to 2GB via the Bot HTTP API.
TG_API_BASE = "https://your-bot-api-server.com"


# ================== UPDATE SETTINGS ==================

GITHUB_REPO = "https://github.com/your-username/your-repo"
