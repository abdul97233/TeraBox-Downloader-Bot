"""Modern broadcast system with media support, captions, stickers, and preview."""

import asyncio
import logging
import time

from telethon import Button, events

log = logging.getLogger(__name__)

BROADCAST_CHUNK = 50
PROGRESS_UPDATE_INTERVAL = 5

# In-memory broadcast states per user
_broadcast_states = {}


def _reset_state(uid):
    _broadcast_states.pop(uid, None)


def _get_state(uid):
    return _broadcast_states.get(uid)


def _set_state(uid, state):
    _broadcast_states[uid] = state


# ─── Menu Builder ────────────────────────────────────────────────

def _menu_text():
    return (
        "┏━━━━━━━━━━━━━━━━━⍟\n"
        "┃  📢 **𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐂𝐞𝐧𝐭𝐞𝐫**\n"
        "┗━━━━━━━━━━━━━━━━━━━━━⍟\n\n"
        "Choose broadcast type:\n\n"
        "📝 **Text** — plain text message\n"
        "📷 **Media** — photo or video + caption\n"
        "🎭 **Sticker** — send a sticker\n"
        "↩️ **Forward** — forward replied message as-is\n\n"
        "Legacy shortcuts still work:\n"
        "`/broadcast <text>` or reply + `/broadcast`"
    )


def _menu_buttons():
    return [
        [Button.inline("📝 Text", data="bcast_text"),
         Button.inline("📷 Media", data="bcast_media")],
        [Button.inline("🎭 Sticker", data="bcast_sticker"),
         Button.inline("↩️ Forward", data="bcast_forward")],
        [Button.inline("❌ Cancel", data="bcast_cancel")],
    ]


