import logging
import os
from typing import Optional, Dict
from pathlib import Path

from mongo.userdb import get_user_language

logger = logging.getLogger(__name__)

# In-memory cache for loaded templates
_template_cache: Dict[str, Dict[str, str]] = {}

# Supported languages
SUPPORTED_LANGUAGES = ["en", "rus", "bur"]
DEFAULT_LANGUAGE = "en"


def load_template(language: str) -> Dict[str, str]:
    """
    Load .temp file and parse KEY=VALUE pairs
    
    Args:
        language: Language code ("en", "rus", "bur")
    
    Returns:
        Dictionary of key-value pairs from template file
    """
    # Return from cache if already loaded
    if language in _template_cache:
        return _template_cache[language]
    
    # Validate language
    if language not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language '{language}', falling back to '{DEFAULT_LANGUAGE}'")
        language = DEFAULT_LANGUAGE
    
    # Build file path
    template_path = Path(f"templates/{language}.temp")
    
    # Check if file exists
    if not template_path.exists():
        logger.error(f"Template file not found: {template_path}")
        if language != DEFAULT_LANGUAGE:
            logger.info(f"Falling back to default language: {DEFAULT_LANGUAGE}")
            return load_template(DEFAULT_LANGUAGE)
        return {}
    
    # Parse template file
    template = {}
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Process escape sequences
                    value = value.replace('\\n', '\n')
                    value = value.replace('\\t', '\t')
                    
                    template[key] = value
                else:
                    logger.warning(f"Invalid line in {template_path}:{line_num} - {line}")
        
        # Cache the template
        _template_cache[language] = template
        logger.info(f"✅ Loaded template for '{language}': {len(template)} keys")
        
        return template
        
    except Exception as e:
        logger.error(f"Error loading template {template_path}: {e}", exc_info=True)
        if language != DEFAULT_LANGUAGE:
            return load_template(DEFAULT_LANGUAGE)
        return {}


async def get_text(user_id: int, key: str, **kwargs) -> Optional[str]:
    """
    Get translated text for a specific user
    
    Args:
        user_id: User's Telegram ID
        key: Message key from template (e.g., "START_MESSAGE", "B_MANAGE_PACKS")
        **kwargs: Format arguments for the message template
    
    Returns:
        Formatted translated text, or None if key not found
    """
    try:
        # Get user's language preference
        language = await get_user_language(user_id)
        
        # Load template
        template = load_template(language)
        
        # Check if key exists
        if key not in template:
            logger.warning(f"Key '{key}' not found in template for language '{language}'")
            return None
        
        # Get message template
        message = template[key]
        
        # Format with provided arguments
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing format argument for key '{key}': {e}")
                return message  # Return unformatted message
            except Exception as e:
                logger.error(f"Error formatting message for key '{key}': {e}")
                return message
        
        return message
        
    except Exception as e:
        logger.error(f"Error getting text for user {user_id}, key '{key}': {e}", exc_info=True)
        return None


def get_text_sync(language: str, key: str, **kwargs) -> Optional[str]:
    """
    Get translated text synchronously (for keyboard builders)
    
    Args:
        language: Language code ("en", "rus", "bur")
        key: Message key from template
        **kwargs: Format arguments
    
    Returns:
        Formatted translated text, or None if key not found
    """
    try:
        # Load template
        template = load_template(language)
        
        # Check if key exists
        if key not in template:
            logger.warning(f"Key '{key}' not found in template for language '{language}'")
            return None
        
        # Get message template
        message = template[key]
        
        # Format with provided arguments
        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                logger.error(f"Missing format argument for key '{key}': {e}")
                return message
            except Exception as e:
                logger.error(f"Error formatting message for key '{key}': {e}")
                return message
        
        return message
        
    except Exception as e:
        logger.error(f"Error getting text for language '{language}', key '{key}': {e}", exc_info=True)
        return None


def reload_templates():
    """
    Clear template cache and reload all templates
    Useful for development/testing
    """
    global _template_cache
    _template_cache.clear()
    logger.info("Template cache cleared")
    
    # Reload all supported languages
    for lang in SUPPORTED_LANGUAGES:
        load_template(lang)


def get_available_languages() -> list:
    """
    Get list of available languages
    
    Returns:
        List of language codes that have template files
    """
    available = []
    for lang in SUPPORTED_LANGUAGES:
        template_path = Path(f"templates/{lang}.temp")
        if template_path.exists():
            available.append(lang)
    return available


# Preload default language on import
try:
    load_template(DEFAULT_LANGUAGE)
except Exception as e:
    logger.error(f"Failed to preload default language template: {e}")
