"""Media conversions: MP3 bitrate menu + compression resolution menu.

No main.py imports. FFmpeg runs in executors (never blocks the loop),
tracked as cancellable jobs. No upscaling: only heights <= source.
"""

import asyncio
import os as _os

from telethon import Button, events

try:
    from telethon.tl import types as _t
    _CLEAR = _t.ReplyInlineMarkup(rows=[])
except Exception:
    _CLEAR = None

MP3_RATES = ("128", "192", "256", "320")
CMP_HEIGHTS = (480, 720, 1080)
CMP_CRF = {480: 26, 720: 23, 1080: 20}


async def _final_edit(msg, text):
    """Terminal status edit that also removes the Cancel button."""
    try:
        if _CLEAR is not None:
            await _final_edit(msg, text, buttons=_CLEAR)
        else:
            await _final_edit(msg, text)
    except Exception:
        pass


def _parse_target(data):
    """b'mp3_192_-100x_42' -> (kind, opt, chat_id, msg_id) or None."""
    try:
        parts = data.decode(errors="ignore").split("_")
        if len(parts) != 4:
            return None
        kind, opt = parts[0], parts[1]
        if kind not in ("mp3", "cmp"):
            return None
        return kind, opt, int(parts[2]), int(parts[3])
    except Exception:
        return None


def _has_audio_sync(video_path):
    import subprocess as _sp
    import shutil as _sh
    ff = _sh.which("ffmpeg")
    if not ff:
        return None
    try:
        r = _sp.run([ff, "-hide_banner", "-i", video_path],
                    capture_output=True, text=True, timeout=60)
        return "Audio:" in (r.stderr or "")
    except Exception:
        return None


def _probe_wh_sync(video_path):
    try:
        from tools import get_video_info
        info = get_video_info(video_path)
        return int(info.get("width") or 0), int(info.get("height") or 0)
    except Exception:
        return 0, 0


