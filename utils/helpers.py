import re
import unicodedata
from typing import Tuple
from config import MAX_PACK_NAME_LENGTH, BOT_USERNAME

def validate_pack_name(name: str) -> Tuple[bool, str]:
    """
    Validate sticker pack name
    Returns: (is_valid, error_message)
    
    Accepts ALL Unicode characters including:
    - Fancy fonts (𝐟𝐨𝐫, 𝕞𝕠𝕣𝕖, etc.)
    - Special characters ([], {}, @, #, $, %, &, *, etc.)
    - Emojis (🎨, 😊, etc.)
    - Any Unicode text
    
    NO CHARACTER MODIFICATION - accepts exactly as user inputs!
    """
    if not name or len(name.strip()) == 0:
        return False, "Pack name cannot be empty"
    
    name = name.strip()
    
    # Only check length, accept ALL characters
    if len(name) > MAX_PACK_NAME_LENGTH:
        return False, "pack_name_too_long"
    
    return True, ""

def generate_short_name(pack_name: str, user_id: int) -> str:
    """
    Generate unique short name for sticker pack (INTERNAL USE ONLY)
    Format: {cleaned_pack_name}_{user_id}_by_{bot_username}
    
    IMPORTANT: This is ONLY for the internal short_name (Telegram requirement).
    The actual pack TITLE remains exactly as user provided with all Unicode!
    
    Telegram Requirements for short name (internal ID):
    - Must end with "_by_<bot_username>"
    - Can only contain: a-z, 0-9, and underscores
    - Must be 1-64 characters
    - Must start with a letter or number
    """
    # Normalize Unicode to extract ASCII equivalents for SHORT NAME only
    # This does NOT affect the pack title!
    normalized = unicodedata.normalize('NFKD', pack_name)
    
    # Extract only ASCII alphanumeric characters for short name
    cleaned = ''
    for char in normalized:
        if char.isalnum() and ord(char) < 128:
            cleaned += char.lower()
    
    # If nothing left after cleaning, use user_id based default
    if not cleaned or len(cleaned) == 0:
        cleaned = f"pack{str(user_id)[-6:]}"
    
    # Ensure it starts with alphanumeric
    if cleaned and not cleaned[0].isalnum():
        cleaned = 'p' + cleaned
    
    # Limit length
    if len(cleaned) > 20:
        cleaned = cleaned[:20]
    
    # Get bot username without @ and ensure it's lowercase
    bot_user = BOT_USERNAME.replace('@', '').lower()
    
    # Create short name
    short_name = f"{cleaned}_{user_id}_by_{bot_user}"
    
    # Ensure total length is under 64 characters
    if len(short_name) > 64:
        max_cleaned_length = 64 - len(f"_{user_id}_by_{bot_user}")
        if max_cleaned_length > 0:
            cleaned = cleaned[:max_cleaned_length]
            short_name = f"{cleaned}_{user_id}_by_{bot_user}"
        else:
            short_name = f"p{user_id}_by_{bot_user}"
    
    # Final validation
    pattern = r'^[a-z0-9_]+$'
    if not re.match(pattern, short_name):
        short_name = f"pack{user_id}_by_{bot_user}"
    
    return short_name

def format_pack_name(user_provided_name: str) -> str:
    """
    Format pack name by appending bot username
    Format: {User Provided Name} ~ @BotUsername
    
    CRITICAL: Accepts ALL Unicode characters - NO FILTERING, NO MODIFICATION!
    The user's input is preserved EXACTLY as they typed it.
    
    This is the VISIBLE pack title that users will see.
    """
    # Keep the name EXACTLY as user provided (with all Unicode characters)
    # No normalization, no filtering, no character replacement!
    return f"{user_provided_name.strip()} ~ @{BOT_USERNAME}"

def get_file_size_mb(file_size: int) -> float:
    """Convert bytes to MB"""
    return file_size / (1024 * 1024)
