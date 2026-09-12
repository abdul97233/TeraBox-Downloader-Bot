"""User /cancel + inline cancel buttons. No main.py imports."""

from telethon import Button, events

try:
    from telethon.tl import types as _t
    _CLEAR = _t.ReplyInlineMarkup(rows=[])
except Exception:
    _CLEAR = None

from utils.jobs import list_jobs, request_cancel


def _clr():
    return {"buttons": _CLEAR} if _CLEAR is not None else {}


def _job_lines(jobs):
    lines = []
    for j in jobs:
        tag = " (stale)" if j.get("stale") else ""
        lines.append(f"• `{j['id']}` — {j.get('label', 'job')}{tag}")
    return "\n".join(lines)


def register(bot, ctx):
    db = ctx["db"]

    @bot.on(events.NewMessage(pattern=r"^/cancel$", incoming=True, outgoing=False))
    async def _cancel(m):
        jobs = list_jobs(db, m.sender_id)
        if not jobs:
            try:
                from utils.errors import send_user_error as _sue
                return await _sue(m, "no_active_job")
            except Exception:
                return await m.reply("ℹ️ You don't have any active downloads.")
        if len(jobs) == 1:
            j = jobs[0]
            request_cancel(db, m.sender_id, job_id=j["id"])
            return await m.reply("❌ Download cancelled successfully.")
        text = (f"You currently have {len(jobs)} active jobs.\n\n"
                f"{_job_lines(jobs)}")
        buttons = [
            [Button.inline("❌ Cancel Current", data=f"jobx_one:{jobs[0]['id']}")],
            [Button.inline("❌ Cancel All", data="jobx_all")],
            [Button.inline("Close", data="jobx_close")],
        ]
        await m.reply(text, parse_mode="markdown", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=rb"jobx_tap"))
    async def _tap_cancel(e):
        """Tap-to-cancel on any progress/status message: cancels all live jobs."""
        res = request_cancel(db, e.sender_id, cancel_all=True)
        if res:
            try:
                await e.edit("❌ Download cancelled successfully.", **_clr())
            except Exception:
                try:
                    await e.answer("❌ Download cancelled successfully.", alert=False)
                except Exception:
                    pass
        else:
            try:
                await e.answer("ℹ️ Nothing active — already finished.", alert=False)
            except Exception:
                pass

    @bot.on(events.CallbackQuery(pattern=rb"jobx_(one|all|close)"))
    async def _cancel_btn(e):
        try:
            data = e.data.decode(errors="ignore")
        except Exception:
            data = ""
        if data == "jobx_close":
            try:
                await e.delete()
            except Exception:
                try:
                    await e.answer("Closed.", alert=False)
                except Exception:
                    pass
            return
        if data == "jobx_all":
            res = request_cancel(db, e.sender_id, cancel_all=True)
            try:
                await e.answer(f"Cancelled {len(res)} job(s).", alert=False)
            except Exception:
                pass
            try:
                await e.edit(f"❌ Cancelled {len(res)} job(s).", **_clr())
            except Exception:
                pass
            return
        if data.startswith("jobx_one:"):
            jid = data.split("jobx_one:", 1)[1]
            res = request_cancel(db, e.sender_id, job_id=jid)
            status = res[0][2] if res else "no-such-job"
            msg = "❌ Download cancelled successfully." if status == "cancelled" \
                else "ℹ️ That job is already gone."
            try:
                await e.answer(msg, alert=False)
            except Exception:
                pass
            try:
                await e.edit(msg, **_clr())
            except Exception:
                pass
            return
        try:
            await e.answer("Invalid callback data.", alert=True)
        except Exception:
            pass
