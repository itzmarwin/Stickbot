from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus, ParseMode, ChatType
from pyrogram.errors import UsernameNotOccupied, PeerIdInvalid, UserNotParticipant

from utils.language import get_chat_lang_dict


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


async def _get_member_status(client: Client, chat_id: int, user_id: int, lang: dict) -> str:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return lang["info_status_admin"]
        return lang["info_status_member"]
    except UserNotParticipant:
        return lang["info_status_not_in_chat"]
    except Exception:
        return lang["info_status_not_in_chat"]


def _format_name(user, lang: dict) -> str:
    if not user.first_name and not user.last_name:
        return lang["info_deleted_account"]
    first = user.first_name or ""
    last  = user.last_name or ""
    return f"{first} {last}".strip()


def setup_info_handlers(client: Client):

    @client.on_message(filters.command("id") & (filters.group | filters.private))
    async def id_command(client: Client, message: Message):
        lang = await get_chat_lang_dict(message.chat.id)

        if message.reply_to_message:
            replied = message.reply_to_message

            if replied.sender_chat:
                sender = replied.sender_chat
                if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    if sender.id == message.chat.id:
                        await message.reply_text(
                            lang["id_anonymous_admin"].format(chat_id=message.chat.id),
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                    else:
                        await message.reply_text(
                            lang["id_channel"].format(chat_id=sender.id),
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                else:
                    if replied.forward_from_chat:
                        await message.reply_text(
                            lang["id_channel"].format(chat_id=replied.forward_from_chat.id),
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                    else:
                        await message.reply_text(
                            lang["id_anonymous_admin_private"],
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                return

            if replied.forward_from_chat:
                await message.reply_text(
                    lang["id_channel"].format(chat_id=replied.forward_from_chat.id),
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=message.id
                )
                return

            if replied.from_user:
                name = _format_name(replied.from_user, lang)
                await message.reply_text(
                    lang["id_user"].format(name=name, user_id=replied.from_user.id),
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=message.id
                )
                return

        parts = message.text.split(maxsplit=1)

        if len(parts) < 2:
            if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                await message.reply_text(
                    lang["id_self_group"].format(
                        user_id=message.from_user.id,
                        chat_id=message.chat.id
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=message.id
                )
            else:
                await message.reply_text(
                    lang["id_self"].format(user_id=message.from_user.id),
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=message.id
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
                            lang["id_chat"].format(chat_id=chat.id),
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                    except Exception:
                        await message.reply_text(
                            lang["id_not_found"],
                            parse_mode=ParseMode.HTML,
                            reply_to_message_id=message.id
                        )
                    return
            else:
                user = await client.get_users(target)

            name = _format_name(user, lang)
            await message.reply_text(
                lang["id_user"].format(name=name, user_id=user.id),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )

        except Exception:
            await message.reply_text(
                lang["id_user_not_found"],
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )


    @client.on_message(filters.command("info") & (filters.group | filters.private))
    async def info_command(client: Client, message: Message):
        lang = await get_chat_lang_dict(message.chat.id)
        user, sender_chat = await _get_user(client, message)

        if not user and not sender_chat:
            await message.reply_text(
                lang["id_user_not_found"],
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )
            return

        if sender_chat:
            await message.reply_text(
                lang["info_chat"].format(
                    name=sender_chat.title,
                    chat_id=sender_chat.id
                ),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )
            return

        name     = _format_name(user, lang)
        username = f"@{user.username}" if user.username else "None"
        user_id  = user.id

        is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

        if is_group:
            status = await _get_member_status(client, message.chat.id, user_id, lang)
            await message.reply_text(
                lang["info_user_group"].format(
                    name=name,
                    username=username,
                    user_id=user_id,
                    status=status
                ),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )
        else:
            await message.reply_text(
                lang["info_user_private"].format(
                    name=name,
                    username=username,
                    user_id=user_id
                ),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id
            )
