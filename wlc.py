"""
One-time script — sabhi existing groups mein welcome enable karo.
Sirf welcome.enabled = True set hoga, baaki kuch nahi chhuega.

Run: python enable_welcome_all.py
"""

import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI        = os.getenv("MONGO_URI_MANAGEMENT")
DATABASE_NAME    = os.getenv("DATABASE_NAME_MANAGEMENT", "sticker_kang_management")
COLLECTION       = "welcome_settings"


async def main():
    print("=" * 50)
    print("  Welcome Enable — All Existing Groups")
    print("=" * 50)

    if not MONGO_URI:
        print("❌ MONGO_URI_MANAGEMENT not found in .env")
        return

    client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)

    try:
        await client.admin.command("ping")
        print("✅ MongoDB connected\n")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return

    db         = client[DATABASE_NAME]
    collection = db[COLLECTION]

    # Pehle count karo — kitne groups hain total
    total = await collection.count_documents({})
    print(f"📊 Total groups in database : {total}")

    # Kitne already enabled hain
    already_on = await collection.count_documents({"welcome.enabled": True})
    print(f"✅ Already enabled           : {already_on}")

    # Kitne off hain ya field nahi hai
    to_update = await collection.count_documents({
        "$or": [
            {"welcome.enabled": False},
            {"welcome.enabled": {"$exists": False}}
        ]
    })
    print(f"🔄 Will be enabled           : {to_update}\n")

    if to_update == 0:
        print("✅ Sab groups mein welcome already enabled hai. Kuch karne ki zarurat nahi.")
        client.close()
        return

    # Confirm
    confirm = input(f"Kya aap {to_update} groups mein welcome enable karna chahte ho? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("❌ Operation cancelled.")
        client.close()
        return

    # Bulk update — sirf welcome.enabled = True, baaki sab untouched
    result = await collection.update_many(
        {
            "$or": [
                {"welcome.enabled": False},
                {"welcome.enabled": {"$exists": False}}
            ]
        },
        {
            "$set": {
                "welcome.enabled": True,
                "updated_at": datetime.utcnow()
            }
        }
    )

    print(f"\n✅ Done! {result.modified_count} groups mein welcome enable ho gaya.")
    print(f"📊 Total enabled now: {already_on + result.modified_count}/{total}")
    print("=" * 50)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
