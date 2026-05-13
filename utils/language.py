import json
import logging
from typing import Optional, Dict
from pathlib import Path

from mongo.userdb import get_user_language

logger = logging.getLogger(__name__)

_template_cache: Dict[str, Dict[str, str]] = {}

SUPPORTED_LANGUAGES = ["en", "rus", "bur"]
DEFAULT_LANGUAGE = "en"


def load_template(language: str) -> Dict[str, str]:
    if language in _template_cache:
        return _template_cache[language]

    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    template_path = Path(f"templates/{language}.json")

    if not template_path.exists():
        if language != DEFAULT_LANGUAGE:
            return load_template(DEFAULT_LANGUAGE)
        return {}

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        _template_cache[language] = template
        logger.info(f"Loaded template '{language}': {len(template)} keys")
        return template
    except Exception as e:
        logger.error(f"Error loading template {template_path}: {e}")
        if language != DEFAULT_LANGUAGE:
            return load_template(DEFAULT_LANGUAGE)
        return {}


async def get_text(user_id: int, key: str, **kwargs) -> Optional[str]:
    try:
        language = await get_user_language(user_id)
        template = _template_cache.get(language) or _template_cache.get(DEFAULT_LANGUAGE, {})

        if key not in template:
            logger.warning(f"Key '{key}' not found for language '{language}'")
            return None

        message = template[key]
        if kwargs:
            try:
                message = message.format(**kwargs)
            except Exception as e:
                logger.error(f"Error formatting key '{key}': {e}")
                return message
        return message
    except Exception as e:
        logger.error(f"Error in get_text user {user_id}, key '{key}': {e}")
        return None


def get_text_sync(language: str, key: str, **kwargs) -> Optional[str]:
    try:
        template = _template_cache.get(language) or _template_cache.get(DEFAULT_LANGUAGE, {})

        if key not in template:
            logger.warning(f"Key '{key}' not found for language '{language}'")
            return None

        message = template[key]
        if kwargs:
            try:
                message = message.format(**kwargs)
            except Exception as e:
                logger.error(f"Error formatting key '{key}': {e}")
                return message
        return message
    except Exception as e:
        logger.error(f"Error in get_text_sync language '{language}', key '{key}': {e}")
        return None


def reload_templates():
    global _template_cache
    _template_cache.clear()
    for lang in SUPPORTED_LANGUAGES:
        load_template(lang)
    logger.info("All templates reloaded")


def get_available_languages() -> list:
    return [
        lang for lang in SUPPORTED_LANGUAGES
        if Path(f"templates/{lang}.json").exists()
    ]


# Startup pe sabhi languages RAM mein load
try:
    for lang in SUPPORTED_LANGUAGES:
        load_template(lang)
    logger.info(f"Templates preloaded: {', '.join(SUPPORTED_LANGUAGES)}")
except Exception as e:
    logger.error(f"Failed to preload templates: {e}")
