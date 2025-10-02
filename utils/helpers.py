import re
from typing import Tuple
from config import MAX_PACK_NAME_LENGTH, BOT_USERNAME

def validate_pack_name(name: str) -> Tuple[bool, str]:
    """
    Validate sticker pack name
    Returns: (is_valid, error_message)
    """
    if not name or len(name.strip()) == 0:
        return False, "Pack name cannot be empty"
    
    name = name.strip()
    
    if len(name) > MAX_PACK_NAME_LENGTH:
        return False, "pack_name_too_long"
    
    # Allow letters, numbers, spaces, underscores, @, and common punctuation
    if not re.match(r'^[a-zA-Z0-9\s_@.!-]+$', name):
        return False, "pack_name_invalid"
    
    return True, ""

def generate_short_name(pack_name: str, user_id: int) -> str:
    """
    Generate unique short name for sticker pack
    Format: {cleaned_pack_name}_{user_id}_by_{bot_username}
    
    Telegram Requirements:
    - Must end with "_by_<bot_username>"
    - Can only contain: a-z, 0-9, and underscores
    - Must be 1-64 characters
    """
    # Clean pack name for short name (only lowercase letters and numbers)
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', pack_name.lower())
    
    # If empty after cleaning, use default
    if not cleaned:
        cleaned = "pack"
    
    # Limit length to avoid Telegram's limits
    if len(cleaned) > 15:
        cleaned = cleaned[:15]
    
    # Get bot username without @ and ensure it's lowercase
    bot_user = BOT_USERNAME.replace('@', '').lower()
    
    # Telegram requires the exact format: name_by_botusername
    short_name = f"{cleaned}_{user_id}_by_{bot_user}"
    
    # Ensure total length is under 64 characters
    if len(short_name) > 64:
        # Reduce cleaned name length
        max_cleaned_length = 64 - len(f"_{user_id}_by_{bot_user}")
        cleaned = cleaned[:max_cleaned_length]
        short_name = f"{cleaned}_{user_id}_by_{bot_user}"
    
    return short_name

def format_pack_name(user_provided_name: str) -> str:
    """
    Format pack name by appending bot username
    Format: {User Provided Name} ~ @BotUsername
    """
    return f"{user_provided_name.strip()} ~ @{BOT_USERNAME}"

def get_file_size_mb(file_size: int) -> float:
    """Convert bytes to MB"""
    return file_size / (1024 * 1024)
