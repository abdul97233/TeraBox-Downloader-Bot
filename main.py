import asyncio
import os
import time
from uuid import uuid4

import redis
import telethon
import telethon.tl.types
from telethon import TelegramClient, events
from telethon import Button
from telethon.tl.functions.messages import ForwardMessagesRequest
from telethon.types import Message, UpdateNewMessage

from cansend import CanSend
from config import *
from terabox import get_files
from tools import (
    convert_seconds,
    download_file,
    download_image_to_bytesio,
    escape_markdown,
    extract_code_from_url,
    get_formatted_size,
    get_video_info,
    get_urls_from_string,
    is_user_on_chat,
    send_document_via_api,
    VIDEO_EXTENSIONS,
)

bot = TelegramClient("tele", API_ID, API_HASH)

db = redis.Redis(
    host=HOST,
    port=PORT,
    password=PASSWORD,
    decode_responses=True,
)

PREMIUM_USERS_KEY = "premium_users"
GIFT_CODES_KEY = "gift_codes"

# Define /info and /id commands to display user information
@bot.on(
    events.NewMessage(
        pattern="/info",
        incoming=True,
        outgoing=False,
    )
)
@bot.on(
    events.NewMessage(
        pattern="/id",
        incoming=True,
        outgoing=False,
    )
)
async def user_info(m: UpdateNewMessage):
    user_id = m.sender_id
    name = m.sender.first_name
    username = m.sender.username if m.sender.username else "-"
    plan = "Premium" if db.sismember(PREMIUM_USERS_KEY, user_id) else "Free"
    info_text = f"Name: {name}\nUsername: @{username}\nUser ID: `{user_id}`\nPlan: {plan}"
    await m.reply(info_text, parse_mode="markdown", link_preview=False)


# Define /cmds or /help command to describe all available commands
# @bot.on(
#     events.NewMessage(
#         pattern="/cmds|/help",
#         incoming=True,
#         outgoing=False,
#         func=lambda x: x.is_private,
#     )
# )
# async def command_help(m: UpdateNewMessage):
#     help_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝘼𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨
# ┗━━━━━━━━━━━━━━━━━⍟

# /start - Start the bot and receive a welcome message.
# /info or /id - Get your user information.
# /redeem <gift_code> - Redeem a gift code for premium access.
# /cmds, or /help to view available cmds 
# /plan - To check availabe plan

# Directly share me the link i will share you the video with direct link

# For premium contact @abdul97233
# """
#     await m.reply(help_text)
@bot.on(
    events.NewMessage(
        pattern="/cmds|/help",
        incoming=True,
        outgoing=False,
        func=lambda x: x.is_private,
    )
)
async def command_help(m: UpdateNewMessage):
    help_text = """
┏━━━━━━━━━━⍟
┃ 𝘼𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨
┗━━━━━━━━━━━━━━━━━⍟

/start - Start the bot and receive a welcome message.
/info or /id - Get your user information.
/redeem <gift_code> - Redeem a gift code for premium access.
/cmds, or /help to view available cmds 
/plan - To check availabe plan

Directly share me the link i will share you the video with direct link

For premium contact @abdul97233
"""

    await m.reply(
        help_text,  # Changed from reply_text to help_text
        link_preview=False,
        parse_mode="markdown",
        buttons=[
            [
                Button.url(
                    "Website Source Code", url="https://github.com/Abdul97233/TeraBox-Downloader-Bot"
                ),
                Button.url(
                    "Bot Source Code",
                    url="https://github.com/Abdul97233/TeraBox-Downloader-Bot",
                ),
            ],
            [
                Button.url("Channel ", url="https://t.me/NTMpro"),
                Button.url("Group ", url="https://t.me/NTMchat"),
            ],
            [
                Button.url("Owner ", url="https://t.me/abdul97233"),
            ],
        ],
    )

    

