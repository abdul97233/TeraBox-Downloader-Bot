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
from terabox import get_data
from tools import (
    convert_seconds,
    download_file,
    download_image_to_bytesio,
    extract_code_from_url,
    get_formatted_size,
    get_urls_from_string,
    is_user_on_chat,
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
        pattern="/gc (\d+)",
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

# Define /broadcast command to allow admins to send broadcast messages
@bot.on(
    events.NewMessage(
        pattern="/broadcast",
        incoming=True,
        outgoing=False,
        from_users=ADMINS,  # Only allow admins to use this command
    )
)
async def broadcast_message(m: UpdateNewMessage):
    # Extract the broadcast message from the command
    broadcast_text = m.text.split("/broadcast", 1)[1].strip()
    
    # Fetch all users who have interacted with the bot
    all_users = await bot.get_participants(-1001336746488)  # Replace with your group ID
    
    # Iterate through all users and send the broadcast message
    for user in all_users:
        try:
            await bot.send_message(user.id, broadcast_text)
        except Exception as e:
            print(f"Failed to send broadcast to user {user.id}: {e}")

    await m.reply("Broadcast sent successfully!")


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
    
    if db.sismember(PREMIUM_USERS_KEY, user_id):
        # Premium user
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
    else:
        # Free user
        reply_text = """
┏━━━━━━━━━━⍟
┃ 𝐅𝐑𝐄𝐄 𝐔𝐒𝐄𝐑 
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟ 
┃ As a free user, 
┃ you're not approved to access the full capabilities of this bot.
┃
┃ Upgrade to premium or utilize.
┃
┃ /cmds, or /help to view available cmds 
┃ /id or /info - To check your details
┃ /plan - To check availabe plan 
╚═════════════════⍟
For subscription inquiries, contact @abdul97233.
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


# Add premium user check for handling message
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
    user_id = m.sender_id
    if db.sismember(PREMIUM_USERS_KEY, user_id):
        asyncio.create_task(handle_message(m))


async def handle_message(m: Message):

    url = get_urls_from_string(m.text)
    if not url:
        return await m.reply("Please enter a valid url.")
    check_if = await is_user_on_chat(bot, "@NTMpro", m.peer_id)
    if not check_if:
        return await m.reply("Please join @NTMpro then send me the link again.")
    check_if = await is_user_on_chat(bot, "@NTMchat", m.peer_id)
    if not check_if:
        return await m.reply(
            "Please join @NTMchat then send me the link again."
        )
    
    is_spam = db.get(m.sender_id)
    if is_spam and m.sender_id not in [803003146]:
        if db.sismember(PREMIUM_USERS_KEY, m.sender_id):
            return await m.reply("You are spamming. Please wait 30 seconds and try again.")
        else:
            return await m.reply("You are spamming. Please wait 1 minute and try again.")
    else:
        hm = await m.reply("Sending you the media wait...")
        count = db.get(f"check_{m.sender_id}")
        if count and int(count) > 5:
            return await hm.edit("You are limited now. Please come back after 2 hours or use another account.")

    shorturl = extract_code_from_url(url)
    if not shorturl:
        return await hm.edit("Seems like your link is invalid.")
    fileid = db.get(shorturl)
    if fileid:
        try:
            await hm.delete()
        except:
            pass

        await bot(
            ForwardMessagesRequest(
                from_peer=PRIVATE_CHAT_ID,
                id=[int(fileid)],
                to_peer=m.chat.id,
                drop_author=True,
                # noforwards=True, #Uncomment it if you dont want to forward the media.
                background=True,
                drop_media_captions=False,
                with_my_score=True,
            )
        )
        db.set(m.sender_id, time.monotonic(), ex=60)
        db.set(
            f"check_{m.sender_id}",
            int(count) + 1 if count else 1,
            ex=7200,
        )

        return

    data = get_data(url)
    if not data:
        return await hm.edit("Sorry! API is dead or maybe your link is broken.")
    db.set(m.sender_id, time.monotonic(), ex=60)
    if (
        not data["file_name"].endswith(".mp4")
        and not data["file_name"].endswith(".mkv")
        and not data["file_name"].endswith(".Mkv")
        and not data["file_name"].endswith(".webm")
    ):
        return await hm.edit(
            f"Sorry! File is not supported for now. I can download only .mp4, .mkv and .webm files."
        )
    if int(data["sizebytes"]) > 524288000 and m.sender_id not in [803003146]:
        return await hm.edit(
            f"Sorry! File is too big. I can download only 500MB and this file is of {data['size']} ."
        )

    start_time = time.time()
    end_time = time.time()  # Record the end time
    total_time = end_time - start_time  # Calculate the total time taken
    user_first_name = m.sender.first_name
    user_username = m.sender.username
    cansend = CanSend()

    async def progress_bar(current_downloaded, total_downloaded, state="Sending"):

        if not cansend.can_send():
            return
        bar_length = 20
        percent = current_downloaded / total_downloaded
        arrow = "█" * int(percent * bar_length)
        spaces = "░" * (bar_length - len(arrow))

        elapsed_time = time.time() - start_time

        head_text = f"{state} `{data['file_name']}`"
        progress_bar = f"[{arrow + spaces}] {percent:.2%}"
        upload_speed = current_downloaded / elapsed_time if elapsed_time > 0 else 0
        speed_line = f"Speed: **{get_formatted_size(upload_speed)}/s**"

        time_remaining = (
            (total_downloaded - current_downloaded) / upload_speed
            if upload_speed > 0
            else 0
        )
        time_line = f"Time Remaining: `{convert_seconds(time_remaining)}`"

        size_line = f"Size: **{get_formatted_size(current_downloaded)}** / **{get_formatted_size(total_downloaded)}**"

        await hm.edit(
            f"{head_text}\n{progress_bar}\n{speed_line}\n{time_line}\n{size_line}",
            parse_mode="markdown",
        )

    uuid = str(uuid4())
    thumbnail = download_image_to_bytesio(data["thumb"], "thumbnail.png")

    try:
        file = await bot.send_file(
            PRIVATE_CHAT_ID,
            file=data["direct_link"],
            thumb=thumbnail if thumbnail else None,
            progress_callback=progress_bar,
            caption=f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{data["size"]}** 
╟➣𝗗𝗶𝗿𝗲𝗰𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗟𝗶𝗻𝗸 : [Click here]({data['direct_link']})
╟➣𝗙𝗶𝗿𝘀𝘁 𝗡𝗮𝗺𝗲: {user_first_name}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: {user_username}
╟➣𝐓𝐨𝐭𝐚𝐥 𝐓𝐢𝐦𝐞 𝐓𝐚𝐤𝐞𝐧: {total_time} sec
╚═════════════════⍟
         @NTMpro
""",
            supports_streaming=True,
            spoiler=True,
        )

        # pm2 start python3 --name "terabox" -- main.py
    except telethon.errors.rpcerrorlist.WebpageCurlFailedError:
        download = await download_file(
            data["direct_link"], data["file_name"], progress_bar
        )
        if not download:
            return await hm.edit(
                f"Sorry! Download Failed but you can download it from [here]({data['direct_link']}).",
                parse_mode="markdown",
            )
        file = await bot.send_file(
            PRIVATE_CHAT_ID,
            download,
            caption=f"""
┏━━━━━━━━━━⍟
┃ 𝐍𝐓𝐌 𝐓𝐞𝐫𝐚 𝐁𝐨𝐱 𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫 𝐁𝐨𝐭
┗━━━━━━━━━━━━━━━━━⍟
╔══════════⍟
╟➣𝙁𝙞𝙡𝙚 𝙉𝙖𝙢𝙚: `{data['file_name']}`
╟➣𝙎𝙞𝙯𝙚: **{data["size"]}** 
╟➣𝗗𝗶𝗿𝗲𝗰𝘁 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗟𝗶𝗻𝗸 : [Click here]({data['direct_link']})
╟➣𝗙𝗶𝗿𝘀𝘁 𝗡𝗮𝗺𝗲: {user_first_name}
╟➣𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲: {user_username}
╟➣𝐓𝐨𝐭𝐚𝐥 𝐓𝐢𝐦𝐞 𝐓𝐚𝐤𝐞𝐧: {total_time} sec
╚═════════════════⍟
         @NTMpro

""",
            progress_callback=progress_bar,
            thumb=thumbnail if thumbnail else None,
            supports_streaming=True,
            spoiler=True,
        )
        try:
            os.unlink(download)
        except Exception as e:
            print(e)
    except Exception:
        return await hm.edit(
            f"Sorry! Download Failed but you can download it from [here]({data['direct_link']}).",
            
        )
    try:
        os.unlink(download)
    except Exception as e:
        pass
    try:
        await hm.delete()
    except Exception as e:
        print(e)

    if shorturl:
        db.set(shorturl, file.id)
    if file:
        db.set(uuid, file.id)

        await bot(
            ForwardMessagesRequest(
                from_peer=PRIVATE_CHAT_ID,
                id=[file.id],
                to_peer=m.chat.id,
                top_msg_id=m.id,
                drop_author=True,
                # noforwards=True,  #Uncomment it if you dont want to forward the media.
                background=True,
                drop_media_captions=False,
                with_my_score=True,
            )
        )
        db.set(m.sender_id, time.monotonic(), ex=60)
        db.set(
            f"check_{m.sender_id}",
            int(count) + 1 if count else 1,
            ex=7200,
        )


bot.start(bot_token=BOT_TOKEN)
bot.run_until_disconnected()
