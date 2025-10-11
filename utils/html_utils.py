import html
import logging

logger = logging.getLogger(__name__)

def escape_html(text: str) -> str:
    """
    Escape HTML special characters to prevent parsing errors
    Converts: &, <, >, ", '
    """
    try:
        if not text:
            return ""
        return html.escape(text)
    except Exception as e:
        logger.error(f"Error escaping HTML: {e}")
        return str(text) if text else ""

def safe_format(template: str, **kwargs) -> str:
    """
    Safely format a template by escaping all values
    """
    try:
        # Escape all keyword arguments
        escaped_kwargs = {key: escape_html(str(value)) for key, value in kwargs.items()}
        return template.format(**escaped_kwargs)
    except Exception as e:
        logger.error(f"Error in safe_format: {e}")
        return template
