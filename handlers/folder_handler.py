"""Future home of the /folder handler.

Migration plan (do NOT move the live handler here until tested on VPS):
  1. Move pure helpers first (done: utils/tags.py, utils/premium.py,
     commands/user_status.py).
  2. Next, move folder progress-text builders here as pure functions.
  3. Finally, move the @bot.on handler with a register(bot, ctx) pattern
     where ctx carries bot/db/config callables (avoids circular imports).

Keeping this stub import-safe: importing this module must never fail.
"""

FOLDER_HANDLER_VERSION = "stub-v1"