def register(bot, ctx):
    import uuid as _uuid
    db = ctx["db"]
    is_admin = ctx["is_admin"]
    is_maintenance = ctx["is_maintenance"]
    download_dir = ctx.get("download_dir", "downloads")

    def _gated(uid):
        try:
            return bool(is_maintenance()) and not bool(is_admin(uid))
        except Exception:
            return False

    async def _need_media(m):
        if not m.is_reply:
            return None, ("Usage: reply to a video first, then send the command again.", False)
        try:
            replied = await m.get_reply_message()
        except Exception:
            replied = None
        if not replied or not replied.media:
            return None, ("Replied message has no media.", False)
        return replied, ("", True)

    @bot.on(events.NewMessage(pattern=r"^/mp3$", incoming=True, outgoing=False))
    async def _mp3_menu(m):
        if _gated(m.sender_id):
            return await m.reply("🔧 Bot is currently under maintenance. Please try again later.")
        replied, (err, ok) = await _need_media(m)
        if not ok:
            return await m.reply(err)
        import shutil as _sh
        if not _sh.which("ffmpeg"):
            return await m.reply("ffmpeg not installed on server.")
        buttons = [[Button.inline(f"{br} kbps", data=f"mp3_{br}_{m.chat.id}_{replied.id}")]
                   for br in MP3_RATES]
        await m.reply("🎵 Extract Audio\n\nChoose a bitrate:", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"mp3_"))
    async def _mp3_go(e):
        parsed = _parse_target(e.data)
        if not parsed or parsed[0] != "mp3" or parsed[1] not in MP3_RATES:
            try:
                await e.answer("Invalid selection.", alert=True)
            except Exception:
                pass
            return
        _, br, chat_id, msg_id = parsed
        if _gated(e.sender_id):
            try:
                await e.answer("Bot is under maintenance.", alert=True)
            except Exception:
                pass
            return
        from utils.jobs import job_scope, ffmpeg_run
        try:
            target = await bot.get_messages(chat_id, ids=msg_id)
        except Exception:
            target = None
        if not target or not target.media:
            try:
                await e.answer("Original message not found.", alert=True)
            except Exception:
                pass
            return
        msg = await e.reply(
            f"🎵 Extracting audio ({br} kbps)...",
            buttons=[[Button.inline("❌ Cancel", data="jobx_tap")]],
        )
        video_path = _os.path.join(download_dir, f"mp3_{_uuid.uuid4().hex}.mp4")
        audio_path = video_path.replace(".mp4", f"_{br}k.mp3")
        try:
            async with job_scope(db, e.sender_id, f"mp3:{br}k", msg=msg) as job:
                _os.makedirs(download_dir, exist_ok=True)
                job["files"].extend([video_path, audio_path])
                await bot.download_media(target, video_path)
                loop = asyncio.get_event_loop()
                has_audio = await loop.run_in_executor(None, _has_audio_sync, video_path)
                if has_audio is False:
                    try:
                        await _final_edit(msg, "❌ This file does not contain an audio track.")
                    except Exception:
                        pass
                    return
                import shutil as _sh
                cmd = [_sh.which("ffmpeg"), "-y", "-i", video_path, "-vn",
                       "-acodec", "libmp3lame", "-ab", f"{br}k", "-ar", "44100",
                       "-map_metadata", "0", "-id3v2_version", "3", audio_path]
                rc, _out, err = await loop.run_in_executor(None, ffmpeg_run, cmd, 600, job)
                if rc != 0 or not _os.path.isfile(audio_path):
                    try:
                        await _final_edit(msg, "❌ Audio extraction failed.")
                    except Exception:
                        pass
                    try:
                        from utils.logx import safe_exc
                        import logging as _logging
                        _logging.getLogger("bot").info(f"mp3 failed: {safe_exc(err, 120)}")
                    except Exception:
                        pass
                    return
                try:
                    audio_mb = _os.path.getsize(audio_path) / 1048576
                except Exception:
                    audio_mb = 0
                await bot.send_file(
                    e.sender_id, file=audio_path,
                    caption=f"🎵 Audio ({br} kbps){f' — {audio_mb:.1f}MB' if audio_mb else ''}",
                    voice_note=False,
                )
                try:
                    db.hincrby(f"user_stats_{int(e.sender_id)}", "audio", 1)
                except Exception:
                    pass
                try:
                    await msg.delete()
                except Exception:
                    pass
        except asyncio.CancelledError:
            try:
                await _final_edit(msg, "❌ Download cancelled successfully.")
            except Exception:
                pass
        except Exception:
            try:
                await _final_edit(msg, "❌ Media processing failed.")
            except Exception:
                pass
        finally:
            for f in (video_path, audio_path):
                try:
                    if f and _os.path.isfile(f):
                        _os.unlink(f)
                except Exception:
                    pass

    @bot.on(events.NewMessage(pattern=r"^/compress(?:\s+(\w+))?$", incoming=True, outgoing=False))
    async def _compress_menu(m):
        if _gated(m.sender_id):
            return await m.reply("🔧 Bot is currently under maintenance. Please try again later.")
        replied, (err, ok) = await _need_media(m)
        if not ok:
            return await m.reply(
                "Usage: Reply to a video with `/compress`\n\n"
                "Example:\n1. Send a video\n2. Reply to it with `/compress`\n3. Pick a resolution"
            )
        import shutil as _sh
        if not _sh.which("ffmpeg"):
            return await m.reply("ffmpeg not installed on server.")
        arg = (m.pattern_match.group(1) or "").lower()
        tmp = _os.path.join(download_dir, f"probe_{_uuid.uuid4().hex}.mp4")
        try:
            _os.makedirs(download_dir, exist_ok=True)
            await bot.download_media(replied, tmp)
            loop = asyncio.get_event_loop()
            _w, _h = await loop.run_in_executor(None, _probe_wh_sync, tmp)
        except Exception:
            _w, _h = 0, 0
        finally:
            try:
                if _os.path.isfile(tmp):
                    _os.unlink(tmp)
            except Exception:
                pass
        if _h and _h < min(CMP_HEIGHTS):
            return await m.reply(f"Source is only {_h}p — nothing to gain from compressing.")
        offered = [h for h in CMP_HEIGHTS if not _h or h <= _h]
        if arg in ("480", "720", "1080") and int(arg) in offered:
            offered = [int(arg)]
        buttons = [[Button.inline(f"{h}p", data=f"cmp_{h}_{m.chat.id}_{replied.id}")]
                   for h in offered]
        src = f"Source: {_w}x{_h}" if _w and _h else "Source resolution unknown"
        await m.reply(f"🎞 Compress Video\n\n{src}\nChoose output (no upscaling):", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"cmp_"))
    async def _cmp_go(e):
        parsed = _parse_target(e.data)
        if not parsed or parsed[0] != "cmp":
            try:
                await e.answer("Invalid selection.", alert=True)
            except Exception:
                pass
            return
        _, h, chat_id, msg_id = parsed
        try:
            h = int(h)
        except Exception:
            h = 0
        if h not in CMP_HEIGHTS:
            try:
                await e.answer("Invalid selection.", alert=True)
            except Exception:
                pass
            return
        if _gated(e.sender_id):
            try:
                await e.answer("Bot is under maintenance.", alert=True)
            except Exception:
                pass
            return
        from utils.jobs import job_scope, ffmpeg_run
        try:
            target = await bot.get_messages(chat_id, ids=msg_id)
        except Exception:
            target = None
        if not target or not target.media:
            try:
                await e.answer("Original message not found.", alert=True)
            except Exception:
                pass
            return
        msg = await e.reply(
            f"⚙️ Processing video...\n\nResolution: {h}p\nPlease wait.",
            buttons=[[Button.inline("❌ Cancel", data="jobx_tap")]],
        )
        video_path = _os.path.join(download_dir, f"cmp_{_uuid.uuid4().hex}.mp4")
        out_path = video_path.replace(".mp4", f"_{h}p.mp4")
        try:
            async with job_scope(db, e.sender_id, f"cmp:{h}p", msg=msg) as job:
                _os.makedirs(download_dir, exist_ok=True)
                job["files"].extend([video_path, out_path])
                await bot.download_media(target, video_path)
                loop = asyncio.get_event_loop()
                _w, src_h = await loop.run_in_executor(None, _probe_wh_sync, video_path)
                if src_h and h > src_h:
                    try:
                        await _final_edit(msg, f"Source is {src_h}p — {h}p would upscale. Picked nothing; try a lower option.")
                    except Exception:
                        pass
                    return
                import shutil as _sh
                crf = CMP_CRF.get(h, 23)
                cmd = [_sh.which("ffmpeg"), "-y", "-i", video_path,
                       "-vf", f"scale=-2:{h}", "-c:v", "libx264",
                       "-crf", str(crf), "-preset", "fast",
                       "-c:a", "aac", "-b:a", "128k", out_path]
                rc, _out, err = await loop.run_in_executor(None, ffmpeg_run, cmd, 900, job)
                if rc != 0 or not _os.path.isfile(out_path):
                    try:
                        await _final_edit(msg, "❌ Video processing failed.")
                    except Exception:
                        pass
                    try:
                        from utils.logx import safe_exc
                        import logging as _logging
                        _logging.getLogger("bot").info(f"compress failed: {safe_exc(err, 120)}")
                    except Exception:
                        pass
                    return
                try:
                    o_mb = _os.path.getsize(video_path) / 1048576
                    n_mb = _os.path.getsize(out_path) / 1048576
                except Exception:
                    o_mb = n_mb = 0
                await bot.send_file(
                    e.sender_id, file=out_path,
                    caption=f"🎞 Compressed to {h}p!\n{ o_mb:.1f}MB -> {n_mb:.1f}MB" if o_mb else f"🎞 Compressed to {h}p!",
                    supports_streaming=True,
                )
                try:
                    db.hincrby(f"user_stats_{int(e.sender_id)}", "video", 1)
                except Exception:
                    pass
                try:
                    await msg.delete()
                except Exception:
                    pass
        except asyncio.CancelledError:
            try:
                await _final_edit(msg, "❌ Download cancelled successfully.")
            except Exception:
                pass
        except Exception:
            try:
                await _final_edit(msg, "❌ Media processing failed.")
            except Exception:
                pass
        finally:
            for f in (video_path, out_path):
                try:
                    if f and _os.path.isfile(f):
                        _os.unlink(f)
                except Exception:
                    pass
