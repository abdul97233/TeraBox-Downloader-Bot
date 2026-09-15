<div align="center">

<img src="https://socialify.git.ci/abdul97233/TeraBox-Downloader-Bot/image?description=1&descriptionEditable=Download%20TeraBox%20videos%20and%20photos%20instantly%20via%20Telegram%20Bot&font=Bitter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Overlapping%20Hexagons&pulls=1&stargazers=1&theme=Dark" alt="TeraBox Downloader Bot" width="640" />

# TeraBox Downloader Bot

**Download TeraBox videos and photos instantly through Telegram — fast, free, and feature-packed.**

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=flat-square&logo=telegram&logoColor=white)](https://t.me/tera_NTM_bot)
[![License](https://img.shields.io/badge/License-AGPL%20v3-blue?style=flat-square)](LICENSE)
[![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)

<br>

[🤖 Try Bot](https://t.me/tera_NTM_bot) · [💬 Support Group](https://t.me/ntmchat) · [📢 Channel](https://t.me/ntmpro) · [⭐ GitHub](https://github.com/abdul97233/TeraBox-Downloader-Bot)

</div>

---

## How It Works

```
You send a TeraBox link
        ↓
Bot fetches file info (with fallback API)
        ↓
Downloads + adds watermark (videos only)
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
- **67 video extensions** supported (mp4, mkv, webm, mov, avi, flv, wmv, m4v, 3gp, ts, ogg, mxf, yuv, etc.)
- **45 photo extensions** supported (jpg, png, gif, webp, heic, raw, psd, exr, jxl, tga, pcx, etc.)
- **47 supported domains** (terabox.com, 1024terabox.com, dubox, mirrobox, teraboxapp.com, etc.)
- Quality selector — `/dl 720p <link>` or `/dl 1080p <link>`
- Folder download — `/folder <link>` (premium)
- Batch multi-file download
- Fallback API — if primary fails, auto-tries secondary
- Cache system — instantly re-sends previously downloaded files
- Searchable library — `/search <query>` to find past downloads

### Premium System
- Time-based expiry (1d, 2d, 3d, 7d, 1w, 1m, unlimited)
- Gift card system with duration and auto-redeem buttons
- 1 GC per user per premium cycle
- Unlimited downloads, no size limit, multi-file
- Custom thumbnail for premium users
- `(OWNER)` tag — auto-applied/removed with premium status
- Expiry reminders — 3-day, 1-day, and expired notifications

### Media Tools
- `/mp3` — Extract audio with bitrate selector (128/192/256/320 kbps)
- `/compress` — Compress video with resolution selector (480p/720p/1080p, no upscaling)
- Video watermark — `@TERA_NTM_BOT` on every video (mp4 only, veryfast preset)
- Photos sent as native Telegram images (no watermark, no compression)

### User Experience
- **Modern button-based UI** — no need to memorize commands
- **3 languages** — English, Nepali, Hindi
- Download history — `/history`
- My Stats — `/mystats` (personal download stats)
- My Status — `/mystatus` (premium, tag, member-since, download counts)
- Referral system — `/ref` (link: `ref_NTM-{tg_id}`, tiered rewards: 5 → 1d, 10 → 3d, 25 → 7d)
- Quick download — `/quick <link>` (skip folder detection)
- Preview — `/preview <link>` (peek first 3 files in a folder)
- Cancel — `/cancel` with tap-to-cancel buttons on progress messages

### Admin Panel
- Dynamic admin system — add/remove admins from bot
- `/finduser` — lookup any user's status/premium/tag
- `/ban` `/unban` — ban/unban users
- `/addpremium` `/delpremium` `/renew` — manage premium
- `/masstag` `/untag` — bulk tag/untag users
- `/gen 7d 5` — generate 5 gift cards for 7 days
- `/gclist` — paginated gift card list with usage tracking
- `/stats` — bot statistics with top users/links
- `/userstats` — per-user download stats
- `/apihealth` — check API response times
- `/errors` — recent error log entries
- `/broadcast` — send message to all users (reply-to-forward preserves format)
- `/announce 30 <msg>` — scheduled broadcast
- `/cleandownloads` — clean downloads folder
- `/maintenance` — toggle maintenance mode
- `/logrotate` — rotate bot.log
- `/configview` `/configset` `/configreset` — runtime config editor

### Safety & Reliability
- `/panic` — emergency stop all services
- `/resume` — bring bot back online
- `/backup` `/restore` — full Redis snapshot and merge restore
- `/setapi` `/reloadconfig` — rotate API templates live
- Parallel downloads — 5 concurrent, 10 total backpressure
- FloodWait protection — global edit backoff, patient forwarding/replies
- In-flight dedup — prevents duplicate downloads for same link
- Cancel with FFmpeg kill — stops running video processing
- Audit log — tracks all admin actions
- Force channel/group join
- Anti-spam cooldown (configurable)
- Max files per request limit
- API log redaction — URLs/tokens stripped from logs

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
| Referral rewards | ❌ | ✅ |
| MP3/Compress | ✅ | ✅ |
| Watermark | ✅ | ✅ |

---

## Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Open main menu with button UI |
| `/help` | Show commands |
| `/info` | Your profile & plan |
| `/id` | Your user ID |
| `/plan` | View premium plans |
| `/mystatus` | Your premium/tag/stats |
| `/mystats` | Personal download statistics |
| `/history` | Your download history |
| `/dl <link>` | Download original quality |
| `/dl 720p <link>` | Download in quality |
| `/quick <link>` | Fast single-file download |
| `/folder <link>` | Download entire folder (premium) |
| `/preview <link>` | Preview first 3 files in folder |
| `/cancel` | Cancel active downloads |
| `/mp3` | Reply to video → extract audio |
| `/compress` | Reply to video → compress |
| `/setthumb` | Set custom thumbnail (reply to image) |
| `/removethumb` | Remove custom thumbnail |
| `/lang ne` | Set language (en/ne/hi) |
| `/ref` `/refer` `/referral` | Get your referral link + stats |
| `/search <query>` | Search file library |
| `/redeem <code>` | Redeem a gift card |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/finduser <id>` | Lookup user status/premium/tag |
| `/ban <id>` | Ban a user |
| `/unban <id>` | Unban a user |
| `/addpremium <id> <days>` | Grant premium |
| `/delpremium <id>` | Revoke premium |
| `/renew <id> <days>` | Extend premium |
| `/masstag <id1,id2,...> <tag>` | Tag multiple users |
| `/untag <id1,id2,...>` | Remove tags |
| `/gcheck <code>` | Validate a gift card |
| `/gen <dur> [n]` | Generate gift cards |
| `/gclist` | List gift cards (paginated) |
| `/gcdel <code>` | Delete a gift card |
| `/gctrack` | Track gift card usage |
| `/stats` | Bot statistics |
| `/userstats [id>` | Per-user stats |
| `/apihealth` | API health check |
| `/errors [n]` | Recent errors |
| `/broadcast <msg>` | Broadcast to all users |
| `/cleandownloads` | Clean downloads folder |

### Owner Only Commands

| Command | Description |
|---------|-------------|
| `/addadmin <id>` | Add admin |
| `/removeadmin <id>` | Remove admin |
| `/adminlist` | List all admins |
| `/panic` | Emergency stop |
| `/resume` | Bring bot online |
| `/maintenance` | Toggle maintenance mode |
| `/update` | Pull & restart |
| `/restart` | Normal restart |
| `/force` | Force restart |
| `/setstorage <id>` | Set storage chat ID |
| `/getstorage` | Show storage IDs |
| `/setforce <type> <@chat>` | Add force channel/group |
| `/removeforce <type> <@chat>` | Remove force channel/group |
| `/maxfiles <n>` | Set file limit |
| `/setcooldown <s>` | Set cooldown |
| `/setplan <text>` | Update plan text |
| `/announce <min> <msg>` | Scheduled broadcast |
| `/setapi` | Rotate API template |
| `/reloadconfig` | Reload API templates |
| `/logrotate` | Rotate bot.log |
| `/configview` | View runtime config |
| `/configset` | Edit runtime config |
| `/configreset` | Reset config key |
| `/backup` | Export Redis data |
| `/restore` | Restore from backup |
| `/auditlog` | View admin action log |
| `/allowredeem <id>` | Reset GC redemption |
| `/settag <id> <tag>` | Set custom tag |
| `/tag` | View your custom tag |
| `/reindex` | Rebuild file library index |
| `/refstats` | Referral statistics |

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

Use the built-in `/update` command — it stashes `config.py`, pulls latest code, and restarts automatically:

```
/update
```

Or manually:

```bash
git pull origin main
pkill -f "python main.py"
nohup python main.py > bot.log 2>&1 &
disown
```

---

## Configuration

Copy `config.example.py` to `config.py` and fill in your credentials:

```python
# Telegram API — get from https://my.telegram.org/apps
API_ID = 12345678
API_HASH = "your_api_hash"

# Bot token from @BotFather
BOT_TOKEN = "your_bot_token"

# Redis
HOST = "localhost"
PORT = 6379
PASSWORD = None

# Storage chat (files are uploaded here, then forwarded)
PRIVATE_CHAT_ID = -1001234567890

# Download folder on VPS
DOWNLOAD_DIR = "downloads"

# Admins (owner is automatic)
OWNER_ID = 123456789
ADMINS = [123456789]

# Force join (users must join before using bot)
FORCE_CHANNELS = ["@your_channel"]
FORCE_GROUPS = ["@your_group"]

# TeraBox API
TERABOX_API_BASE = "https://your-terabox-api.com/"
TERABOX_API_TOKEN = "your_token"
TERABOX_API_TEMPLATE = f"{TERABOX_API_BASE}?authkey={TERABOX_API_TOKEN}&url={{url}}"

# Fallback API
TERABOX_FALLBACK_API_BASE = "https://your-fallback-api.com/"
TERABOX_FALLBACK_API_TEMPLATE = f"{TERABOX_FALLBACK_API_BASE}?authkey={TERABOX_API_TOKEN}&url={{url}}"

# Self-hosted Bot API (2GB uploads)
TG_API_BASE = "https://your-bot-api-server.com"

# GitHub (for /update)
GITHUB_REPO = "https://github.com/your-username/your-repo"
```

**Never commit `config.py` to GitHub.** It is protected by `.gitignore`.

---

## Project Structure

```
TeraBox-Downloader-Bot/
├── main.py              # Bot entry point, handlers, button menus, download flows
├── terabox.py           # TeraBox API integration (primary + fallback)
├── tools.py             # Download, upload, watermark, video info, utilities
├── cansend.py           # Rate throttle for progress bar edits
├── FastTelethon.py      # Fast upload/download helper
├── config.py            # Your credentials (NOT pushed)
├── config.example.py    # Template for config.py
├── requirements.txt     # Python dependencies
├── setup.sh             # VPS setup script
│
├── commands/            # Modular command handlers
│   ├── admin_users.py   # /finduser, /ban, /unban, /addpremium, /masstag
│   ├── analytics.py     # /stats, /userstats, /apihealth, /errors
│   ├── backup.py        # /backup, /restore
│   ├── cacheux.py       # Cache prompt (auto-send + Download Again)
│   ├── cancel.py        # /cancel with tap-to-cancel buttons
│   ├── config_editor.py # /configview, /configset, /configreset
│   ├── library.py       # /search, /reindex (searchable library)
│   ├── maintenance.py   # /maintenance, /logrotate, /setapi, /reloadconfig
│   ├── media.py         # /mp3, /compress (bitrate/resolution menus)
│   ├── mystats.py       # /mystats
│   ├── redeem_core.py   # Shared gift card redeem logic
│   ├── referral.py      # /referral, /refstats, expiry reminders
│   ├── user_status.py   # /mystatus text builder
│   └── ux.py            # /broadcast, /quick, /preview, gift card buttons
│
├── utils/               # Shared utilities
│   ├── errors.py        # Centralized user-facing error messages
│   ├── flood.py         # FloodWait protection (edit backoff, patient helpers)
│   ├── jobs.py          # Job registry, FFmpeg kill-on-cancel, inflight dedup
│   ├── logx.py          # API log redaction (URLs/tokens stripped)
│   ├── premium.py       # Premium grant/revoke/check + tag cleanup
│   └── tags.py          # Tag resolve/set/clear with premium expiry
│
├── handlers/            # Specialized handlers
│   └── folder_handler.py # Folder download orchestration
│
├── models/              # Data models (reserved)
├── downloads/           # Temporary download storage
├── bot.log              # Runtime log (not pushed)
└── .gitignore           # Protects secrets and temp files
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.9+ |
| Bot Framework | Telethon 1.42 (MTProto) |
| Bot API Upload | aiohttp + self-hosted Bot API (2GB) |
| Download | aiohttp (async, 3 retries) |
| Photo Support | sendPhoto (native Telegram images) |
| Database | Redis (cloud) |
| Video Processing | ffmpeg (watermark, compress, extract) |
| Watermark | ffmpeg drawtext (veryfast preset) |
| Parallel | asyncio (5 concurrent, 10 backpressure) |
| Flood Protection | Custom backoff (patient_edit, patient_forward) |
| Cancellation | FFmpeg kill + job registry |

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
| FloodWait errors | Normal during heavy use — auto-recovers in seconds |
| "Server busy" | Max concurrent downloads reached — wait for current ones to finish |
| Stray backslashes | Legacy Markdown escaping — already fixed (v2) |

---

## Security

- Never commit `config.py` to GitHub
- `.gitignore` protects: `config.py`, `*.session`, `font.ttf`, `thumb.jpg`, `*.wm.mp4`, `downloads/`, `bot.log`
- API logs are redacted — URLs and tokens are stripped
- Credential leaks: rotate immediately via BotFather + Redis CLI

---

## Contributing

1. Fork the repo
2. Create branch: `git checkout -b feature/my-feature`
3. Commit: `git commit -m "Add: my feature"`
4. Push: `git push origin feature/my-feature`
5. Open a Pull Request

---

## License

[AGPL-3.0](LICENSE) — Free to use, modify, and distribute. Network use counts as distribution.

---

<div align="center">

**Made with ❤️ by [Abdul](https://t.me/abdul97233)**

⭐ Star this repo if you found it useful!

</div>
