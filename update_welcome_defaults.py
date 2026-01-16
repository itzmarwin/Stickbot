# Create update_welcome_defaults.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT

async def update_defaults():
    client = AsyncIOMotorClient(MONGO_URI_MANAGEMENT)
    db = client[DATABASE_NAME_MANAGEMENT]
    
    result = await db.welcome_settings.update_many(
        {},
        {
            "$set": {
                "welcome.default_text": "Welcome {MENTION} to {GROUPNAME}!",
                "goodbye.default_text": "Goodbye {NAME}!"
            }
        }
    )
    
    print(f"✅ Updated {result.modified_count} documents")
    client.close()

asyncio.run(update_defaults())
