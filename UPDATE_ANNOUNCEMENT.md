# 🚀 TeraBox Downloader Bot — v3.8 Update

## ✨ New Features

### ⚙️ **Configurable Download Limits**
Now fully customizable by the owner — no code changes needed.

| Setting | Default | Command |
|---------|---------|---------|
| Free user limit | 10/hour | `/setlimit free <n>` |
| Premium user limit | Unlimited | `/setlimit premium <n>` |
| Max files per link (free) | 10 | `/maxfiles <n>` |
| Download cooldown | 10s | `/setcooldown <seconds>` |
| **Custom user limit** | — | `/userlimit <user_id> <n>` |

### 👑 **Owner = No Limits**
Owner bypasses **all** limits — rate limits, file limits, cooldowns.

### 🔗 **Multi-Link Support**
Send multiple TeraBox links in **one message** — bot downloads each sequentially.

```
https://terabox.com/s/abc123
https://terabox.com/s/xyz789
https://1024tera.com/s/def456
```
→ Bot processes all 3 automatically.

### 👤 **New User Tap-to-Contact**
Admin notification now includes clickable user name:
```
👤 New user started bot
Name: [John](tg://user?id=123456789)
Username: @johndoe (or "No username")
ID: `123456789`
```
Tap the name → opens private chat instantly, even if user has no username.

---

## 📋 Owner Commands

```
/setlimit free 20          # Free users: 20 downloads/hour
/setlimit premium 0        # Premium: unlimited (0 = no limit)
/maxfiles 5                # Max 5 files per link for free users
/setcooldown 5             # 5 second cooldown between downloads
/userlimit 803003146 50    # Custom limit for specific user
/userlimit 803003146 0     # Unlimited for specific user
```

---

## 🛠 Technical Improvements
- Dynamic welcome text shows current free limit
- Rate limit errors use translation system (`{limit}` placeholder)
- Nepali & Hindi translations updated
- Upload timeout fixes (v3.7): 5 min max instead of 30-60 min

---

## 📥 Get the Bot
[🤖 Try Bot](https://t.me/tera_NTM_bot) · [💬 Support](https://t.me/ntmchat) · [📢 Channel](https://t.me/ntmpro) · [⭐ GitHub](https://github.com/abdul97233/TeraBox-Downloader-Bot)

---

**Update on VPS:** Run `/update` → bot restarts automatically.