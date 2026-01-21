import os
import base64
import logging
from random import choice
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.utils import get_display_name
from telethon.errors import ChatAdminRequiredError, ChatSendStickersForbiddenError, ChatWriteForbiddenError

logger = logging.getLogger(__name__)

# Available background colors
COLOR_MAP = {
    "red": "#d63031",
    "blue": "#74b9ff",
    "green": "#00b894",
    "purple": "#6c5ce7",
    "pink": "#fd79a8",
    "orange": "#e17055",
    "yellow": "#fdcb6e",
    "cyan": "#81ecec",
    "black": "#0d1117",
    "white": "#ffffff",
    "dark": "#1b1429",
    "grey": "#2f3640",
    "brown": "#8B4513"
}


class QuotlyTelethon:
    _API = "https://bot.lyo.su/quote/generate"
    _entities = {
        types.MessageEntityPhone: "phone_number",
        types.MessageEntityMention: "mention",
        types.MessageEntityBold: "bold",
        types.MessageEntityCashtag: "cashtag",
        types.MessageEntityStrike: "strikethrough",
        types.MessageEntityHashtag: "hashtag",
        types.MessageEntityEmail: "email",
        types.MessageEntityMentionName: "text_mention",
        types.MessageEntityUnderline: "underline",
        types.MessageEntityUrl: "url",
        types.MessageEntityTextUrl: "text_link",
        types.MessageEntityBotCommand: "bot_command",
        types.MessageEntityCode: "code",
        types.MessageEntityPre: "pre",
    }

    async def _format_quote(self, event, reply=None, sender=None, type_="private"):
        async def telegraph(file_):
            import aiohttp
            from PIL import Image

            file = file_ + ".png"
            Image.open(file_).save(file, "PNG")
            files = {"file": open(file, "rb").read()}

            async with aiohttp.ClientSession() as session:
                async with session.post("https://telegra.ph/upload", data=files) as resp:
                    result = await resp.json()
                    uri = "https://telegra.ph" + result[0]["src"]

            os.remove(file)
            os.remove(file_)
            return uri

        reply_data = {}
        if reply:
            try:
                reply_sender = await reply.get_sender()
                reply_data = {
                    "name": get_display_name(reply_sender) or "Deleted Account",
                    "text": reply.raw_text,
                    "chatId": reply.chat_id,
                }
            except (ChatAdminRequiredError, Exception) as e:
                logger.warning(f"Could not get reply sender: {e}")
                reply_data = {
                    "name": "User",
                    "text": reply.raw_text,
                    "chatId": reply.chat_id,
                }

        is_fwd = event.fwd_from
        name, last_name = None, None

        if sender:
            id_ = sender.id
            name = get_display_name(sender)
        elif not is_fwd:
            id_ = event.sender_id
            try:
                sender = await event.get_sender()
                name = get_display_name(sender)
            except (ChatAdminRequiredError, Exception) as e:
                logger.warning(f"Could not get event sender: {e}")
                name = "User"
                sender = None
        else:
            id_, sender = None, None
            name = is_fwd.from_name
            if is_fwd.from_id:
                id_ = is_fwd.from_id.user_id if hasattr(is_fwd.from_id, 'user_id') else is_fwd.from_id
                try:
                    sender = await event.client.get_entity(id_)
                    name = get_display_name(sender)
                except (ValueError, ChatAdminRequiredError, Exception) as e:
                    logger.warning(f"Could not get forwarded sender: {e}")
                    pass

        if sender and hasattr(sender, "last_name"):
            last_name = sender.last_name

        entities = []
        if event.entities:
            for entity in event.entities:
                entity_type = type(entity)
                if entity_type in self._entities:
                    entity_dict = {
                        "type": self._entities[entity_type],
                        **{k: v for k, v in entity.to_dict().items() if k != "_"},
                    }
                    entities.append(entity_dict)

        message = {
            "entities": entities,
            "chatId": id_,
            "avatar": True,
            "from": {
                "id": id_,
                "first_name": (name or (sender.first_name if sender else None)) or "Deleted Account",
                "last_name": last_name,
                "username": sender.username if sender else None,
                "language_code": "en",
                "title": name,
                "name": name or "Unknown",
                "type": type_,
            },
            "text": event.raw_text,
            "replyMessage": reply_data,
        }

        if event.document and event.document.thumbs:
            try:
                file_ = await event.download_media(thumb=-1)
                uri = await telegraph(file_)
                message["media"] = {"url": uri}
            except Exception as e:
                logger.warning(f"Could not download media: {e}")

        return message

    async def create_quotly(self, event, bg=None, reply=None, sender=None, file_name="quote.webp"):
        if not isinstance(event, list):
            event = [event]

        url = self._API
        bg = bg or "#2a1f3d"

        content = {
            "type": "quote",
            "format": "webp",
            "backgroundColor": bg,
            "width": 512,
            "height": 768,
            "scale": 2,
            "messages": [
                await self._format_quote(message, reply=reply, sender=sender)
                for message in event
            ],
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=content) as response:
                    request = await response.json()
        except Exception as er:
            logger.error(f"API Error: {er}")
            raise er

        if request.get("ok"):
            with open(file_name, "wb") as file:
                image = base64.decodebytes(request["result"]["image"].encode("utf-8"))
                file.write(image)
            return file_name
        raise Exception(str(request))


