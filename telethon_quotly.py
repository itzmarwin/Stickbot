import os
import base64
import logging
import asyncio
from random import choice
from telethon import TelegramClient, events
from telethon.tl import types
from telethon.utils import get_display_name

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
    # ✅ Multiple working APIs for redundancy
    _APIS = [
        "https://quote-api.botyaro.repl.co/generate",  # API 1
        "https://qoute-api-akash.koyeb.app/generate",  # API 2
        "https://quote.smnirv.me/generate",             # API 3
    ]
    
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
        """Format message data for quote API"""
        async def telegraph(file_):
            """Upload image to telegraph"""
            try:
                import aiohttp
                from PIL import Image
                file = file_ + ".png"
                Image.open(file_).save(file, "PNG")
                
                with open(file, "rb") as f:
                    files = {"file": f.read()}
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://telegra.ph/upload", 
                        data=files,
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as resp:
                        if resp.status != 200:
                            raise Exception(f"Telegraph upload failed: {resp.status}")
                        
                        result = await resp.json()
                        uri = "https://telegra.ph" + result[0]["src"]
                
                # Cleanup
                if os.path.exists(file):
                    os.remove(file)
                if os.path.exists(file_):
                    os.remove(file_)
                
                return uri
            except Exception as e:
                logger.error(f"Telegraph upload error: {e}")
                # Cleanup on error
                try:
                    if os.path.exists(file):
                        os.remove(file)
                    if os.path.exists(file_):
                        os.remove(file_)
                except:
                    pass
                return None

        reply_data = {}
        if reply:
            try:
                reply_sender = await reply.get_sender()
                reply_data = {
                    "name": get_display_name(reply_sender) or "Deleted Account",
                    "text": reply.raw_text or "",
                    "chatId": reply.chat_id,
                }
            except Exception as e:
                logger.error(f"Error getting reply data: {e}")

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
            except Exception as e:
                logger.error(f"Error getting sender: {e}")
                id_ = event.sender_id
                name = "User"
        else:
            id_, sender = None, None
            name = is_fwd.from_name
            if is_fwd.from_id:
                id_ = is_fwd.from_id.user_id if hasattr(is_fwd.from_id, 'user_id') else is_fwd.from_id
                try:
                    sender = await event.client.get_entity(id_)
                    name = get_display_name(sender)
                except (ValueError, Exception) as e:
                    logger.debug(f"Could not get forwarded sender: {e}")
        
        if sender and hasattr(sender, "last_name"):
            last_name = sender.last_name

        entities = []
        if event.entities:
            for entity in event.entities:
                try:
                    entity_type = type(entity)
                    if entity_type in self._entities:
                        entity_dict = {
                            "type": self._entities[entity_type],
                            **{k: v for k, v in entity.to_dict().items() if k != "_"},
                        }
                        entities.append(entity_dict)
                except Exception as e:
                    logger.debug(f"Error processing entity: {e}")

        message = {
            "entities": entities,
            "chatId": id_,
            "avatar": True,
            "from": {
                "id": id_,
                "first_name": (name or (sender.first_name if sender and hasattr(sender, 'first_name') else None)) or "User",
                "last_name": last_name,
                "username": sender.username if sender and hasattr(sender, 'username') else None,
                "language_code": "en",
                "title": name,
                "name": name or "Unknown",
                "type": type_,
            },
            "text": event.raw_text or "",
            "replyMessage": reply_data,
        }

        # ✅ Handle media with better error handling
        if event.document and event.document.thumbs:
            try:
                file_ = await event.download_media(thumb=-1)
                if file_:
                    uri = await telegraph(file_)
                    if uri:
                        message["media"] = {"url": uri}
            except Exception as e:
                logger.error(f"Error processing media: {e}")

        return message

    async def create_quotly(self, event, bg=None, reply=None, sender=None, file_name="quote.webp"):
        """
        Create quote sticker with multiple API fallback
        ✅ Tries all available APIs until one succeeds
        """
        if not isinstance(event, list):
            event = [event]
        
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
        
        # ✅ Try all APIs one by one
        for i, api_url in enumerate(self._APIS):
            logger.info(f"Trying API {i+1}/{len(self._APIS)}: {api_url}")
            result = await self._try_api(api_url, content, file_name)
            
            if result:
                return result
            
            # Wait a bit before trying next API
            if i < len(self._APIS) - 1:
                await asyncio.sleep(0.5)
        
        # ✅ All APIs failed
        raise Exception(
            "Unable to generate quote at the moment. Please try again in a few minutes."
        )
    
    async def _try_api(self, api_url: str, content: dict, file_name: str):
        """
        Try to generate quote using specific API
        Returns file_name on success, None on failure
        """
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json=content,
                    timeout=aiohttp.ClientTimeout(total=25),
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0'
                    }
                ) as response:
                    
                    # ✅ Check response status
                    if response.status != 200:
                        logger.warning(f"API returned status {response.status}")
                        return None
                    
                    # ✅ Check content type
                    content_type = response.headers.get('Content-Type', '').lower()
                    
                    if 'application/json' not in content_type:
                        logger.warning(f"API returned non-JSON: {content_type}")
                        return None
                    
                    # ✅ Parse JSON response
                    try:
                        request = await response.json()
                    except Exception as json_err:
                        logger.error(f"Failed to parse JSON: {json_err}")
                        return None
                    
                    # ✅ Check if API returned success
                    if not request.get("ok"):
                        error_msg = request.get("error", request.get("description", "Unknown error"))
                        logger.warning(f"API error: {error_msg}")
                        return None
                    
                    # ✅ Decode and save image
                    try:
                        image_data = request["result"]["image"]
                        decoded_image = base64.b64decode(image_data.encode("utf-8"))
                        
                        with open(file_name, "wb") as file:
                            file.write(decoded_image)
                        
                        logger.info(f"✅ Quote generated successfully using {api_url}")
                        return file_name
                        
                    except (KeyError, TypeError, ValueError) as e:
                        logger.error(f"Failed to decode image: {e}")
                        return None
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout: {api_url}")
            return None
            
        except aiohttp.ClientError as e:
            logger.warning(f"Connection error ({api_url}): {e}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error with API ({api_url}): {e}")
            return None

