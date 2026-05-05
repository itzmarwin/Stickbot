import asyncio
import random
from pyrogram import Client, filters
from pyrogram.types import Message, LinkPreviewOptions
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, ChatAdminRequired

from pyrogram_handlers.utils import is_user_admin
from pyrogram_handlers.commands import cmd
from config import LOG_GROUP_ID

DELAY_BETWEEN_BATCHES = 2
MAX_RETRIES = 6
MAX_MESSAGE_LENGTH = 3900

EMOJI_POOL = [
    "🌚", "😶‍🌫️", "🥺", "💁", "😋", "😢", "😹", "👊", "🙋", "🤦",
    "🎮", "🎨", "🎯", "🚀", "⚡", "🔥", "💎", "🌟", "🎭", "🎪",
    "🌈", "🎵", "🍕", "🎸", "🌺", "🎬", "🏆", "🌊", "⚽", "🔮",
    "🌸", "🎲", "🎹", "🎤", "🎧", "🎼", "🎻", "🎺", "🥁", "🎷",
    "🌻", "🌷", "🌹", "🥀", "🏵️", "💐", "🌼", "🌴", "🌳", "🌲",
    "🍀", "🍁", "🍂", "🍃", "🎋", "🎍", "🌾", "🌿", "☘️", "🌱",
    "🍄", "🌰", "🦋", "🐝", "🐞", "🦗", "🕷️", "🦂", "🐢", "🐍",
    "🦎", "🦖", "🦕", "🐙", "🦑", "🦐", "🦞", "🦀", "🐡", "🐠",
    "🐟", "🐬", "🐳", "🐋", "🦈", "🐊", "🐅", "🐆", "🦓", "🦍",
    "🦧", "🐘", "🦛", "🦏", "🐪", "🐫", "🦒", "🦘", "🦬", "🐃",
    "🐂", "🐄", "🐎", "🐖", "🐏", "🐑", "🦙", "🐐", "🦌", "🐕",
]

active_tagall = {}


def get_batch_size(member_count: int) -> int:
    if member_count <= 1000:
        return 7
    elif member_count <= 2000:
        return 10
    elif member_count <= 5000:
        return 20
    else:
        return 30


