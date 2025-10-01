from .telegram_utils import (
    generate_pack_short_name,
    generate_pack_link,
    is_sticker_supported,
    extract_sticker_from_message,
    extract_gif_from_message,
    is_private_chat,
    is_group_chat,
    validate_pack_name,
    create_pack_link_keyboard,
    format_sticker_success_message,
    format_pack_creation_message_with_button,
    format_sticker_added_message_with_button
)

from .sticker_utils import (
    download_sticker,
    download_gif,
    create_sticker_pack,
    add_sticker_to_pack,
    get_sticker_emoji,
    cleanup_temp_file,
    create_sticker_pack_fast,
    add_sticker_to_pack_fast,
    add_converted_sticker_to_pack_fast,
    create_pack_with_converted_sticker_fast
)

from .file_converters import (
    convert_sticker_to_png,
    convert_webm_to_mp4,
    convert_gif_to_webm,
    convert_gif_to_webm_optimized,
    convert_gif_to_webm_compressed,
    get_gif_dimensions,
    convert_gif_to_webm_fallback
)

__all__ = [
    # Telegram utilities
    "generate_pack_short_name",
    "generate_pack_link", 
    "is_sticker_supported",
    "extract_sticker_from_message",
    "extract_gif_from_message",
    "is_private_chat",
    "is_group_chat",
    "validate_pack_name",
    "create_pack_link_keyboard",
    "format_sticker_success_message",  # NEW unified function
    "format_pack_creation_message_with_button",
    "format_sticker_added_message_with_button",
    
    # Sticker utilities
    "download_sticker",
    "download_gif",
    "create_sticker_pack",
    "add_sticker_to_pack",
    "get_sticker_emoji",
    "cleanup_temp_file",
    "create_sticker_pack_fast",  # NEW fast function
    "add_sticker_to_pack_fast",  # NEW fast function
    "add_converted_sticker_to_pack_fast",  # NEW fast function
    "create_pack_with_converted_sticker_fast",  # NEW fast function
    
    # File converters
    "convert_sticker_to_png",
    "convert_webm_to_mp4",
    "convert_gif_to_webm",
    "convert_gif_to_webm_optimized",  # NEW optimized function
    "convert_gif_to_webm_compressed",  # NEW compressed function
    "get_gif_dimensions",  # NEW utility function
    "convert_gif_to_webm_fallback"  # NEW fallback function
]
