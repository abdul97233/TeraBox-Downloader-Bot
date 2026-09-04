# ================== TELEGRAM API CONFIG ==================

# Get these from https://my.telegram.org/apps
API_ID = 1234567
API_HASH = "YOUR_API_HASH_HERE"

# Bot token from @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"


# ================== REDIS DATABASE CONFIG ==================

# Redis Host / Port / Password
HOST = "127.0.0.1"
PORT = 6379
PASSWORD = None   # Set to None if Redis has no password

# ================== BOT SETTINGS ==================

# Private storage chat where files are uploaded
# Use your private channel / chat ID (must be integer)
PRIVATE_CHAT_ID = -1001313190597

# Folder where downloaded videos are stored on the VPS
DOWNLOAD_DIR = "downloads"


# Admin user IDs (MUST be integers)
# Add multiple IDs inside list
ADMINS = [
    803003146,   # Example: Your Telegram ID
    # 123456789,
]


# ================== OPTIONAL FLAGS ==================

# If you still want to support single ADMIN broadcast logs etc.
# (Used in old redeem handler — safe to keep)
ADMIN_ID = 803003146

TERABOX_API_BASE = "https://api.ntm.com/api/terabox"
TERABOX_API_TOKEN = "NTMPASS"

TERABOX_API_TEMPLATE = (
    f"{TERABOX_API_BASE}?key={TERABOX_API_TOKEN}&url={{url}}"
)

# Self-hosted Telegram Bot API server (replaces https://api.telegram.org)
# Enables high-speed uploads up to 2GB via the Bot HTTP API.
TG_API_BASE = "https://saiyantg.saiyanprojects.com"
