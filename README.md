# 🚀 TeraBox Downloader Bot

<p align="center">
  <h1 align="center">TeraBox Downloader Bot</h1>
</p>

<p align="center">
  A powerful Telegram bot built with Python for downloading and processing files from TeraBox links directly through Telegram.
</p>

<p align="center">
  <img src="https://socialify.git.ci/abdul97233/TeraBox-Downloader-Bot/image?description=1&descriptionEditable=Telegram%20bot%20in%20Python%20enabling%20seamless%20file%20downloads%20from%20Terabox%20links.&font=Bitter&forks=1&issues=1&language=1&name=1&owner=1&pattern=Overlapping%20Hexagons&pulls=1&stargazers=1&theme=Dark" alt="TeraBox Downloader Bot" width="640" />
</p>

<p align="center">
  <a href="https://github.com/abdul97233/TeraBox-Downloader-Bot">
    <img src="https://img.shields.io/github/repo-size/abdul97233/TeraBox-Downloader-Bot?color=yellow" alt="Repository Size">
  </a>
  <a href="https://github.com/abdul97233/TeraBox-Downloader-Bot/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/abdul97233/TeraBox-Downloader-Bot" alt="License">
  </a>
  <img src="https://img.shields.io/github/commit-activity/m/abdul97233/TeraBox-Downloader-Bot" alt="Commit Activity">
</p>

<p align="center">
  <a href="https://t.me/tera_NTM_bot">🤖 Main Bot</a> •
  <a href="https://t.me/tera2_NTM_bot">🤖 Backup Bot</a> •
  <a href="https://t.me/ntmchat">💬 Support Group</a> •
  <a href="https://t.me/ntmpro">📢 Telegram Channel</a>
</p>

---

## 📖 About

**TeraBox Downloader Bot** is a Python-based Telegram bot designed to make downloading files from TeraBox simple and convenient.

Users can send supported TeraBox links to the bot, and the bot processes the link and provides the available file or download information directly through Telegram.

The project includes a **Free/Premium user system**, anti-spam protection, gift-card support, Redis-based data storage, administrator controls, broadcasting, and Telegram-based file storage.

---

## ✨ Features

### 📥 Download Features

* 🔗 Process TeraBox links directly through Telegram
* 🎬 Direct video support
* 🔗 Direct download links
* ⚡ Fast file processing and downloading
* 📦 Telegram-based file delivery
* ☁️ Private Telegram storage support
* 🔄 Easy to update and maintain

### 👤 User System

* 🆓 Free user support
* 💎 Premium user support
* ⏱️ Configurable anti-spam protection
* 🎁 Gift-card redemption
* 📊 User information
* ❤️ Bot health/ping command
* 📋 Plan information

### 🛡️ Protection & Management

* 🚫 Anti-spam system
* ⏳ User cooldown system
* 👑 Premium user management
* 🔐 Admin-only commands
* 📢 Broadcast system
* 📝 Logging support
* 🗄️ Redis database support

---

# 💎 Free vs Premium

| Feature              |  Free User | Premium User |
| -------------------- | ---------: | -----------: |
| TeraBox downloads    |          ✅ |            ✅ |
| Direct video         |          ✅ |            ✅ |
| Direct download link |          ✅ |            ✅ |
| Anti-spam cooldown   | 60 seconds |   30 seconds |
| Premium commands     |          ❌ |            ✅ |
| Gift-card redemption |          ❌ |            ✅ |
| Priority access      |          ❌ |            ✅ |

> **Note:** Premium limits and cooldowns can be customized according to your bot configuration.

---

# 🤖 Bot Commands

## 👤 User Commands

| Command          | Description                  |
| ---------------- | ---------------------------- |
| `/start`         | Start the bot                |
| `/help`          | Display help information     |
| `/cmds`          | Show available commands      |
| `/info`          | Display user information     |
| `/id`            | Display Telegram user ID     |
| `/ping`          | Check bot/server response    |
| `/plan`          | View available premium plans |
| `/redeem <code>` | Redeem a premium gift card   |

### Example

```text
/redeem ABCD-1234-EFGH
```

---

# 👑 Admin Commands

Admin commands are restricted to authorized administrators.

| Command                | Description                      |
| ---------------------- | -------------------------------- |
| `/gc`                  | Generate premium gift cards      |
| `/pre`                 | Promote a user to Premium        |
| `/de`                  | Demote a Premium user to Free    |
| `/broadcast`           | Broadcast a message to bot users |
| `/premium_users`       | View Premium users               |
| `/remove_premium_user` | Remove Premium status from users |

> ⚠️ Never share your administrator Telegram ID configuration or bot credentials publicly.

---

# 🎁 Premium Gift Cards

The bot includes a gift-card based Premium system.

The basic workflow is:

```text
Administrator
      │
      ▼
Generate Gift Card
      │
      ▼
Share Code With User
      │
      ▼
User Uses /redeem
      │
      ▼
Premium Activated
```

Example:

```text
/redeem YOUR-GIFT-CODE
```

Gift cards can be used to provide Premium access without manually changing a user's account.

---