# Define /ping command to check bot's latency
@bot.on(
    events.NewMessage(
        pattern="/ping",
        incoming=True,
        outgoing=False,
        # func=lambda x: x.is_private,
    )
)
async def ping_pong(m: UpdateNewMessage):
    start_time = time.time()
    message = await m.reply("🖥️ Connection Status\nCommand: `/ping`\nResponse Time: Calculating...")
    end_time = time.time()
    latency = end_time - start_time  # Calculate latency in seconds
    latency_str = "{:.2f}".format(latency)  # Format latency with two decimal places
    await message.edit(f"🖥️ Connection Status\nCommand: `/ping`\nResponse Time: {latency_str} seconds")

# Generate gift codes
@bot.on(
    events.NewMessage(
        pattern=r"/gc (\d+)",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
# async def generate_gift_codes(m: UpdateNewMessage):
#     quantity = int(m.pattern_match.group(1))
#     gift_codes = [f"NTM-{str(uuid4())[:8]}" for _ in range(quantity)]
#     db.sadd(GIFT_CODES_KEY, *gift_codes)
#     await m.reply(f"{quantity} gift codes generated: {', '.join(gift_codes)}")
# async def generate_gift_codes(m: UpdateNewMessage):
#     quantity = int(m.pattern_match.group(1))
#     gift_codes = [f"NTM-{str(uuid4())[:8]}" for _ in range(quantity)]
#     db.sadd(GIFT_CODES_KEY, *gift_codes)
#     reply_text = "\n".join(gift_codes)  # Joining the gift codes with newline character
#     await m.reply(reply_text)

async def generate_gift_codes(m: UpdateNewMessage):
    quantity = int(m.pattern_match.group(1))
    gift_codes = [f"NTM-{str(uuid4())[:8]}" for _ in range(quantity)]
    db.sadd(GIFT_CODES_KEY, *gift_codes)
    
    # Send a reply confirming the generation of gift codes
    await m.reply(f"{quantity} gift codes generated. Here they are:")
    
    # Send each gift code as a separate message with some interval (e.g., 1 second)
    for code in gift_codes:
        await asyncio.sleep(1)  # Introduce a delay to avoid rate limiting
        await m.reply(code)


# Redeem gift codes
# @bot.on(
#     events.NewMessage(
#         pattern="/redeem (.*)",
#         incoming=True,
#         outgoing=False,
#     )
# )
# async def redeem_gift_code(m: UpdateNewMessage):
#     gift_code = m.pattern_match.group(1)
#     if db.sismember(GIFT_CODES_KEY, gift_code):
#         db.sadd(PREMIUM_USERS_KEY, m.sender_id)
#         db.srem(GIFT_CODES_KEY, gift_code)
#         await m.reply("Gift code redeemed successfully. You are now a premium user!")
#     else:
#         await m.reply("Invalid or expired gift code.")

# Redeem gift codes
# @bot.on(
#     events.NewMessage(
#         pattern="/redeem (.*)",
#         incoming=True,
#         outgoing=False,
#     )
# )
# async def redeem_gift_code(m: UpdateNewMessage):
#     gift_code = m.pattern_match.group(1)
#     if db.sismember(GIFT_CODES_KEY, gift_code):
#         user_id = m.sender_id
#         user = await bot.get_entity(user_id)
#         name = user.first_name
#         username = user.username if user.username else "-"
#         db.sadd(PREMIUM_USERS_KEY, user_id)
#         db.srem(GIFT_CODES_KEY, gift_code)
#         admin_message = f"Gift code redeemed by:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
#         await bot.send_message(ADMIN_ID, admin_message)
#         await m.reply("Gift code redeemed successfully. You are now a premium user!")
#     else:
#         await m.reply("Invalid or expired gift code.")


# Redeem gift codes
@bot.on(
    events.NewMessage(
        pattern="/redeem (.*)",
        incoming=True,
        outgoing=False,
    )
)
async def redeem_gift_code(m: UpdateNewMessage):
    gift_code = m.pattern_match.group(1)
    if db.sismember(GIFT_CODES_KEY, gift_code):
        user_id = m.sender_id
        user = await bot.get_entity(user_id)
        name = user.first_name
        username = user.username if user.username else "-"
        db.sadd(PREMIUM_USERS_KEY, user_id)
        db.srem(GIFT_CODES_KEY, gift_code)
        admin_message = f"Gift code redeemed by:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
        for admin_id in ADMINS:
            await bot.send_message(admin_id, admin_message)
        await m.reply("Gift code redeemed successfully. You are now a premium user!")
    else:
        await m.reply("Invalid or expired gift code.")

@bot.on(
    events.NewMessage(
        pattern="/broadcast",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def broadcast_message(m: UpdateNewMessage):
    broadcast_text = m.text.split("/broadcast", 1)[1].strip()
    if not broadcast_text:
        return await m.reply(
            "**Usage:** `/broadcast <message>`\n"
            "Send a message to all bot users."
        )

    status = await m.reply("Broadcasting...")

    all_users = await bot.get_participants(-1001336746488)
    total = len(all_users)
    sent = 0
    failed = 0

    for user in all_users:
        try:
            await bot.send_message(user.id, broadcast_text)
            sent += 1
        except Exception:
            failed += 1

    await status.edit(
        f"**Broadcast Complete**\n\n"
        f"Total users: **{total}**\n"
        f"Sent: **{sent}**\n"
        f"Failed: **{failed}**",
        parse_mode="markdown",
    )


# Define start command to check user's plan and send welcome message accordingly
# @bot.on(
#     events.NewMessage(
#         pattern="/start",
#         incoming=True,
#         outgoing=False,
#     )
# )
# async def start(m: UpdateNewMessage):
#     user_id = m.sender_id
#     if db.sismember(PREMIUM_USERS_KEY, user_id):
#         # Premium user
#         reply_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
# ┗━━━━━━━━━━━━━━━━━⍟
# ╔══════════⍟
# ┃🌟 Welcome! 🌟
# ┃
# ┃Excited to introduce Tera Box video downloader bot! 🤖 
# ┃Simply share the terabox link, and voila! 
# ┃Your desired video will swiftly start downloading. 
# ┃It's that easy! 🚀
# ╚═════════════════⍟
# Do /help or /cmds - Display available commands.

# [『 𝗡⋆𝗧⋆𝗠 』](https://t.me/NTMpro) 
# """
#     else:
#         # Free user
#         reply_text = """
# ┏━━━━━━━━━━⍟
# ┃ 𝐅𝐑𝐄𝐄 𝐔𝐒𝐄𝐑 
# ┗━━━━━━━━━━━━━━━━━⍟
# ╔══════════⍟ 
# ┃ As a free user, 
# ┃ you're not approved to access the full capabilities of this bot.
# ┃
# ┃ Upgrade to premium or utilize /id, /cmds, or /help to view available details. 
# ┃
# ┃ To check availabe plan do /plan in chat group @NTMchat
# ╚═════════════════⍟
# For subscription inquiries, contact @abdul97233.
# """

#     # Send the welcome message
#     check_if = await is_user_on_chat(bot, "@NTMpro", m.peer_id)
#     if not check_if:
#         return await m.reply("Please join @NTMpro then send me the link again.")
#     await m.reply(reply_text, link_preview=False, parse_mode="markdown")

# Define start command to check user's plan and send welcome message accordingly
@bot.on(
    events.NewMessage(
        pattern="/start",
        incoming=True,
        outgoing=False,
    )
)
async def start(m: UpdateNewMessage):
    user_id = m.sender_id
    user = await bot.get_entity(user_id)
    name = user.first_name
    username = user.username if user.username else "-"
    
    admin_message = f"User started the bot:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
    for admin_id in ADMINS:
        await bot.send_message(admin_id, admin_message)
    
    reply_text = """
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
┃🌟 Welcome! 🌟
┃
┃Excited to introduce Tera Box video downloader bot! 🤖 
┃Simply share the terabox link, and voila! 
┃Your desired video will swiftly start downloading. 
┃It's that easy! 🚀
╚═════════════════⍟
Do /help or /cmds - Display available commands.

[『 𝗡⋆𝗧⋆𝗠 』](https://t.me/NTMpro) 
"""
    await m.reply(
        reply_text,
        link_preview=False,
        parse_mode="markdown",
        buttons=[
            [
                Button.url(
                    "Website Source Code", url="https://github.com/Abdul97233/TeraBox-Downloader-Bot"
                ),
                Button.url(
                    "Bot Source Code",
                    url="https://github.com/Abdul97233/TeraBox-Downloader-Bot",
                ),
            ],
            [
                Button.url("Channel ", url="https://t.me/NTMpro"),
                Button.url("Group ", url="https://t.me/NTMchat"),
            ],
            [
                Button.url("Owner ", url="https://t.me/abdul97233"),
            ],
        ],
    )
# Handler for when a user joins the chat
@bot.on(events.ChatAction)
async def user_joined(event):
    if event.user_joined:
        user_id = event.user_id
        user = await bot.get_entity(user_id)
        name = user.first_name
        username = user.username if user.username else "-"
        
        admin_message = f"User joined the bot:\nName: {name}\nUsername: @{username}\nUser ID: {user_id}"
        for admin_id in ADMINS:
            await bot.send_message(admin_id, admin_message)

@bot.on(
    events.NewMessage(
        pattern="/remove (.*)",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def remove(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    if db.get(f"check_{user_id}"):
        db.delete(f"check_{user_id}")
        await m.reply(f"Removed {user_id} from the list.")
    else:
        await m.reply(f"{user_id} is not in the list.")
        

# Define /plan command to display premium plans and payment methods
@bot.on(
    events.NewMessage(
        pattern="/plan",
        incoming=True,
        outgoing=False,
    )
)
async def display_plan(m: UpdateNewMessage):
    plan_text = """
┏━━━━━━━━━━⍟
┃ 𝐓𝐄𝐑𝐀 𝐁𝐎𝐗 𝐏𝐑𝐄𝐌𝐈𝐔𝐌 𝐁𝐎𝐓 𝐩𝐥𝐚𝐧
┗━━━━━━━━━━━━━━━━━⍟

Membership Plans:
1. Rs. 100 for 10 days
2. Rs. 60 for 4 days
3. Rs. 30 for 2 days
4. Rs. 20 for 1 day

Payment Methods Available:
- UPI
- Esewa
- Khalti
- Phone Pay
- Fone Pay
- PayPal

Note: Nepal and India all payment accepted.

To purchase premium, send a message to @Abdul97233.
"""
    await m.reply(plan_text, parse_mode="markdown")

# Define premium user promotion command
@bot.on(
    events.NewMessage(
        pattern="/pre (.*)",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def pre(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    if not db.sismember(PREMIUM_USERS_KEY, user_id):
        db.sadd(PREMIUM_USERS_KEY, user_id)
        await m.reply(f"Promoted {user_id} to premium.")
    else:
        await m.reply(f"{user_id} is already a premium user.")

# Command to check all premium users with name, username, and user ID
@bot.on(
    events.NewMessage(
        pattern="/premium_users",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def premium_users(m: UpdateNewMessage):
    premium_users = db.smembers(PREMIUM_USERS_KEY)
    if premium_users:
        users_info = []
        for user_id in premium_users:
            user = await bot.get_entity(int(user_id))
            name = user.first_name
            username = user.username if user.username else "-"
            users_info.append(f"\nName: {name}, \nUsername: @{username}, \nUser ID: {user_id}")
        users_text = "\n".join(users_info)
        await m.reply(f"Premium Users:\n{users_text}")
    else:
        await m.reply("No premium users found.")

# Command to directly demote all premium users
@bot.on(
    events.NewMessage(
        pattern="/demote_all_premium",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def demote_all_premium(m: UpdateNewMessage):
    db.delete(PREMIUM_USERS_KEY)
    await m.reply("All premium users demoted successfully.")


# Define premium user demotion command
@bot.on(
    events.NewMessage(
        pattern="/de (.*)",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def de(m: UpdateNewMessage):
    user_id = m.pattern_match.group(1)
    if db.sismember(PREMIUM_USERS_KEY, user_id):
        db.srem(PREMIUM_USERS_KEY, user_id)
        await m.reply(f"Demoted {user_id} from premium.")
    else:
        await m.reply(f"{user_id} is not a premium user.")


@bot.on(
    events.NewMessage(
        incoming=True,
        outgoing=False,
        func=lambda message: message.text
        and get_urls_from_string(message.text)
        and message.is_private,
    )
)
async def get_message(m: Message):
    asyncio.create_task(handle_message(m))


async def handle_message(m: Message):

    url = get_urls_from_string(m.text)
    if not url:
        return await m.reply("Please enter a valid url.")
    check_if = await is_user_on_chat(bot, "@NTMpro", m.sender_id)
    if not check_if:
        return await m.reply("Please join @NTMpro then send me the link again.")
    check_if = await is_user_on_chat(bot, "@NTMchat", m.sender_id)
    if not check_if:
        return await m.reply(
            "Please join @NTMchat then send me the link again."
        )
    
    hm = await m.reply("Sending you the media wait...")

    is_premium = bool(db.sismember(PREMIUM_USERS_KEY, m.sender_id))
    count = db.get(f"check_{m.sender_id}")

    # Free user rate limit: 10 downloads per hour
    if not is_premium and m.sender_id not in ADMINS:
        if count and int(count) >= 10:
            ttl = db.ttl(f"check_{m.sender_id}")
            ttl_text = convert_seconds(ttl) if ttl and ttl > 0 else "1 hour"
            return await hm.edit(
                f"You've reached your limit (10 videos/hour).\n"
                f"Try again in **{ttl_text}**.\n"
                f"Upgrade to **Premium** for unlimited downloads."
            )

    shorturl = extract_code_from_url(url)
    if not shorturl:
        return await hm.edit("Seems like your link is invalid.")

    files = await get_files(url)
    if not files:
        return await hm.edit("Sorry! API is dead or maybe your link is broken.")

    # Premium users get all files, free users get only the first one
    files_to_process = files if is_premium else files[:1]
    total = len(files_to_process)

    # Cached forwarding only works for the single-file (free) flow
    if not is_premium:
        fileid = db.get(shorturl)
        if fileid:
            try:
                cached_msg = await bot.get_messages(PRIVATE_CHAT_ID, ids=int(fileid))
                if cached_msg and cached_msg.media:
                    data = files_to_process[0]
                    cached_caption = f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{data['size']}**
╟➣𝗙𝗶𝗿𝘀𝗧 𝗡𝗮𝗺𝗲: {escape_markdown(m.sender.first_name)}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: @{escape_markdown(m.sender.username or '-')}
╚═════════════════⍟
         @NTMpro
"""
                    await bot.send_file(
                        m.chat.id,
                        file=cached_msg.media,
                        caption=cached_caption,
                        supports_streaming=True,
                    )
                    await hm.delete()
                    db.set(
                        f"check_{m.sender_id}",
                        int(count) + 1 if count else 1,
                        ex=3600,
                    )
                    return
            except Exception as e:
                print(f"Cache forward failed: {e}")

    user_first_name = m.sender.first_name
    user_username = m.sender.username
    cansend = CanSend()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    for idx, data in enumerate(files_to_process, start=1):

        # -------- Per-file supported type check --------
        fname_lower = data["file_name"].lower()
        file_ext = "." + fname_lower.rsplit(".", 1)[-1] if "." in fname_lower else ""
        if file_ext not in VIDEO_EXTENSIONS:
            if total == 1:
                supported = ", ".join(VIDEO_EXTENSIONS)
                return await hm.edit(
                    f"Sorry! File type `{file_ext}` is not supported.\nSupported: {supported}"
                )
            await hm.edit(f"Skipping unsupported file: `{data['file_name']}`")
            continue

        # -------- Per-file size check (admins and premium bypass) --------
        if int(data["sizebytes"]) > 524288000 and m.sender_id not in ADMINS and not is_premium:
            if total == 1:
                return await hm.edit(
                    f"Sorry! File is too big. I can download only 500MB and this file is of {data['size']} ."
                )
            await hm.edit(f"Skipping too big file: `{data['file_name']}` ({data['size']})")
            continue

        start_time = time.time()
        label = f"({idx}/{total}) " if total > 1 else ""

        async def progress_bar(current_downloaded, total_downloaded, state="Sending"):

            if not cansend.can_send():
                return
            bar_length = 20
            percent = current_downloaded / total_downloaded
            arrow = "█" * int(percent * bar_length)
            spaces = "░" * (bar_length - len(arrow))

            elapsed_time = time.time() - start_time

            head_text = f"{state} {label}`{data['file_name']}`"
            bar_text = f"[{arrow + spaces}] {percent:.2%}"
            upload_speed = current_downloaded / elapsed_time if elapsed_time > 0 else 0
            speed_mbps = upload_speed / (1024 * 1024)
            speed_line = f"Speed: **{speed_mbps:.2f} MB/s**"

            time_remaining = (
                (total_downloaded - current_downloaded) / upload_speed
                if upload_speed > 0
                else 0
            )
            time_line = f"Time Remaining: `{convert_seconds(time_remaining)}`"

            size_line = f"Size: **{get_formatted_size(current_downloaded)}** / **{get_formatted_size(total_downloaded)}**"

            await hm.edit(
                f"{head_text}\n{bar_text}\n{speed_line}\n{time_line}\n{size_line}",
                parse_mode="markdown",
            )

        uuid = str(uuid4())
        thumbnail = download_image_to_bytesio(data["thumb"], "thumbnail.png")

        download = await download_file(
            data["direct_link"], os.path.join(DOWNLOAD_DIR, data["file_name"]), progress_bar
        )
        total_time = time.time() - start_time
        if not download:
            if total == 1:
                return await hm.edit(
                    f"Sorry! Download Failed but you can download it from [here]({url}).",
                    parse_mode="markdown",
                )
            await hm.edit(f"Download failed for `{data['file_name']}`")
            continue

        caption = f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{escape_markdown(data['size'])}** 
╟➣𝗗𝗶𝗿𝗲𝗰𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗟𝗶𝗻𝗸 : [Click here]({data['direct_link']})
╟➣𝗙𝗶𝗿𝘀𝗧 𝗡𝗮𝗺𝗲: {escape_markdown(user_first_name)}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: @{escape_markdown(user_username or '-')}
╟➣𝐓𝐨𝐭𝐚𝐥 𝐓𝐢𝐦𝐞 𝐓𝐚𝐤𝐞𝐧: {total_time} sec
╚═════════════════⍟
         @NTMpro
"""

        # ---- Extract video metadata (duration, width, height, thumbnail) ----
        vinfo = get_video_info(download)
        vduration = vinfo.get("duration", 0)
        vwidth = vinfo.get("width", 0)
        vheight = vinfo.get("height", 0)
        vthumb = vinfo.get("thumbnail")
        if vthumb and not thumbnail:
            thumbnail = download_image_to_bytesio(vthumb, "thumb.jpg")

        # ---- Upload via self-hosted Telegram Bot API (2GB / high speed) ----
        sent_id = None
        try:
            api_res = await send_document_via_api(
                TG_API_BASE, BOT_TOKEN, PRIVATE_CHAT_ID, download, caption, data["file_name"], progress_bar,
                duration=vduration, width=vwidth, height=vheight, thumb=vthumb,
            )
            if api_res.get("ok"):
                sent_id = api_res["result"]["message_id"]
                print("Uploaded via custom Bot API, message_id:", sent_id)
            else:
                print("Custom Bot API error:", api_res)
        except Exception as e:
            print("Custom Bot API upload failed:", e)

        # ---- Fallback to Telethon MTProto upload if Bot API path failed ----
        if sent_id is None:
            try:
                file = await bot.send_file(
                    PRIVATE_CHAT_ID,
                    file=download,
                    thumb=thumbnail if thumbnail else None,
                    progress_callback=progress_bar,
                    caption=caption,
                    video=True,
                    supports_streaming=True,
                    duration=vduration,
                    attributes=[],
                    spoiler=True,
                )
                sent_id = file.id
            except Exception as e:
                print("Telethon upload failed:", e)
                try:
                    os.unlink(download)
                except Exception:
                    pass
                if total == 1:
                    return await hm.edit(
                        f"Sorry! Upload Failed but you can download it from [here]({url}).",
                        parse_mode="markdown",
                    )
                await hm.edit(f"Upload failed for `{data['file_name']}`")
                continue

        if sent_id:
            if shorturl and not is_premium:
                db.set(shorturl, sent_id)
            db.set(uuid, sent_id)

            # ---- Forward video from PRIVATE_CHAT_ID to user (instant, no re-upload) ----
            fwd_kwargs = dict(
                from_peer=PRIVATE_CHAT_ID,
                id=[sent_id],
                to_peer=m.chat.id,
                drop_author=True,
                background=True,
                drop_media_captions=False,
                with_my_score=True,
            )
            if m.is_group:
                fwd_kwargs["top_msg_id"] = m.id
            try:
                await bot(ForwardMessagesRequest(**fwd_kwargs))
            except Exception as e:
                print("Forward failed:", e)

            # Cleanup download file
            try:
                os.unlink(download)
            except Exception:
                pass

            # Success message
            try:
                await hm.edit("✅ Video sent successfully to your chat!")
            except Exception:
                pass

            db.set(
                f"check_{m.sender_id}",
                int(count) + 1 if count else 1,
                ex=3600,
            )



# Define /cleandownloads command for admins to free VPS storage
@bot.on(
    events.NewMessage(
        pattern="/cleandownloads",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,
    )
)
async def clean_downloads(m: UpdateNewMessage):
    if not os.path.isdir(DOWNLOAD_DIR):
        return await m.reply("Downloads folder does not exist. Nothing to clean.")

    files = [
        os.path.join(DOWNLOAD_DIR, f)
        for f in os.listdir(DOWNLOAD_DIR)
        if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))
    ]

    if not files:
        return await m.reply("Downloads folder is already empty.")

    total_size = sum(os.path.getsize(f) for f in files)

    deleted = 0
    for f in files:
        try:
            os.unlink(f)
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {f}: {e}")

    if deleted:
        return await m.reply(
            f"Cleaned **{deleted}** file(s) and freed **{get_formatted_size(total_size)}** of storage."
        )
    return await m.reply("Could not delete any files. Check permissions.")


# ---- Background cleanup task: auto-delete downloads older than 1 hour ----
CLEANUP_INTERVAL = 3600  # 1 hour in seconds


async def auto_cleanup_downloads():
    """Periodically delete files in DOWNLOAD_DIR older than 1 hour."""
    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            if not os.path.isdir(DOWNLOAD_DIR):
                continue
            now = time.time()
            for filename in os.listdir(DOWNLOAD_DIR):
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if now - file_mtime > CLEANUP_INTERVAL:
                        try:
                            os.unlink(filepath)
                            print(f"Auto-deleted old file: {filepath}")
                        except Exception as e:
                            print(f"Failed to auto-delete {filepath}: {e}")
        except asyncio.CancelledError:
            break


# Start the cleanup task before running the bot
cleanup_task = bot.loop.create_task(auto_cleanup_downloads())

bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
cleanup_task.cancel()
