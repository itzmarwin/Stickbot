from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus, ParseMode, ChatType
from pyrogram.errors import UsernameNotOccupied, PeerIdInvalid, UserNotParticipant


async def _get_user(client: Client, message: Message):
    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.from_user:
            return replied.from_user, None
        if replied.sender_chat:
            return None, replied.sender_chat
        return None, None

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return message.from_user, None

    target = parts[1].strip()

    try:
        if target.startswith("@"):
            user = await client.get_users(target)
        elif target.lstrip("-").isdigit():
            user = await client.get_users(int(target))
        else:
            user = await client.get_users(target)
        return user, None
    except (UsernameNotOccupied, PeerIdInvalid, Exception):
        return None, None


async def _get_member_status(client: Client, chat_id: int, user_id: int) -> str:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return "Administrator"
        return "Member"
    except UserNotParticipant:
        return "Not in this chat"
    except Exception:
        return "Not in this chat"


def _format_name(user) -> str:
    if not user.first_name and not user.last_name:
        return "Deleted Account"
    first  = user.first_name or ""
    last   = user.last_name or ""
    return f"{first} {last}".strip()


def setup_info_handlers(client: Client):

    @client.on_message(filters.command("id") & (filters.group | filters.private))
    async def id_command(client: Client, message: Message):
        if message.reply_to_message:
            replied = message.reply_to_message

            if replied.sender_chat:
                sender = replied.sender_chat
                if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    if sender.id == message.chat.id:
                        await message.reply_text(
                            f"This message was sent by an anonymous admin.\n"
                            f"Chat ID: <code>{message.chat.id}</code>",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await message.reply_text(
                            f"Channel ID: <code>{sender.id}</code>",
                            parse_mode=ParseMode.HTML
                        )
                else:
                    if replied.forward_from_chat:
                        await message.reply_text(
                            f"Channel ID: <code>{replied.forward_from_chat.id}</code>",
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await message.reply_text(
                            "This message was sent by an anonymous admin.",
                            parse_mode=ParseMode.HTML
                        )
                return

            if replied.forward_from_chat:
                await message.reply_text(
                    f"Channel ID: <code>{replied.forward_from_chat.id}</code>",
                    parse_mode=ParseMode.HTML
                )
                return

            if replied.from_user:
                await message.reply_text(
                    f"User ID: <code>{replied.from_user.id}</code>",
                    parse_mode=ParseMode.HTML
                )
                return

        parts = message.text.split(maxsplit=1)

        if len(parts) < 2:
            if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                await message.reply_text(
                    f"User ID: <code>{message.from_user.id}</code>\n"
                    f"Chat ID: <code>{message.chat.id}</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await message.reply_text(
                    f"User ID: <code>{message.from_user.id}</code>",
                    parse_mode=ParseMode.HTML
                )
            return

        target = parts[1].strip()

        try:
            if target.startswith("@"):
                user = await client.get_users(target)
            elif target.lstrip("-").isdigit():
                try:
                    user = await client.get_users(int(target))
                except Exception:
                    try:
                        chat = await client.get_chat(int(target))
                        await message.reply_text(
                            f"Chat ID: <code>{chat.id}</code>",
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        await message.reply_text("Could not find this ID.", parse_mode=ParseMode.HTML)
                    return
            else:
                user = await client.get_users(target)

            await message.reply_text(
                f"User ID: <code>{user.id}</code>",
                parse_mode=ParseMode.HTML
            )

        except Exception:
            await message.reply_text("User not found.", parse_mode=ParseMode.HTML)


    @client.on_message(filters.command("info") & (filters.group | filters.private))
    async def info_command(client: Client, message: Message):
        user, sender_chat = await _get_user(client, message)

        if not user and not sender_chat:
            await message.reply_text("User not found.", parse_mode=ParseMode.HTML)
            return

        if sender_chat:
            await message.reply_text(
                f"<b>Chat Information</b>\n\n"
                f"<b>Name:</b> {sender_chat.title}\n"
                f"<b>ID:</b> <code>{sender_chat.id}</code>",
                parse_mode=ParseMode.HTML
            )
            return

        name     = _format_name(user)
        username = f"@{user.username}" if user.username else "None"
        user_id  = user.id

        is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

        if is_group:
            status = await _get_member_status(client, message.chat.id, user_id)
            await message.reply_text(
                f"<b>User Information</b>\n\n"
                f"<b>Name:</b> {name}\n"
                f"<b>Username:</b> {username}\n"
                f"<b>User ID:</b> <code>{user_id}</code>\n"
                f"<b>Status:</b> {status}",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(
                f"<b>User Information</b>\n\n"
                f"<b>Name:</b> {name}\n"
                f"<b>Username:</b> {username}\n"
                f"<b>User ID:</b> <code>{user_id}</code>",
                parse_mode=ParseMode.HTML
            )