# 🛡️ Anti-Spam System

The bot includes an anti-spam/cooldown system to prevent excessive requests.

### Free Users

Default cooldown:

```text
60 seconds
```

### Premium Users

Default cooldown:

```text
30 seconds
```

The cooldown values can be customized according to your deployment and requirements.

---

# 🗄️ Redis Database

Redis is used for persistent bot data and user-related information.

Depending on the configured version of the bot, Redis may be used for information such as:

* User data
* Premium users
* Gift cards
* Cooldown information
* Usage data
* Bot statistics
* Temporary/cache data

For production deployments, Redis should preferably run locally on the server or behind proper authentication/firewall rules.

---

# 🛠️ Requirements

Before installing the bot, make sure you have:

* Python 3.9+
* Telegram Bot Token
* Telegram API ID
* Telegram API Hash
* Redis
* A Telegram private storage chat/channel
* Required TeraBox configuration/API credentials
* Git *(recommended)*

---

# 📦 Installation

## 1. Clone the Repository

```bash
git clone https://github.com/abdul97233/TeraBox-Downloader-Bot.git
cd TeraBox-Downloader-Bot
```

Alternatively, download the repository as a ZIP file:

```text
https://github.com/abdul97233/TeraBox-Downloader-Bot/archive/refs/heads/main.zip
```

---

## 2. Create a Virtual Environment

Using a virtual environment is recommended.

### Linux / Ubuntu

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

---

## 3. Install Dependencies

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install the required packages:

```bash
pip install -r requirements.txt
```

---

# ⚙️ Configuration

The bot requires Telegram, Redis, storage, administrator, and TeraBox-related configuration.

> ⚠️ **Never commit real API keys, bot tokens, passwords, cookies, or other credentials to GitHub.**

Keep sensitive values outside the repository whenever possible.

---

## 🔑 Telegram Configuration

You need:

### API ID and API Hash

Create a Telegram application through Telegram's official developer platform and obtain:

```text
API_ID
API_HASH
```

### Bot Token

Create a bot using **@BotFather** and obtain:

```text
BOT_TOKEN
```

Example configuration:

```python
API_ID = 123456
API_HASH = "YOUR_API_HASH"

BOT_TOKEN = "YOUR_BOT_TOKEN"
```

Use your real credentials only in your local/server configuration.

---

# 🗄️ Redis Configuration

Example:

```python
HOST = "localhost"
PORT = 6379
PASSWORD = ""
```

For a local Redis installation:

```text
HOST = localhost
PORT = 6379
```

If your Redis server requires authentication:

```python
PASSWORD = "YOUR_REDIS_PASSWORD"
```

### Production Recommendation

Do not expose Redis directly to the public internet.

Prefer:

```text
Python Bot
    │
    ▼
127.0.0.1:6379
    │
    ▼
Redis
```

instead of exposing:

```text
0.0.0.0:6379
```

---

# 📁 Telegram Private Storage

The bot can use a private Telegram chat/channel for storing downloaded files.

Configure:

```python
PRIVATE_CHAT_ID = -1001234567890
```

Replace the example value with the ID of your private Telegram storage chat/channel.

Make sure the bot has the necessary permissions in the storage destination.

---

# 🔐 TeraBox Configuration

The TeraBox integration depends on the configuration used by the current version of the project.

If your version uses an API-based configuration, configure the corresponding TeraBox API endpoint and authentication token in your server configuration.

Example structure:

```python
TERABOX_API_BASE = "YOUR_TERABOX_API_ENDPOINT"
TERABOX_API_TOKEN = "YOUR_TERABOX_API_TOKEN"
```

If your deployment uses another authentication method, configure it according to the corresponding implementation in `config.py`.

> ⚠️ Do not publish TeraBox API tokens or authentication cookies in the repository.

---

# 👑 Administrator Configuration

Add authorized Telegram user IDs to the administrator configuration.

Example:

```python
ADMINS = [
    123456789,
]
```

You can obtain your Telegram user ID using the bot's `/id` command or another trusted Telegram ID utility.

Only trusted users should be added as administrators.

---

# ▶️ Running the Bot

After completing the configuration, start the bot with:

```bash
python main.py
```

On Linux systems:

```bash
python3 main.py
```

If everything is configured correctly, the bot should start and connect to Telegram and the configured services.

---

# 🖥️ Running on Ubuntu VPS

For production use, it is recommended to run the bot as a background service instead of keeping an SSH terminal open.