async def is_bot_admin_in_chat(client: Client, chat_id: int) -> bool:
    try:
        bot = await client.get_me()
        member = await client.get_chat_member(chat_id, bot.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


async def get_all_members(client: Client, chat_id: int) -> list:
    members = []
    async for member in client.get_chat_members(chat_id):
        if not member.user.is_bot:
            members.append(member.user)
    return members

async def send_mention_batch(message_target, mentions: str, chat_id: int, retry_count: int = 0):
    if not active_tagall.get(chat_id, False):
        return False
    try:
        await message_target.reply_text(mentions)
        return True
    except FloodWait as e:
        if retry_count >= MAX_RETRIES:
            return False
        await asyncio.sleep(e.value + 1)
        if not active_tagall.get(chat_id, False):
            return False
        return await send_mention_batch(message_target, mentions, chat_id, retry_count + 1)


async def send_fresh_message(client: Client, chat_id: int, text: str, retry_count: int = 0):
    if not active_tagall.get(chat_id, False):
        return False
    try:
        await client.send_message(chat_id, text)
        return True
    except FloodWait as e:
        if retry_count >= MAX_RETRIES:
            return False
        await asyncio.sleep(e.value + 1)
        if not active_tagall.get(chat_id, False):
            return False
        return await send_fresh_message(client, chat_id, text, retry_count + 1)


async def send_tagall_log(client: Client, message: Message, command: str):
    if not LOG_GROUP_ID or LOG_GROUP_ID == 0:
        return

    try:
        chat = message.chat
        user = message.from_user

        try:
            invite_link = await client.export_chat_invite_link(chat.id)
        except Exception:
            invite_link = "None"

        admin_mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
        group_name = chat.title or "Unknown"

        log_text = (
            f"<b>#TagAll Log</b>\n\n"
            f"<b>Group:</b> {group_name}\n"
            f"<b>Group ID:</b> <code>{chat.id}</code>\n"
            f"<b>Admin:</b> {admin_mention}\n"
            f"<b>Command:</b> <code>{command}</code>\n"
            f"<b>Invite Link:</b> {invite_link}"
        )

        await client.send_message(LOG_GROUP_ID, log_text)

    except Exception:
        pass


async def setup_tagall_handlers(client: Client):

    @client.on_message(cmd(["tagall", "all"]) & filters.group)
    async def emoji_tagall_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗎𝗌𝖾 𝗍𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽.")
            return

        if chat_id in active_tagall and active_tagall[chat_id]:
            await message.reply_text(
                "𝖳𝖺𝗀𝖺𝗅𝗅 𝖺𝗅𝗋𝖾𝖺𝖽𝗒 𝗋𝗎𝗇𝗇𝗂𝗇𝗀!\n\n"
                "𝖴𝗌𝖾 /stop 𝗈𝗋 /cancel 𝗍𝗈 𝗌𝗍𝗈𝗉 𝗂𝗍."
            )
            return

        if not await is_bot_admin_in_chat(client, chat_id):
            await message.reply_text(
                "𝖨 𝗇𝖾𝖾𝖽 𝗍𝗈 𝖻𝖾 𝖺𝗇 𝖺𝖽𝗆𝗂𝗇 𝗍𝗈 𝗎𝗌𝖾 𝗍𝖺𝗀𝖺𝗅𝗅!\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗉𝗋𝗈𝗆𝗈𝗍𝖾 𝗆𝖾 𝖺𝗌 𝖺𝖽𝗆𝗂𝗇 𝖺𝗇𝖽 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
            )
            return

        is_reply = message.reply_to_message is not None
        has_text = len(message.text.split(maxsplit=1)) > 1

        if not is_reply and not has_text:
            await message.reply_text(
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗎𝗌𝖾 𝖾𝗆𝗈𝗃𝗂 𝗍𝖺𝗀𝖺𝗅𝗅 𝗉𝗋𝗈𝗉𝖾𝗋𝗅𝗒!\n\n"
                "𝖮𝗉𝗍𝗂𝗈𝗇 1: 𝖱𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗆𝖾𝗌𝗌𝖺𝗀𝖾 𝗐𝗂𝗍𝗁 /tagall\n"
                "𝖮𝗉𝗍𝗂𝗈𝗇 2: 𝖴𝗌𝖾 /tagall <𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾>\n\n"
                "𝖤𝗑𝖺𝗆𝗉𝗅𝖾: /tagall 𝖧𝖾𝗅𝗅𝗈 𝖾𝗏𝖾𝗋𝗒𝗈𝗇𝖾!"
            )
            return

        if not is_reply:
            command_parts = message.text.split(maxsplit=1)
            user_message = command_parts[1]
            if len(user_message) > MAX_MESSAGE_LENGTH:
                await message.reply_text(
                    f"𝖬𝖾𝗌𝗌𝖺𝗀𝖾 𝗍𝗈𝗈 𝗅𝗈𝗇𝗀!\n\n"
                    f"𝖸𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾: {len(user_message)} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n"
                    f"𝖬𝖺𝗑𝗂𝗆𝗎𝗆 𝖺𝗅𝗅𝗈𝗐𝖾𝖽: {MAX_MESSAGE_LENGTH} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n\n"
                    f"𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝗁𝗈𝗋𝗍𝖾𝗇 𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾."
                )
                return

        progress_msg = await message.reply_text("𝖥𝖾𝗍𝖼𝗁𝗂𝗇𝗀 𝗆𝖾𝗆𝖻𝖾𝗋𝗌...")
        members = await get_all_members(client, chat_id)

        if not members:
            await progress_msg.edit_text("𝖭𝗈 𝗆𝖾𝗆𝖻𝖾𝗋𝗌 𝖿𝗈𝗎𝗇𝖽!")
            return

        batch_size = get_batch_size(len(members))
        active_tagall[chat_id] = True
        await send_tagall_log(client, message, "/tagall")

        stopped_manually = False

        try:
            if is_reply:
                original_message = message.reply_to_message
                await progress_msg.delete()

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    random_emojis = random.sample(EMOJI_POOL, min(len(batch), len(EMOJI_POOL)))
                    mentions = " ".join([
                        f"[{random_emojis[idx]}](tg://user?id={user.id})"
                        for idx, user in enumerate(batch)
                    ])

                    result = await send_mention_batch(original_message, mentions, chat_id)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            else:
                command_text = message.text.split(maxsplit=1)
                header = command_text[1]
                await progress_msg.delete()

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    random_emojis = random.sample(EMOJI_POOL, min(len(batch), len(EMOJI_POOL)))
                    mentions = " ".join([
                        f"[{random_emojis[idx]}](tg://user?id={user.id})"
                        for idx, user in enumerate(batch)
                    ])
                    text = f"{header}\n\n{mentions}"

                    result = await send_fresh_message(client, chat_id, text)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        finally:
            active_tagall[chat_id] = False
            if not stopped_manually:
                await client.send_message(chat_id, "𝖳𝖺𝗀𝖺𝗅𝗅 𝖤𝗇𝖽𝖾𝖽")


    @client.on_message(cmd(["uall", "utagall", "utag"]) & filters.group)
    async def username_tagall_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗎𝗌𝖾 𝗍𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽.")
            return

        if chat_id in active_tagall and active_tagall[chat_id]:
            await message.reply_text(
                "𝖳𝖺𝗀𝖺𝗅𝗅 𝖺𝗅𝗋𝖾𝖺𝖽𝗒 𝗋𝗎𝗇𝗇𝗂𝗇𝗀!\n\n"
                "𝖴𝗌𝖾 /stop 𝗈𝗋 /cancel 𝗍𝗈 𝗌𝗍𝗈𝗉 𝗂𝗍."
            )
            return

        if not await is_bot_admin_in_chat(client, chat_id):
            await message.reply_text(
                "𝖨 𝗇𝖾𝖾𝖽 𝗍𝗈 𝖻𝖾 𝖺𝗇 𝖺𝖽𝗆𝗂𝗇 𝗍𝗈 𝗎𝗌𝖾 𝗍𝖺𝗀𝖺𝗅𝗅!\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗉𝗋𝗈𝗆𝗈𝗍𝖾 𝗆𝖾 𝖺𝗌 𝖺𝖽𝗆𝗂𝗇 𝖺𝗇𝖽 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
            )
            return

        is_reply = message.reply_to_message is not None
        has_text = len(message.text.split(maxsplit=1)) > 1

        if not is_reply and not has_text:
            await message.reply_text(
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗎𝗌𝖾 𝗎𝗌𝖾𝗋𝗇𝖺𝗆𝖾 𝗍𝖺𝗀𝖺𝗅𝗅 𝗉𝗋𝗈𝗉𝖾𝗋𝗅𝗒!\n\n"
                "𝖮𝗉𝗍𝗂𝗈𝗇 1: 𝖱𝖾𝗉𝗅𝗒 𝗍𝗈 𝖺 𝗆𝖾𝗌𝗌𝖺𝗀𝖾 𝗐𝗂𝗍𝗁 /utagall\n"
                "𝖮𝗉𝗍𝗂𝗈𝗇 2: 𝖴𝗌𝖾 /utagall <𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾>\n\n"
                "𝖤𝗑𝖺𝗆𝗉𝗅𝖾: /utagall 𝖧𝖾𝗅𝗅𝗈 𝖾𝗏𝖾𝗋𝗒𝗈𝗇𝖾!"
            )
            return

        if not is_reply:
            command_parts = message.text.split(maxsplit=1)
            user_message = command_parts[1]
            if len(user_message) > MAX_MESSAGE_LENGTH:
                await message.reply_text(
                    f"𝖬𝖾𝗌𝗌𝖺𝗀𝖾 𝗍𝗈𝗈 𝗅𝗈𝗇𝗀!\n\n"
                    f"𝖸𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾: {len(user_message)} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n"
                    f"𝖬𝖺𝗑𝗂𝗆𝗎𝗆 𝖺𝗅𝗅𝗈𝗐𝖾𝖽: {MAX_MESSAGE_LENGTH} 𝖼𝗁𝖺𝗋𝖺𝖼𝗍𝖾𝗋𝗌\n\n"
                    f"𝖯𝗅𝖾𝖺𝗌𝖾 𝗌𝗁𝗈𝗋𝗍𝖾𝗇 𝗒𝗈𝗎𝗋 𝗆𝖾𝗌𝗌𝖺𝗀𝖾."
                )
                return

        progress_msg = await message.reply_text("𝖥𝖾𝗍𝖼𝗁𝗂𝗇𝗀 𝗆𝖾𝗆𝖻𝖾𝗋𝗌...")
        members = await get_all_members(client, chat_id)

        if not members:
            await progress_msg.edit_text("𝖭𝗈 𝗆𝖾𝗆𝖻𝖾𝗋𝗌 𝖿𝗈𝗎𝗇𝖽!")
            return

        batch_size = get_batch_size(len(members))
        active_tagall[chat_id] = True
        await send_tagall_log(client, message, "/utagall")

        stopped_manually = False

        try:
            if is_reply:
                original_message = message.reply_to_message
                await progress_msg.delete()

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    mentions = ", ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])

                    result = await send_mention_batch(original_message, mentions, chat_id)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            else:
                command_text = message.text.split(maxsplit=1)
                header = command_text[1]
                await progress_msg.delete()

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    mentions = ", ".join([
                        f"[{user.first_name}](tg://user?id={user.id})"
                        for user in batch
                    ])
                    text = f"{header}\n\n{mentions}"

                    result = await send_fresh_message(client, chat_id, text)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        finally:
            active_tagall[chat_id] = False
            if not stopped_manually:
                await client.send_message(chat_id, "𝖳𝖺𝗀𝖺𝗅𝗅 𝖤𝗇𝖽𝖾𝖽")


    @client.on_message(cmd("call") & filters.group)
    async def call_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗎𝗌𝖾 𝗍𝗁𝗂𝗌 𝖼𝗈𝗆𝗆𝖺𝗇𝖽.")
            return

        if chat_id in active_tagall and active_tagall[chat_id]:
            await message.reply_text(
                "𝖳𝖺𝗀𝖺𝗅𝗅 𝖺𝗅𝗋𝖾𝖺𝖽𝗒 𝗋𝗎𝗇𝗇𝗂𝗇𝗀!\n\n"
                "𝖴𝗌𝖾 /stop 𝗈𝗋 /cancel 𝗍𝗈 𝗌𝗍𝗈𝗉 𝗂𝗍."
            )
            return

        if not await is_bot_admin_in_chat(client, chat_id):
            await message.reply_text(
                "𝖨 𝗇𝖾𝖾𝖽 𝗍𝗈 𝖻𝖾 𝖺𝗇 𝖺𝖽𝗆𝗂𝗇 𝗍𝗈 𝗎𝗌𝖾 𝗍𝖺𝗀𝖺𝗅𝗅!\n\n"
                "𝖯𝗅𝖾𝖺𝗌𝖾 𝗉𝗋𝗈𝗆𝗈𝗍𝖾 𝗆𝖾 𝖺𝗌 𝖺𝖽𝗆𝗂𝗇 𝖺𝗇𝖽 𝗍𝗋𝗒 𝖺𝗀𝖺𝗂𝗇."
            )
            return

        is_reply = message.reply_to_message is not None
        has_text = len(message.text.split(maxsplit=1)) > 1

        progress_msg = await message.reply_text("𝖥𝖾𝗍𝖼𝗁𝗂𝗇𝗀 𝗆𝖾𝗆𝖻𝖾𝗋𝗌...")
        members = await get_all_members(client, chat_id)

        if not members:
            await progress_msg.edit_text("𝖭𝗈 𝗆𝖾𝗆𝖻𝖾𝗋𝗌 𝖿𝗈𝗎𝗇𝖽!")
            return

        batch_size = get_batch_size(len(members))
        await progress_msg.delete()
        active_tagall[chat_id] = True
        await send_tagall_log(client, message, "/call")

        stopped_manually = False

        try:
            if is_reply:
                original_message = message.reply_to_message

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    random_emojis = random.sample(EMOJI_POOL, min(len(batch), len(EMOJI_POOL)))
                    mentions = " ".join([
                        f"[{random_emojis[idx]}](tg://user?id={user.id})"
                        for idx, user in enumerate(batch)
                    ])

                    result = await send_mention_batch(original_message, mentions, chat_id)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            elif has_text:
                header = message.text.split(maxsplit=1)[1]

                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    random_emojis = random.sample(EMOJI_POOL, min(len(batch), len(EMOJI_POOL)))
                    mentions = " ".join([
                        f"[{random_emojis[idx]}](tg://user?id={user.id})"
                        for idx, user in enumerate(batch)
                    ])
                    text = f"{header}\n\n{mentions}"

                    result = await send_fresh_message(client, chat_id, text)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            else:
                for i in range(0, len(members), batch_size):
                    if not active_tagall.get(chat_id, False):
                        stopped_manually = True
                        break

                    batch = members[i:i + batch_size]
                    random_emojis = random.sample(EMOJI_POOL, min(len(batch), len(EMOJI_POOL)))
                    mentions = " ".join([
                        f"[{random_emojis[idx]}](tg://user?id={user.id})"
                        for idx, user in enumerate(batch)
                    ])

                    result = await send_fresh_message(client, chat_id, mentions)
                    if not result:
                        if not active_tagall.get(chat_id, False):
                            stopped_manually = True
                            break

                    if i + batch_size < len(members):
                        await asyncio.sleep(DELAY_BETWEEN_BATCHES)

        finally:
            active_tagall[chat_id] = False
            if not stopped_manually:
                await client.send_message(chat_id, "𝖳𝖺𝗀𝖺𝗅𝗅 𝖤𝗇𝖽𝖾𝖽")


    @client.on_message(cmd(["stop", "cancel"]) & filters.group)
    async def stop_tagall_command(client: Client, message: Message):
        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user else None

        is_admin = await is_user_admin(client, chat_id, user_id)
        if not is_admin:
            await message.reply_text("𝖮𝗇𝗅𝗒 𝖺𝖽𝗆𝗂𝗇𝗌 𝖼𝖺𝗇 𝗌𝗍𝗈𝗉 𝗍𝖺𝗀𝖺𝗅𝗅.")
            return

        if chat_id not in active_tagall or not active_tagall[chat_id]:
            await message.reply_text("𝖭𝗈 𝖺𝖼𝗍𝗂𝗏𝖾 𝗍𝖺𝗀𝖺𝗅𝗅 𝗉𝗋𝗈𝖼𝖾𝗌𝗌.")
            return
            
        active_tagall[chat_id] = False
        await message.reply_text("𝖳𝖺𝗀𝖺𝗅𝗅 𝗌𝗍𝗈𝗉𝗉𝖾𝖽 𝗌𝗎𝖼𝖼𝖾𝗌𝗌𝖿𝗎𝗅𝗅𝗒!")
