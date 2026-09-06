<div align="center">

<img src="https://socialify.git.ci/abdul97233/TeraBox-Downloader-Bot/image?description=1&descriptionEditable=Download%20TeraBox%20videos%20instantly%20via%20Telegram%20Bot&font=Bitter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Overlapping%20Hexagons&pulls=1&stargazers=1&theme=Dark" alt="TeraBox Downloader Bot" width="640" />

# TeraBox Downloader Bot

**Download TeraBox videos instantly through Telegram — fast, free, and feature-packed.**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/tera_NTM_bot)
[![License](https://img.shields.io/badge/License-GPL%20v3-green?style=flat-square)](LICENSE)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)

<br>

[🤖 Try Bot](https://t.me/tera_NTM_bot) • [💬 Support Group](https://t.me/ntmchat) • [📢 Channel](https://t.me/ntmpro) • [⭐ GitHub](https://github.com/abdul97233/TeraBox-Downloader-Bot)

</div>

---

## How It Works

```
You send a TeraBox link
        ↓
Bot fetches file info (with fallback API)
        ↓
Downloads + adds watermark
        ↓
Uploads to Telegram (2GB fast upload)
        ↓
Forwards to you instantly
```

**That's it. No ads, no waiting, no nonsense.**

---

## Features

### Download
- Send any TeraBox link → instant download
- **39+ supported domains** (terabox.com, 1024terabox.com, dubox, mirrobox, etc.)
- **20+ video formats** (mp4, mkv, webm, mov, avi, flv, wmv, etc.)
- Quality selector — `/dl 720p <link>` or `/dl 1080p <link>`
- Folder download — `/folder <link>` (premium)
- Batch multi-file download
- Fallback API — if primary fails, auto-tries secondary

### Premium System
- Time-based expiry (1d, 2d, 3d, 7d, 1w, 1m, unlimited)
- Gift card system with duration
- 1 GC per user per premium cycle
- Unlimited downloads, no size limit, multi-file
- Custom thumbnail for premium users

### Media Tools
- `/mp3` — Extract audio from any video
- `/compress` — Compress video (low/mid quality)
- Video watermark — `@TERA_NTM_BOT` on every video
- Video metadata — duration, resolution, thumbnail

### User Experience
- **Modern button-based UI** — no need to memorize commands
- **3 languages** — English, Nepali, Hindi
- Download history — `/history`
- Auto-expired premium
- Instant cached forwarding

### Admin Panel
- Dynamic admin system — add/remove admins from bot
- `/ban` `/unban` — ban users
- `/broadcast` — send message to all users
- `/announce 30 <msg>` — scheduled broadcast
- `/gen 7d 5` — generate 5 gift cards for 7 days
- `/gclist` — list all gift cards
- `/stats` — bot statistics
- `/usage` — disk, RAM, CPU usage
- `/logs` — recent error logs
- `/backup` — export Redis data

### Safety
- `/panic` — emergency stop all services
- `/resume` — bring bot back online
- `/maintenance` — toggle maintenance mode
- Anti-spam cooldown (configurable)
- Max files per request limit
- Audit log — tracks all admin actions
- Force channel/group join

---

## Free vs Premium

| Feature | Free | Premium |
|---------|:----:|:-------:|
| Downloads | 10/hour | Unlimited |
| Files per link | 1 | All |
| File size limit | 500MB | Unlimited |
| Multi-file | ❌ | ✅ |
| Folder download | ❌ | ✅ |
| Custom thumbnail | ❌ | ✅ |
| Priority speed | ❌ | ✅ |
| Watermark | ✅ | ✅ |

---

## Commands

### User
| Command | Description |
|---------|-------------|
| `/start` | Open main menu |
| `/help` | Show commands |
| `/info` | Your profile & plan |
| `/plan` | View plans |
| `/redeem <code>` | Redeem gift card |
| `/history` | Your download history |
| `/dl 720p <link>` | Download in quality |
| `/folder <link>` | Download folder (⭐) |
| `/mp3` | Reply to video → audio |
| `/compress` | Reply to video → compress |
| `/setthumb` | Set thumbnail (⭐) |
| `/lang ne` | Set language |

### Admin
| Command | Description |
|---------|-------------|
| `/pre <id> <dur>` | Promote to premium |
| `/de <id>` | Demote from premium |
| `/premium_users` | List premium users |
| `/gen <dur> [n]` | Generate gift cards |
| `/gclist` | List all gift cards |
| `/ban <id>` | Ban user |
| `/unban <id>` | Unban user |
| `/broadcast <msg>` | Broadcast to all |
| `/announce <min> <msg>` | Scheduled broadcast |
| `/stats` | Bot statistics |
| `/usage` | Resource usage |
| `/logs` | Error logs |

### Owner Only
| Command | Description |
|---------|-------------|
| `/panic` | 🚨 Emergency stop |
| `/resume` | Bring bot online |
| `/maintenance` | Toggle maintenance |
| `/addadmin <id>` | Add admin |
| `/removeadmin <id>` | Remove admin |
| `/adminlist` | List all admins |
| `/auditlog` | View admin action log |
| `/backup` | Export Redis data |
| `/update` | Pull & restart |
| `/maxfiles <n>` | Set file limit |
| `/setcooldown <s>` | Set cooldown |
| `/setstorage <id>` | Update storage chat |
| `/allowredeem <id>` | Reset GC redemption |

---

## Installation

### Quick Start (Ubuntu VPS)

```bash
# Install dependencies
sudo apt update && sudo apt install python3 python3-pip python3-venv redis-server git ffmpeg -y

# Clone
git clone https://github.com/abdul97233/TeraBox-Downloader-Bot.git
cd TeraBox-Downloader-Bot

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt
pip install opencv-python-headless

# Configure
cp config.example.py config.py
nano config.py  # Add your credentials

# Run
python main.py
```

### Run in Background

```bash
nohup python main.py > bot.log 2>&1 &
disown
```

### Update

```bash
git pull origin main
pkill -f "python main.py"
nohup python main.py > bot.log 2>&1 &
disown
```

---

## Configuration

Create `config.py`:

```python
# Telegram
API_ID = 123456
API_HASH = "your_api_hash"
BOT_TOKEN = "your_bot_token"

# Redis
HOST = "localhost"
PORT = 6379
PASSWORD = ""

# Bot
PRIVATE_CHAT_ID = -1001234567890
DOWNLOAD_DIR = "downloads"

# Admin
OWNER_ID = 123456789
ADMINS = [123456789]

# Force Join
FORCE_CHANNELS = ["@your_channel"]
FORCE_GROUPS = ["@your_group"]

# TeraBox API
TERABOX_API_BASE = "https://saiyanteraboxapi.saiyanprojects.com/"
TERABOX_API_TOKEN = "your_token"
TERABOX_API_TEMPLATE = f"{TERABOX_API_BASE}?authkey={TERABOX_API_TOKEN}&url={{url}}"

# Fallback API
TERABOX_FALLBACK_API_BASE = "https://saiyanteraboxapi2.saiyanprojects.com/"
TERABOX_FALLBACK_API_TEMPLATE = f"{TERABOX_FALLBACK_API_BASE}?authkey={TERABOX_API_TOKEN}&url={{url}}"

# Self-hosted Bot API (2GB uploads)
TG_API_BASE = "https://your-bot-api-server.com"

# GitHub (for /update)
GITHUB_REPO = "https://github.com/abdul97233/TeraBox-Downloader-Bot"
```

---

## Project Structure

```
TeraBox-Downloader-Bot/
├── main.py          # Bot entry point, handlers, UI
├── terabox.py       # TeraBox API integration (async)
├── tools.py         # Download, upload, watermark, utils
├── config.py        # Your credentials (not pushed)
├── cansend.py       # Rate limiter for progress bars
├── requirements.txt # Python dependencies
└── README.md        # This file
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| Bot Framework | Telethon (MTProto) |
| Bot API Upload | aiohttp + self-hosted Bot API |
| Download | aiohttp (async, 2MB chunks) |
| Database | Redis |
| Video Processing | ffmpeg + OpenCV |
| Watermark | ffmpeg drawtext |
| Parallel | asyncio (non-blocking) |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot not starting | Check `python --version`, reinstall deps |
| Redis error | `sudo systemctl restart redis` |
| Slow download | VPS location matters — use nearby server |
| ffmpeg not found | `sudo apt install ffmpeg` |
| Upload fails | Check `TG_API_BASE` server status |
| Memory full | Run `/cleandownloads` or `/usage` |

---

## Security

- Never commit `config.py` to GitHub
- Use `.gitignore`:
  ```
  config.py
  *.session
  *.session-journal
  __pycache__/
  venv/
  bot.log
  downloads/
  ```
- If credentials leak: rotate immediately

---

## Contributing

1. Fork the repo
2. Create branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "Add: my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

[GPL-3.0](LICENSE) — Free to use, modify, and distribute.

---

<div align="center">

**Made with ❤️ by [Abdul](https://t.me/abdul97233)**

⭐ Star this repo if you found it useful!

</div>
