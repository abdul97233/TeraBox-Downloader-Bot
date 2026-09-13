# Changelog

All notable changes to the TeraBox Downloader Bot.

---

## v3.0 — Modular Rewrite (2026-09-12)

### Architecture
- **Modular file structure** — split 4600-line `main.py` into `commands/`, `utils/`, `handlers/` directories
- **16 command modules** — admin, analytics, backup, cancel, config editor, library, maintenance, media, mystats, redeem, referral, status, UX
- **6 utility modules** — errors, flood protection, jobs, log redaction, premium, tags
- **Error isolation** — per-file download failures no longer crash entire handler
- **Boot notification** — pro card with build ID, boot number, packs count, storage ID, maintenance status

### Download System
- **HTTP 500 retries** — 3 attempts per file with progressive delay
- **Fallback API retry** — primary fails → fallback automatically
- **Strict file completion verify** — `!=` instead of `<` for file size check
- **Upload 2-retry loop** — retry on upload failure
- **mp4-only watermark** — non-mp4 files skip watermark instead of failing
- **In-flight dedup** — prevents duplicate downloads for same link (`dl:inflight:{code}`)
- **Cache system** — auto-send cached files, stale entry purge
- **Searchable library** — auto-index uploads, `/search`, `/reindex`

### Progress & UI
- **Fixed stuck progress bars** — watermark/compress/videoinfo timeouts resolved
- **Upload bars labeled "Uploading"** — distinguishes from download progress
- **Flood-aware edit backoff** — 2s throttle per edit, account-wide backoff on FloodWait
- **`/cancel` with job registry** — FFmpeg kill-on-cancel, file cleanup, waiter notification on failure
- **Cancel button removal** — buttons clear on all terminal states (success, failure, cancel confirmation)
- **Media tool menus** — `/mp3` bitrate selector (128/192/256/320), `/compress` resolution selector (480/720/1080, no upscaling)

### Premium System
- **Tag format fix** — `(OWNER)` parentheses, auto-remove when premium expires
- **Premium expiry reminders** — hourly sweep, 3d/1d/expired notifications
- **`/addpremium` `/delpremium` `/renew`** — full premium lifecycle
- **`/masstag` `/untag`** — bulk tag management
- **Member-since tracking** — `member_since:{uid}` Redis key

### Admin Tools
- **`/finduser`** — lookup any user's status/premium/tag
- **`/ban` `/unban`** — ban/unban users
- **`/addpremium` `/delpremium` `/renew`** — manage premium
- **`/masstag` `/untag`** — bulk tag/untag users
- **`/gcheck`** — validate gift cards
- **`/apihealth`** — check API response times
- **`/errors`** — recent error log entries
- **`/configview` `/configset` `/configreset`** — runtime config editor
- **`/setapi` `/reloadconfig`** — rotate API templates live
- **`/reindex`** — rebuild file library index
- **`/refstats`** — referral statistics
- **Audit log** — tracks all admin actions

### Referral System (v2)
- **New link format** — `ref_NTM-{tg_id}` (simple, readable, uses Telegram ID)
- **Count on join** — referral credited immediately when someone joins via link (not on first download)
- **Modern UI** — progress bars, tier visualization, share/claim/stats buttons
- **Self-redeem** — "Claim Reward" button to manually claim tier rewards
- **Cumulative tiers** — 5→1d, 10→3d, 25→7d (one-time at each threshold)
- **Self-ref protection** — cannot refer yourself, each user attributed once

### Safety & Reliability
- **FloodWait protection** — global edit backoff, patient_forward, patient_reply, patient_send
- **API log redaction** — URLs/tokens stripped from logs (`utils/logx.py`)
- **Centralized error messages** — `utils/errors.py` for consistent user-facing text
- **FFmpeg kill-on-cancel** — stops running video processing when user cancels
- **File cleanup on cancel** — partial downloads removed
- **Boot-clear stale claims** — `dl:inflight:*` and `dl:wait:*` cleared on startup
- **Restart flood-safe** — `/restart` and `/force` use patient_reply

### Broadcast & UX
- **Reply-to-forward** — broadcast preserves format, buttons, media
- **FloodWait resume** — broadcast pauses and continues after cooldown
- **Self-skip** — broadcast skips sending to the bot itself
- **Redeem confirmations** — show full name, username, user ID for both typed and button paths
- **Gift card auto-redeem** — button in channel posts auto-redeems on click

### Bug Fixes
- **Legacy Markdown escaping** — stray backslashes in captions fixed
- **Watermark timeouts** — `veryfast` preset + 300s timeout, was 900s+
- **Progress bar stuck at 90-100%** — videoinfo/watermark timeouts resolved
- **Font.ttf removed from git** — auto-downloads from GitHub on first watermark
- **CRLF line endings** — consistent across all files

---

## v2.x — Original Monolith

- Single `main.py` with all handlers
- Basic TeraBox download
- Premium system with gift cards
- Admin panel
- Media tools (mp3, compress)
- Button-based UI
- 3 languages (English, Nepali, Hindi)

---

## v1.0 — Initial Release

- Basic TeraBox link download
- Telegram bot interface
- Redis storage