Basic setup:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv redis-server git -y
```

Clone the repository:

```bash
git clone https://github.com/abdul97233/TeraBox-Downloader-Bot.git
cd TeraBox-Downloader-Bot
```

Create the virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the bot and start it:

```bash
python3 main.py
```

For a permanent production deployment, use a process manager such as **systemd**, **Supervisor**, or **Docker**.

---

# 📂 Project Structure

```text
TeraBox-Downloader-Bot/
│
├── FastTelethon.py       # Telegram file transfer utilities
├── cansend.py            # Telegram sending/file handling utilities
├── config.py             # Application configuration
├── main.py               # Main bot entry point
├── terabox.py            # TeraBox processing functionality
├── tools.py              # Helper and utility functions
├── requirements.txt      # Python dependencies
├── README.md             # Project documentation
└── LICENSE               # Project license
```

---

# 🔄 How It Works

The general workflow is:

```text
                    ┌──────────────┐
                    │ Telegram     │
                    │ User         │
                    └──────┬───────┘
                           │
                           │ TeraBox URL
                           ▼
                    ┌──────────────┐
                    │ Telegram Bot │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ URL          │
                    │ Validation   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ TeraBox      │
                    │ Processing   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ File / URL   │
                    │ Processing   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Telegram     │
                    │ Storage      │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ User         │
                    └──────────────┘
```

Redis works alongside the bot for persistent user and Premium-related data.

---

# 🔒 Security Recommendations

Before deploying the bot publicly:

### Never commit secrets

Do not commit:

```text
BOT_TOKEN
API_HASH
REDIS_PASSWORD
TERABOX_API_TOKEN
TERABOX_COOKIE
SESSION FILES
.env
```

### Recommended `.gitignore`

```gitignore
.env
.env.*
venv/
.venv/
__pycache__/
*.pyc
*.session
*.session-journal
```

### If a secret is accidentally published

Immediately:

1. Revoke/rotate the exposed credential.
2. Replace it on the server.
3. Remove it from the repository.
4. Check Git history if the secret was committed previously.
5. Do not assume deleting the latest commit removes the secret from Git history.

---

# 🐛 Troubleshooting

## Bot does not start

Check:

```bash
python --version
```

and:

```bash
pip install -r requirements.txt
```

Then verify that your Telegram credentials are correct.

---

## Redis connection error

Check whether Redis is running:

```bash
sudo systemctl status redis
```

Start it if necessary:

```bash
sudo systemctl start redis
```

Test Redis:

```bash
redis-cli ping
```

Expected:

```text
PONG
```

---

## Bot does not respond

Check:

* Bot token
* Telegram API ID
* Telegram API Hash
* Internet connection
* Redis connection
* Python process
* Server logs

---

## TeraBox link fails

Check:

* Whether the URL is supported
* Whether the TeraBox service/API is available
* TeraBox API configuration
* Authentication configuration
* Network connectivity
* API response/logs

---

## Telegram upload fails

Check:

* Bot permissions
* Telegram limits
* Available disk space
* Network speed
* Private storage chat ID
* Telegram API errors

---

# 📊 Recommended Production Monitoring

For a production deployment, monitor:

```text
CPU usage
RAM usage
Disk usage
Network usage
Redis status
Bot status
Active downloads
Failed downloads
Total users
Premium users
Daily requests
API failures
Telegram errors
```

This makes it easier to detect problems before users report them.

---

# 🤝 Contributing

Contributions are welcome.

To contribute:

### 1. Fork the repository

```bash
git clone https://github.com/abdul97233/TeraBox-Downloader-Bot.git
```

### 2. Create a branch

```bash
git checkout -b feature/my-feature
```

### 3. Make your changes

Test your changes locally before submitting them.

### 4. Commit

```bash
git add .
git commit -m "Add: my feature"
```

### 5. Push

```bash
git push origin feature/my-feature
```

### 6. Open a Pull Request

Please provide a clear explanation of:

* What was changed
* Why it was changed
* How it was tested
* Any configuration changes required

---

# 📜 Disclaimer

This project is provided for **educational and personal use**.

Users are responsible for ensuring that their use of this software complies with:

* Applicable laws
* Telegram's terms and policies
* TeraBox's terms and policies
* Copyright and intellectual-property laws
* Any other applicable third-party terms

The project author and contributors are not responsible for misuse of the software, violations of third-party terms, copyright infringement, or any damages resulting from its use.

Use this project responsibly and only with content you are authorized to access or download.

---

# 📄 License

This project is licensed under the **GNU General Public License v3.0 (GPL-3.0)**.

See the [`LICENSE`](LICENSE) file for the complete license text.

---

# 🌐 Community & Support

<p align="center">

<a href="https://t.me/tera_NTM_bot">
  <img src="https://img.shields.io/badge/Main%20Bot-TeraBox%20Downloader-blue?style=for-the-badge&logo=telegram" alt="Main Bot">
</a>

<a href="https://t.me/tera2_NTM_bot">
  <img src="https://img.shields.io/badge/Backup%20Bot-TeraBox%20Downloader-blue?style=for-the-badge&logo=telegram" alt="Backup Bot">
</a>

<br><br>

<a href="https://t.me/ntmchat">
  <img src="https://img.shields.io/badge/Support%20Group-NTM%20Chat-blue?style=for-the-badge&logo=telegram" alt="Support Group">
</a>

<a href="https://t.me/ntmpro">
  <img src="https://img.shields.io/badge/Telegram-Channel-blue?style=for-the-badge&logo=telegram" alt="Telegram Channel">
</a>

</p>

---

<p align="center">
  ⭐ If this project helped you, consider giving the repository a star!
</p>

<p align="center">
  Made with ❤️ using Python and Telegram
</p>
