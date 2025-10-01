import re
from typing import Optional
from aiogram.types import Message, Sticker
from config import settings


def generate_pack_short_name(pack_name: str, user_id: int) -> str:
    """
    FAST Generate a unique short name for the sticker pack
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


def extract_gif_from_message(message: Message) -> Optional[any]:
    """Extract GIF from message if it's a reply to GIF"""
    if not message.reply_to_message:
        return None
    
    reply_message = message.reply_to_message
    
    # Check if replied message contains a GIF (animation)
    if reply_message.animation:
        return reply_message.animation
    
    # Check if it's a document that might be a GIF
    if reply_message.document and reply_message.document.mime_type == "image/gif":
        return reply_message.document
    
    return None


def create_pack_link_keyboard(pack_link: str) -> any:
    """Create simple inline keyboard with pack link button only"""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 VIEW PACK", url=pack_link)]
    ])
    
    return keyboard


def format_sticker_success_message(pack_link: str, emoji: str = "🔥") -> tuple:
    """
    UNIFIED success message for both stickers and GIFs
    Returns: (message_text, keyboard)
    """
    message_text = f"Your sticker has been added!\nEmoji Is : {emoji}"
    keyboard = create_pack_link_keyboard(pack_link)
    
    return message_text, keyboard


# Aliases for backward compatibility - use the unified function above
def format_pack_creation_message_with_button(pack_link: str, emoji: str = "🔥") -> tuple:
    """Alias for format_sticker_success_message"""
    return format_sticker_success_message(pack_link, emoji)


def format_sticker_added_message_with_button(pack_link: str, emoji: str = "🔥") -> tuple:
    """Alias for format_sticker_success_message"""
    return format_sticker_success_message(pack_link, emoji)


# Remove legacy functions to avoid confusion - they are not used in the optimized code
# def format_pack_creation_message(pack_name: str, pack_link: str) -> str:
#     """Legacy function - NOT USED in optimized version"""
#     return (
#         f"✅ Pack created: **{pack_name}**\n\n"
#         f"🔗 [View Pack]({pack_link})\n\n"
#         f"{settings.PACK_CREATED_MESSAGE}"
#     )


# def format_sticker_added_message(pack_name: str, pack_link: str) -> str:
#     """Legacy function - NOT USED in optimized version"""
#     return (
#         f"✅ Sticker added to **{pack_name}**\n\n"
#         f"🔗 [View Pack]({pack_link})"
#     )


# def format_gif_conversion_message(pack_name: str, pack_link: str) -> str:
#     """Legacy function - NOT USED in optimized version"""
#     return (
#         f"✅ GIF converted to video sticker and added to **{pack_name}**\n\n"
#         f"🔗 [View Pack]({pack_link})"
#     )
