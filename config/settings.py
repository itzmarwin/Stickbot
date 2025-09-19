import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    """Bot configuration settings"""
    
    # Telegram Bot Configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "")
    
    # MongoDB Configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "sticker_kang_bot")
    MONGO_USERNAME: str = os.getenv("MONGO_USERNAME", "")
    MONGO_PASSWORD: str = os.getenv("MONGO_PASSWORD", "")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Bot Constants
    MAX_STICKERS_PER_PACK: int = 120  # Telegram limit
    SUPPORTED_STICKER_TYPES: tuple = ("photo", "video", "document", "animated")  # All sticker types
    
    # Messages
    WELCOME_MESSAGE = (
        "Hey! I'm a Sticker Kang Bot. 🤖\n\n"
        "Use /kang in a group by replying to any sticker (static, animated, or video) to start creating your own sticker pack!"
    )
    
    KANG_PRIVATE_CHAT_MESSAGE = "⚠️ Please use /kang in a group by replying to a sticker"
    
    PACK_CREATED_MESSAGE = "✅ Pack created! Now reply to any sticker with /kang to add it."
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that all required settings are present"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN is required")
        if not cls.BOT_USERNAME:
            raise ValueError("BOT_USERNAME is required")
        if not cls.MONGO_DB_NAME:
            raise ValueError("MONGO_DB_NAME is required")
        return True

# Create settings instance
settings = Settings()

# Validate settings on import
settings.validate()
