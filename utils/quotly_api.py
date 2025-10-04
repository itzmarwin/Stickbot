import base64
import logging
import aiohttp
from typing import List, Dict, Optional
from aiogram.types import Message
from aiogram import Bot

logger = logging.getLogger(__name__)

class QuotlyAPI:
    """
    API client for lyo.su quote generation service
    Creates Telegram-style quote stickers
    """
    
    API_URL = "https://bot.lyo.su/quote/generate"
    
    # Telegram entity types mapping
    ENTITIES = {
        "bold": "bold",
        "italic": "italic",
        "underline": "underline",
        "strikethrough": "strikethrough",
        "spoiler": "spoiler",
        "code": "code",
        "pre": "pre",
        "text_link": "text_link",
        "text_mention": "text_mention",
        "url": "url",
        "mention": "mention",
        "hashtag": "hashtag",
        "cashtag": "cashtag",
        "bot_command": "bot_command",
        "email": "email",
        "phone_number": "phone_number",
    }
    
    async def format_message(self, message: Message, bot: Bot, replied_to: Message = None) -> Optional[Dict]:
        """
        Format aiogram Message to lyo.su API format
        
        Args:
            message: Aiogram Message object
            bot: Bot instance
            replied_to: Message being replied to (for reply context)
            
        Returns:
            Dictionary in API format or None
        """
        try:
            user = message.from_user
            
            # Get user info
            user_id = user.id
            first_name = user.first_name or "Deleted Account"
            last_name = user.last_name or ""
            username = user.username
            
            # Create display name (first_name + last_name if available)
            display_name = first_name
            if last_name:
                display_name = f"{first_name} {last_name}"
            
            # Get message text
            text = message.text or message.caption or ""
            
            # Format entities
            entities = []
            if message.entities:
                for entity in message.entities:
                    entity_type = entity.type
                    if entity_type in self.ENTITIES:
                        entity_dict = {
                            "type": self.ENTITIES[entity_type],
                            "offset": entity.offset,
                            "length": entity.length
                        }
                        
                        # Add URL for text links
                        if entity_type == "text_link" and hasattr(entity, 'url'):
                            entity_dict["url"] = entity.url
                        
                        # Add user for text mentions
                        if entity_type == "text_mention" and hasattr(entity, 'user'):
                            entity_dict["user"] = {
                                "id": entity.user.id,
                                "first_name": entity.user.first_name or "User"
                            }
                        
                        entities.append(entity_dict)
            
            # Handle reply context - FIXED FOR LYOSU API
            reply_message = {}
            if replied_to:
                reply_user = replied_to.from_user
                reply_text = replied_to.text or replied_to.caption or ""
                
                # Get reply user display name
                reply_display_name = "Deleted Account"
                if reply_user:
                    reply_first_name = reply_user.first_name or "Deleted Account"
                    reply_last_name = reply_user.last_name or ""
                    reply_display_name = reply_first_name
                    if reply_last_name:
                        reply_display_name = f"{reply_first_name} {reply_last_name}"
                
                # Format reply message exactly as lyo.su API expects
                reply_message = {
                    "name": reply_display_name,
                    "text": reply_text,
                    "chatId": replied_to.chat.id
                }
                
                logger.info(f"Reply context added: {reply_display_name} - {reply_text[:30]}...")
            
            # Build message dict
            message_dict = {
                "entities": entities,
                "chatId": message.chat.id,
                "avatar": True,
                "from": {
                    "id": user_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "username": username,
                    "language_code": user.language_code or "en",
                    "title": display_name,  # Use display name for title
                    "name": display_name,   # Use display name for name
                    "type": "private" if message.chat.type == "private" else "group"
                },
                "text": text,
                "replyMessage": reply_message  # This will be empty dict if no reply
            }
            
            # Add media if available (photo)
            if message.photo:
                try:
                    # Get the largest photo
                    photo = message.photo[-1]
                    file = await bot.get_file(photo.file_id)
                    
                    # Get file URL
                    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
                    message_dict["media"] = {"url": file_url}
                except Exception as e:
                    logger.warning(f"Failed to add media: {e}")
            
            return message_dict
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}", exc_info=True)
            return None
    
    async def create_quote(
        self,
        messages: List[Dict],
        bg_color: str = "#1b1429",
        width: int = 512,
        height: int = 768,
        scale: int = 2
    ) -> Optional[bytes]:
        """
        Create quote sticker using lyo.su API
        
        Args:
            messages: List of formatted message dicts
            bg_color: Background color (hex)
            width: Image width
            height: Image height
            scale: Image scale
            
        Returns:
            WebP sticker bytes or None
        """
        try:
            # Prepare API request
            payload = {
                "type": "quote",
                "format": "webp",
                "backgroundColor": bg_color,
                "width": width,
                "height": height,
                "scale": scale,
                "messages": messages
            }
            
            logger.info(f"Sending request to lyo.su API with {len(messages)} messages")
            
            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        logger.error(f"API returned status {response.status}")
                        return None
                    
                    result = await response.json()
                    
                    if not result.get("ok"):
                        logger.error(f"API error: {result}")
                        return None
                    
                    # Decode base64 image
                    image_base64 = result["result"]["image"]
                    image_bytes = base64.b64decode(image_base64)
                    
                    logger.info("Successfully generated quote sticker")
                    return image_bytes
        
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating quote: {e}", exc_info=True)
            return None