def _preview_text(state):
    type_labels = {
        "text": "📝 Text",
        "media_photo": "📷 Photo",
        "media_video": "🎥 Video",
        "media_document": "📄 Document",
        "sticker": "🎭 Sticker",
        "forward": "↩️ Forward",
    }
    label = type_labels.get(state["type"], state["type"])
    lines = [
        "┏━━━━━━━━━━━━━━━━━⍟",
        "┃  📢 **𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐏𝐫𝐞𝐯𝐢𝐞𝐰**",
        "┗━━━━━━━━━━━━━━━━━━━━━⍟",
        "",
        f"**Type:** {label}",
    ]
    if state.get("caption"):
        lines.append(f"**Caption:**\n{state['caption']}")
    if state.get("text") and state["type"] == "text":
        lines.append(f"**Message:**\n{state['text']}")
    lines += [
        "",
        "━━━━━━━━━━━━━━━━",
        f"👥 **Recipients:** {state.get('recipient_count', '?')}",
        "━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def _preview_buttons():
    return [
        [Button.inline("✅ Send", data="bcast_send"),
         Button.inline("✏️ Edit", data="bcast_edit")],
        [Button.inline("❌ Cancel", data="bcast_cancel")],
    ]


def _progress_text(sent, failed, total):
    pct = int((sent + failed) / total * 100) if total else 0
    filled = int(pct / 10)
    bar = "█" * filled + "░" * (10 - filled)
    remaining = total - sent - failed
    return (
        "📢 **Broadcasting...**\n\n"
        f"`{bar}` {pct}%\n\n"
        f"✅ Sent: **{sent}** | ❌ Failed: **{failed}** | ⏳ Remaining: **{remaining}**"
    )


def _done_text(sent, failed, total):
    note = "" if not failed else "\n\n❌ Failed = blocked/deleted accounts."
    return (
        "┏━━━━━━━━━━━━━━━━━⍟\n"
        "┃  ✅ **𝐁𝐫𝐨𝐚𝐝𝐜𝐚𝐬𝐭 𝐂𝐨𝐦𝐩𝐥𝐞𝐭𝐞**\n"
        "┗━━━━━━━━━━━━━━━━━━━━━⍟\n\n"
        f"👥 Total: **{total}**\n"
        f"✅ Sent: **{sent}**\n"
        f"❌ Failed: **{failed}**{note}"
    )


# ─── User ID Collection ─────────────────────────────────────────

def _collect_ids(get_all_users_fn, sender_id):
    res = get_all_users_fn()
    if hasattr(res, "__await__"):
        res = asyncio.get_event_loop().run_until_complete(res)
    ids = []
    for u in (res or []):
        try:
            uid = int(getattr(u, "id", u))
            if uid != int(sender_id):
                ids.append(uid)
        except Exception:
            continue
    return list(dict.fromkeys(ids))


def _chunk(ids, size=BROADCAST_CHUNK):
    return [ids[i:i + size] for i in range(0, len(ids), size)] if ids else []


# ─── Broadcast Sender ───────────────────────────────────────────

async def _send_broadcast(bot, state, status_msg, sender_id):
    get_all_users_fn = state.get("get_all_users")
    if not get_all_users_fn:
        return await status_msg.edit("❌ Broadcast source not configured.")

    ids = _collect_ids(get_all_users_fn, sender_id)
    if not ids:
        return await status_msg.edit("❌ No users found to broadcast to.")

    state["recipient_count"] = len(ids)
    chunks = _chunk(ids)
    sent = failed = 0
    total = len(ids)

    for ch in chunks:
        for uid in ch:
            try:
                btype = state["type"]
                if btype == "text":
                    await bot.send_message(uid, state["text"])
                elif btype in ("media_photo", "media_video", "media_document"):
                    file_id = state.get("file_id")
                    caption = state.get("caption", "")
                    if file_id:
                        await bot.send_file(uid, file_id, caption=caption)
                    else:
                        await bot.send_message(uid, caption or "(no content)")
                elif btype == "sticker":
                    file_id = state.get("file_id")
                    if file_id:
                        await bot.send_file(uid, file_id)
                    else:
                        failed += 1
                        continue
                elif btype == "forward":
                    fwd_src = state.get("reply_to")
                    if fwd_src:
                        await bot.forward_messages(uid, fwd_src)
                    else:
                        failed += 1
                        continue
                sent += 1
            except Exception as e:
                if type(e).__name__ == "FloodWaitError":
                    secs = int(getattr(e, "seconds", 60) or 60)
                    try:
                        await status_msg.edit(
                            f"⏳ Flood-wait {secs}s — resuming automatically...\n\n"
                            f"✅ Sent: **{sent}** | ❌ Failed: **{failed}** | ⏳ Remaining: **{total - sent - failed}**",
                            parse_mode="markdown",
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(secs + 5)
                    try:
                        if btype == "text":
                            await bot.send_message(uid, state["text"])
                        elif btype in ("media_photo", "media_video", "media_document"):
                            file_id = state.get("file_id")
                            caption = state.get("caption", "")
                            if file_id:
                                await bot.send_file(uid, file_id, caption=caption)
                            else:
                                await bot.send_message(uid, caption or "(no content)")
                        elif btype == "sticker":
                            file_id = state.get("file_id")
                            if file_id:
                                await bot.send_file(uid, file_id)
                            else:
                                failed += 1
                                continue
                        elif btype == "forward":
                            fwd_src = state.get("reply_to")
                            if fwd_src:
                                await bot.forward_messages(uid, fwd_src)
                            else:
                                failed += 1
                                continue
                        sent += 1
                        continue
                    except Exception:
                        pass
                failed += 1

        # Update progress after each chunk
        if (sent + failed) % PROGRESS_UPDATE_INTERVAL == 0 or (sent + failed) == total:
            try:
                await status_msg.edit(_progress_text(sent, failed, total), parse_mode="markdown")
            except Exception:
                pass
        await asyncio.sleep(2.0)

    # Final update
    try:
        await status_msg.edit(_done_text(sent, failed, total), parse_mode="markdown")
    except Exception:
        pass

    # Track in Redis
    try:
        db = state.get("db")
        if db:
            db.incr("stats:broadcasts")
    except Exception:
        pass

    _reset_state(sender_id)


# ─── Register ────────────────────────────────────────────────────

def register(bot, ctx):
    db = ctx.get("db")
    owner_id = ctx.get("OWNER_ID")
    get_all_users = ctx.get("get_all_users")

    def _is_owner(uid):
        return owner_id is not None and int(uid) == int(owner_id)

    # ─── /broadcast command (entry point) ─────────────────────────
    @bot.on(events.NewMessage(pattern=r"^/broadcast(?:\s|$)", incoming=True, outgoing=False))
    async def _broadcast_cmd(m):
        if not _is_owner(m.sender_id):
            return

        # Legacy: reply + /broadcast → forward mode
        if m.is_reply:
            try:
                fwd_src = await m.get_reply_message()
            except Exception:
                fwd_src = None
            if fwd_src is None:
                return await m.reply("Could not read the replied message.")

            ids = _collect_ids(get_all_users, m.sender_id)
            state = {
                "type": "forward",
                "reply_to": fwd_src,
                "recipient_count": len(ids),
                "get_all_users": get_all_users,
                "db": db,
            }
            _set_state(m.sender_id, state)
            return await m.reply(_preview_text(state), parse_mode="markdown", buttons=_preview_buttons())

        # Legacy: /broadcast <text> → text mode
        text = (m.text or "").split("/broadcast", 1)[1].strip()
        if text:
            ids = _collect_ids(get_all_users, m.sender_id)
            state = {
                "type": "text",
                "text": text,
                "recipient_count": len(ids),
                "get_all_users": get_all_users,
                "db": db,
            }
            _set_state(m.sender_id, state)
            return await m.reply(_preview_text(state), parse_mode="markdown", buttons=_preview_buttons())

        # No text, no reply → show menu
        await m.reply(_menu_text(), parse_mode="markdown", buttons=_menu_buttons())

    # ─── Callback: menu buttons ────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_(text|media|sticker|forward)"))
    async def _bcast_type(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)

        btype = e.data.decode().replace("bcast_", "")
        _reset_state(e.sender_id)

        prompts = {
            "text": "📝 Send the text message to broadcast:",
            "media": "📷 Send the **photo or video** to broadcast:",
            "sticker": "🎭 Send the **sticker** to broadcast:",
            "forward": "↩️ **Reply** to any message with `/broadcast` to forward it.",
        }

        if btype == "forward":
            await e.answer()
            return await e.edit(
                prompts["forward"],
                parse_mode="markdown",
                buttons=[[Button.inline("◀️ Back", data="bcast_menu")]],
            )

        _set_state(e.sender_id, {"type": f"wait_{btype}", "get_all_users": get_all_users, "db": db})
        await e.answer()
        await e.edit(
            prompts[btype],
            parse_mode="markdown",
            buttons=[[Button.inline("◀️ Back", data="bcast_menu")]],
        )

    # ─── Callback: back to menu ────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_menu"))
    async def _bcast_menu(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)
        _reset_state(e.sender_id)
        await e.answer()
        await e.edit(_menu_text(), parse_mode="markdown", buttons=_menu_buttons())

    # ─── Callback: cancel ──────────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_cancel"))
    async def _bcast_cancel(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)
        _reset_state(e.sender_id)
        await e.answer("Broadcast cancelled.")
        try:
            await e.edit("❌ Broadcast cancelled.", buttons=None)
        except Exception:
            pass

    # ─── Callback: send ────────────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_send"))
    async def _bcast_send(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)

        state = _get_state(e.sender_id)
        if not state:
            await e.answer("No broadcast pending.", alert=True)
            return _reset_state(e.sender_id)

        await e.answer("Starting broadcast...")
        status = await e.edit("📢 Starting broadcast...", parse_mode="markdown")
        asyncio.create_task(_send_broadcast(bot, state, status, e.sender_id))

    # ─── Callback: edit ────────────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_edit"))
    async def _bcast_edit(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)
        _reset_state(e.sender_id)
        await e.answer()
        await e.edit(_menu_text(), parse_mode="markdown", buttons=_menu_buttons())

    # ─── Content handler: text input ───────────────────────────────
    @bot.on(events.NewMessage(incoming=True, outgoing=False))
    async def _bcast_content(m):
        if not _is_owner(m.sender_id):
            return

        state = _get_state(m.sender_id)
        if not state:
            return

        btype = state.get("type", "")

        # Waiting for text
        if btype == "wait_text":
            text = (m.text or "").strip()
            if not text or text.startswith("/"):
                return
            state["type"] = "text"
            state["text"] = text
            ids = _collect_ids(get_all_users, m.sender_id)
            state["recipient_count"] = len(ids)
            _set_state(m.sender_id, state)
            await m.reply(_preview_text(state), parse_mode="markdown", buttons=_preview_buttons())
            return

        # Waiting for media (photo/video)
        if btype in ("wait_media", "wait_sticker"):
            is_sticker = btype == "wait_sticker"
            file_id = None
            detected_type = None

            if m.photo:
                file_id = m.photo
                detected_type = "media_photo"
            elif m.video:
                file_id = m.video
                detected_type = "media_video"
            elif m.document:
                if is_sticker:
                    file_id = m.document
                    detected_type = "sticker"
                else:
                    file_id = m.document
                    detected_type = "media_document"
            elif m.sticker:
                file_id = m.sticker
                detected_type = "sticker"
            else:
                return await m.reply("Please send a photo, video, or sticker.")

            state["type"] = detected_type
            state["file_id"] = file_id
            state["original_msg"] = m

            if is_sticker or detected_type == "sticker":
                ids = _collect_ids(get_all_users, m.sender_id)
                state["recipient_count"] = len(ids)
                _set_state(m.sender_id, state)
                return await m.reply(
                    _preview_text(state),
                    parse_mode="markdown",
                    buttons=_preview_buttons(),
                )

            # Ask about caption
            _set_state(m.sender_id, state)
            await m.reply(
                "✏️ Add a caption?\n\nSend the caption text, or tap **No Caption** to skip.",
                parse_mode="markdown",
                buttons=[
                    [Button.inline("No Caption", data="bcast_nocaption")],
                    [Button.inline("◀️ Back", data="bcast_menu")],
                ],
            )
            return

        # Waiting for caption
        if btype == "wait_caption":
            caption = (m.text or "").strip()
            if caption.startswith("/"):
                return
            state = _get_state(m.sender_id)
            if not state:
                return
            state["type"] = state.get("pending_type", "media_photo")
            state["caption"] = caption
            ids = _collect_ids(get_all_users, m.sender_id)
            state["recipient_count"] = len(ids)
            _set_state(m.sender_id, state)
            await m.reply(_preview_text(state), parse_mode="markdown", buttons=_preview_buttons())
            return

    # ─── Callback: no caption ──────────────────────────────────────
    @bot.on(events.CallbackQuery(pattern=rb"bcast_nocaption"))
    async def _bcast_nocaption(e):
        if not _is_owner(e.sender_id):
            return await e.answer("Access denied!", alert=True)

        state = _get_state(e.sender_id)
        if not state:
            await e.answer("No broadcast pending.", alert=True)
            return _reset_state(e.sender_id)

        state["type"] = state.get("pending_type", "media_photo")
        state["caption"] = ""
        ids = _collect_ids(get_all_users, e.sender_id)
        state["recipient_count"] = len(ids)
        _set_state(e.sender_id, state)

        await e.answer()
        await e.edit(_preview_text(state), parse_mode="markdown", buttons=_preview_buttons())
