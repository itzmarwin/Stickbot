import re
import unicodedata
import time
import random
from typing import Tuple
from config import MAX_PACK_NAME_LENGTH, BOT_USERNAME

def validate_pack_name(name: str) -> Tuple[bool, str]:
    """
    Validate sticker pack name with security checks
    Returns: (is_valid, error_message)
    """
    if not name or len(name.strip()) == 0:
        return False, "Pack name cannot be empty"

    name = name.strip()

    # Check length
    if len(name) > MAX_PACK_NAME_LENGTH:
        return False, "pack_name_too_long"

    # Security: Check for potentially dangerous patterns
    dangerous_patterns = ['../', './', '/..', '\\', '//', '<script', 'javascript:', 'vbscript:']
    if any(pattern in name.lower() for pattern in dangerous_patterns):
        return False, "Invalid characters in pack name"

    # Check for excessive special characters (potential spam)
    special_char_count = len(re.findall(r'[^\w\s]', name))
    if special_char_count > 15:  # Allow reasonable special chars but prevent spam
        return False, "Too many special characters"

    # Check for excessive repeated characters (potential spam)
    if re.search(r'(.)\1{10,}', name):  # 10+ repeated characters
        return False, "Invalid pack name pattern"

    return True, ""

def generate_short_name(pack_name: str, user_id: int) -> str:
    """
    Generate UNIQUE short name for sticker pack with timestamp
    Format: {cleaned_name}_{timestamp}_{user_id}_by_{bot}

    This ensures EVERY pack gets a unique short_name even if:
    - Same user creates multiple packs with same name
    - Pack names are identical after cleaning
    """
    # Normalize Unicode to extract ASCII equivalents
    normalized = unicodedata.normalize('NFKD', pack_name)

    # Extract only ASCII alphanumeric characters for short name
    cleaned = ''
    for char in normalized:
        if char.isalnum() and ord(char) < 128:
            cleaned += char.lower()

    # If nothing left after cleaning, use default
    if not cleaned or len(cleaned) == 0:
        cleaned = "pack"

    # Ensure it starts with alphanumeric
    if cleaned and not cleaned[0].isalnum():
        cleaned = 'p' + cleaned

    # Limit cleaned name length to leave room for timestamp
    if len(cleaned) > 12:
        cleaned = cleaned[:12]

    # ✅ ADD TIMESTAMP for uniqueness (last 6 digits of milliseconds)
    timestamp = int(time.time() * 1000) % 1000000

    # ✅ ADD RANDOM 3-digit number for extra safety
    random_suffix = random.randint(100, 999)

    # Get bot username without @ and ensure it's lowercase
    bot_user = BOT_USERNAME.replace('@', '').lower()

    # ✅ Create UNIQUE short name with timestamp
    short_name = f"{cleaned}{timestamp}{random_suffix}_{user_id}_by_{bot_user}"

    # Ensure total length is under 64 characters (Telegram limit)
    if len(short_name) > 64:
        # Fallback: Use shorter format
        short_name = f"p{timestamp}{random_suffix}_{user_id}_by_{bot_user}"

    # If still too long, use minimal format
    if len(short_name) > 64:
        short_name = f"p{timestamp}_{user_id}"[:64]

    # Final validation - ensure it matches Telegram's pattern
    pattern = r'^[a-z0-9_]+$'
    if not re.match(pattern, short_name):
        # Ultimate fallback with timestamp
        short_name = f"pack{timestamp}_{user_id}_by_{bot_user}"

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