# Global instance
quotly = QuotlyTelethon()

async def setup_telethon_handlers(client):
    """Setup telethon event handlers for /q command"""
    
    @client.on(events.NewMessage(pattern='^/q(?: |$)(.*)'))
    async def quott_(event):
        """Handle /q command for creating quote stickers"""
        match = event.pattern_match.group(1).strip()
        
        # ✅ Check if reply
        if not event.is_reply:
            return await event.reply(
                "💬 <b>Quote Sticker</b>\n\n"
                "Reply to a message with <code>/q</code> to create a quote sticker.\n\n"
                "<b>Options:</b>\n"
                "• <code>/q</code> - Basic quote\n"
                "• <code>/q [color]</code> - With color (red, blue, green, etc.)\n"
                "• <code>/q [number]</code> - Quote multiple messages (1-20)\n"
                "• <code>/q r</code> - Include replied message\n"
                "• <code>/q random</code> - Random color",
                parse_mode='html'
            )

        msg = await event.reply("⏳ Creating quote, please wait...")
        reply = await event.get_reply_message()
        replied_to, reply_ = None, None

        # ✅ Parse command arguments
        try:
            if match:
                spli_ = match.split(maxsplit=1)
                
                # Check for reply or multiple messages
                if (spli_[0] in ["r", "reply"]) or (
                    spli_[0].isdigit() and int(spli_[0]) in range(1, 21)
                ):
                    if spli_[0].isdigit():
                        # Get multiple messages
                        try:
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
                        except Exception as e:
                            logger.error(f"Error getting multiple messages: {e}")
                            reply_ = reply
                    else:
                        # Include replied message
                        try:
                            replied_to = await reply.get_reply_message()
                        except Exception as e:
                            logger.debug(f"Could not get replied message: {e}")
                    
                    try:
                        match = spli_[1]
                    except IndexError:
                        match = None

            user = None

            if not reply_:
                reply_ = reply

            # ✅ Parse user mention or color
            if match:
                match = match.split(maxsplit=1)

            if match:
                if match[0].startswith("@") or match[0].isdigit():
                    try:
                        match_ = await event.client.parse_id(match[0])
                        user = await event.client.get_entity(match_)
                    except (ValueError, Exception) as e:
                        logger.debug(f"Could not parse user: {e}")
                    match = match[1] if len(match) == 2 else None
                else:
                    match = match[0]

            if match == "random":
                match = choice(list(COLOR_MAP.values()))

            # ✅ Handle color mapping
            bg_color = "#2a1f3d"
            if match and match in COLOR_MAP:
                bg_color = COLOR_MAP[match]
            elif match and match.startswith("#"):
                bg_color = match

            # ✅ Create quote with proper error handling
            try:
                file = await quotly.create_quotly(
                    reply_, bg=bg_color, reply=replied_to, sender=user
                )
            except Exception as er:
                error_message = str(er)
                
                # ✅ Simple error message without promoting other bots
                await msg.edit(
                    "❌ <b>Unable to create quote</b>\n\n"
                    "The quote service is temporarily unavailable. "
                    "Please try again in a few minutes.\n\n"
                    "If the issue persists, contact support.",
                    parse_mode='html'
                )
                logger.error(f"Quote generation failed: {error_message}")
                return

            # ✅ Send quote sticker
            try:
                message = await reply.reply("", file=file)
                await msg.delete()
                return message
                
            except Exception as e:
                logger.error(f"Error sending quote: {e}")
                await msg.edit(
                    "❌ <b>Failed to send quote</b>\n\n"
                    "Quote was created but couldn't be sent. Please try again.",
                    parse_mode='html'
                )
                
            finally:
                # ✅ Cleanup file
                if file and os.path.exists(file):
                    try:
                        os.remove(file)
                    except Exception as e:
                        logger.error(f"Error removing temp file: {e}")
                        
        except Exception as e:
            logger.error(f"Unexpected error in /q command: {e}", exc_info=True)
            try:
                await msg.edit(
                    "❌ <b>Something went wrong</b>\n\n"
                    "Please try again or contact support if the issue continues.",
                    parse_mode='html'
                )
            except:
                pass
    
    logger.info("✅ Telethon /q command handler setup complete")
