import re
from typing import Optional
from aiogram.types import Message, Sticker
from config import settings


def generate_pack_short_name(pack_name: str, user_id: int) -> str:
    """
    Generate a unique short name for the sticker pack
    Format: cleaned_pack_name_userID_by_botusername
    """
    # Clean pack name: remove special characters, convert to lowercase
    cleaned_name = re.sub(r'[^a-zA-Z0-9_]', '_', pack_name.lower())
    
    # Remove multiple underscores and strip
    cleaned_name = re.sub(r'_+', '_', cleaned_name).strip('_')
    
    # Limit length to avoid Telegram limits
    if len(cleaned_name) > 20:
        cleaned_name = cleaned_name[:20]
    
    # Generate unique short name
    short_name = f"{cleaned_name}_{user_id}_by_{settings.BOT_USERNAME}"
    
    return short_name


def generate_pack_link(pack_short_name: str) -> str:
    """Generate Telegram sticker pack link"""
    return f"https://t.me/addstickers/{pack_short_name}"


def is_sticker_supported(sticker: Sticker) -> bool:
    """Check if sticker type is supported (static image, video, or animated)"""
    # Now we support all three types: static, video, and animated
    return True  # Support all sticker types


def extract_sticker_from_message(message: Message) -> Optional[Sticker]:
    """Extract sticker from message if it's a reply to sticker"""
    if not message.reply_to_message:
        return None
    
    reply_message = message.reply_to_message
    
    # Check if replied message contains a sticker
    if reply_message.sticker:
        return reply_message.sticker
    
    return None


def is_private_chat(message: Message) -> bool:
    """Check if message is from private chat"""
    return message.chat.type == "private"


def is_group_chat(message: Message) -> bool:
    """Check if message is from group or supergroup"""
    return message.chat.type in ["group", "supergroup"]


def validate_pack_name(pack_name: str) -> tuple[bool, str]:
    """
    Validate sticker pack name
    Returns: (is_valid, error_message)
    """
    if not pack_name:
        return False, "Pack name cannot be empty"
    
    if len(pack_name.strip()) < 1:
        return False, "Pack name cannot be empty"
    
    if len(pack_name) > 64:
        return False, "Pack name is too long (max 64 characters)"
    
    # Check for valid characters (allow unicode for international names)
    if not re.match(r'^[a-zA-Z0-9\s\u00C0-\u017F\u0400-\u04FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]+$', pack_name):
        return False, "Pack name contains invalid characters"
    
    return True, ""


def format_pack_creation_message(pack_name: str, pack_link: str) -> str:
    """Format the pack creation success message"""
    return (
        f"✅ Pack created: **{pack_name}**\n\n"
        f"🔗 [View Pack]({pack_link})\n\n"
        f"{settings.PACK_CREATED_MESSAGE}"
    )


def format_sticker_added_message(pack_name: str, pack_link: str) -> str:
    """Format the sticker added success message"""
    return (
        f"✅ Sticker added to **{pack_name}**\n\n"
        f"🔗 [View Pack]({pack_link})"
    )