# Global instance
quotly = QuotlyTelethon()


async def setup_telethon_handlers(client):
    """Setup telethon event handlers for /q command"""

    @client.on(events.NewMessage(pattern=r'^/q(?: |$)(.*)'))
    async def quott_(event):
        try:
            match = event.pattern_match.group(1).strip()
            if not event.is_reply:
                return await event.reply("<b>Please reply to a message to create a quote.</b>", parse_mode='html')

            msg = await event.reply("⏳ <b>Creating quote, please wait...</b>", parse_mode='html')
            reply = await event.get_reply_message()
            replied_to, reply_ = None, None

            if match:
                spli_ = match.split(maxsplit=1)
                if (spli_[0] in ["r", "reply"]) or (
                    spli_[0].isdigit() and int(spli_[0]) in range(1, 21)
                ):
                    if spli_[0].isdigit():
                        if not event.client.is_bot:
                            reply_ = await event.client.get_messages(
                                event.chat_id,
                                min_id=event.reply_to_msg_id - 1,
                                reverse=True,
                                limit=int(spli_[0]),
                            )
                        else:
                            id_ = reply.id
                            reply_ = []
                            for msg_ in range(id_, id_ + int(spli_[0])):
                                msh = await event.client.get_messages(event.chat_id, ids=msg_)
                                if msh:
                                    reply_.append(msh)
                    else:
                        try:
                            replied_to = await reply.get_reply_message()
                        except (ChatAdminRequiredError, Exception) as e:
                            logger.warning(f"Could not get reply message: {e}")
                    try:
                        match = spli_[1]
                    except IndexError:
                        match = None

            user = None

            if not reply_:
                reply_ = reply

            if match:
                match = match.split(maxsplit=1)

            if match:
                if match[0].startswith("@") or match[0].isdigit():
                    try:
                        match_ = await event.client.parse_id(match[0])
                        user = await event.client.get_entity(match_)
                    except (ValueError, ChatAdminRequiredError, Exception) as e:
                        logger.warning(f"Could not get user entity: {e}")
                        pass
                    match = match[1] if len(match) == 2 else None
                else:
                    match = match[0]

            if match == "random":
                match = choice(list(COLOR_MAP.values()))

            # Handle color mapping
            bg_color = "#2a1f3d"
            if match and match in COLOR_MAP:
                bg_color = COLOR_MAP[match]
            elif match and match.startswith("#"):
                bg_color = match

            try:
                file = await quotly.create_quotly(
                    reply_, bg=bg_color, reply=replied_to, sender=user
                )
            except Exception as er:
                error_msg = (
                    "<b>Oops! Couldn't send the quote.</b>\n\n"
                    "If the problem continues, kindly report it here: <a href='https://t.me/Samuraissupportchat'>Support Group</a>"
                )
                await msg.edit(error_msg, parse_mode='html')
                logger.error(f"Quote creation error: {er}")
                return

            try:
                message = await reply.reply("", file=file)
                os.remove(file)
                await msg.delete()
                return message
                
            except ChatSendStickersForbiddenError:
                os.remove(file)
                error_msg = (
                    "<b>If the problem continues, kindly report it here: <a href='https://t.me/Samuraissupportchat'>Support Group</a></b>"
                )
                await msg.edit(error_msg, parse_mode='html')
                logger.warning(f"Stickers forbidden in chat {event.chat_id}")
                
            except ChatWriteForbiddenError:
                os.remove(file)
                error_msg = (
                    "<b>I need admin rights to complete this. Kindly promote me and try again.</b>"
                )
                await msg.edit(error_msg, parse_mode='html')
                logger.warning(f"Write forbidden in chat {event.chat_id}")
                
            except ChatAdminRequiredError:
                os.remove(file)
                error_msg = (
                    "<b>I need admin rights to complete this. Kindly promote me and try again.</b>"
                )
                await msg.edit(error_msg, parse_mode='html')
                logger.warning(f"Admin required in chat {event.chat_id}")
                
            except Exception as e:
                if os.path.exists(file):
                    os.remove(file)
                error_msg = (
                    "<b>Oops! Couldn't send the quote.</b>\n\n"
                    "If the problem continues, kindly report it here: <a href='https://t.me/Samuraissupportchat'>Support Group</a>"
                )
                await msg.edit(error_msg, parse_mode='html')
                logger.error(f"Unexpected error in quott_: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"Unhandled exception in quott_: {e}", exc_info=True)
            try:
                error_msg = (
                    "<b>Oops! Couldn't send the quote.</b>\n\n"
                    "If the problem continues, kindly report it here: <a href='https://t.me/Samuraissupportchat'>Support Group</a>"
                )
                await event.reply(error_msg, parse_mode='html')
            except:
                pass
