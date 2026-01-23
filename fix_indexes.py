

import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header():
    print(f"""
{Colors.BLUE}{Colors.BOLD}
╔══════════════════════════════════════════════════════════╗
║         MongoDB Index Cleanup Script v1.0               ║
║         Fixes index conflicts automatically              ║
╚══════════════════════════════════════════════════════════╝
{Colors.END}
""")


def print_success(msg):
    print(f"{Colors.GREEN}✅ {msg}{Colors.END}")


def print_error(msg):
    print(f"{Colors.RED}❌ {msg}{Colors.END}")


def print_warning(msg):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.END}")


def print_info(msg):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.END}")


async def get_config():
    """Get MongoDB configuration"""
    try:
        # Try to import from config.py
        sys.path.insert(0, '.')
        from config import MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT
        
        print_success("Configuration loaded from config.py")
        return MONGO_URI_MANAGEMENT, DATABASE_NAME_MANAGEMENT
        
    except ImportError:
        print_warning("config.py not found, please enter manually")
        
        mongo_uri = input("\nEnter MongoDB URI: ").strip()
        database_name = input("Enter Database Name: ").strip()
        
        return mongo_uri, database_name


async def list_indexes(collection):
    """List all indexes in collection"""
    try:
        indexes = await collection.list_indexes().to_list(length=None)
        return indexes
    except Exception as e:
        print_error(f"Failed to list indexes: {e}")
        return []


async def drop_index_safe(collection, index_name):
    """Safely drop an index"""
    try:
        await collection.drop_index(index_name)
        print_success(f"Dropped index: {index_name}")
        return True
    except Exception as e:
        print_warning(f"Could not drop {index_name}: {e}")
        return False


async def create_index_safe(collection, keys, name, unique=False):
    """Safely create an index"""
    try:
        if isinstance(keys, str):
            await collection.create_index(keys, name=name, unique=unique)
        else:
            await collection.create_index(keys, name=name, unique=unique)
        print_success(f"Created index: {name}")
        return True
    except Exception as e:
        print_error(f"Failed to create {name}: {e}")
        return False


async def main():
    print_header()
    
    # Step 1: Get configuration
    print_info("Step 1: Loading configuration...")
    try:
        mongo_uri, database_name = await get_config()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
    
    if not mongo_uri or not database_name:
        print_error("MongoDB URI or Database Name is empty!")
        sys.exit(1)
    
    print_info(f"Database: {database_name}")
    print()
    
    # Step 2: Connect to MongoDB
    print_info("Step 2: Connecting to MongoDB...")
    try:
        client = AsyncIOMotorClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000
        )
        
        # Test connection
        await client.admin.command('ping')
        print_success("Connected to MongoDB successfully")
        
        db = client[database_name]
        collection = db.welcome_settings
        
    except Exception as e:
        print_error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)
    
    print()
    
    # Step 3: List existing indexes
    print_info("Step 3: Checking existing indexes...")
    existing_indexes = await list_indexes(collection)
    
    if not existing_indexes:
        print_warning("No indexes found or failed to retrieve indexes")
    else:
        print(f"\n{Colors.BOLD}Current indexes:{Colors.END}")
        for idx in existing_indexes:
            name = idx.get('name')
            keys = idx.get('key')
            unique = idx.get('unique', False)
            unique_str = f" {Colors.YELLOW}(unique){Colors.END}" if unique else ""
            print(f"   • {name}: {keys}{unique_str}")
    
    print()
    
    # Step 4: Identify and drop conflicting indexes
    print_info("Step 4: Removing conflicting indexes...")
    
    existing_index_names = {idx.get('name') for idx in existing_indexes}
    indexes_to_drop = []
    
    # Find conflicting indexes
    for idx in existing_indexes:
        idx_name = idx.get('name')
        
        # Skip _id_ index (system index)
        if idx_name == '_id_':
            continue
        
        # Check for old unnamed chat_id index
        if idx_name == 'chat_id_1':
            indexes_to_drop.append(idx_name)
        
        # Drop old separate enabled indexes
        elif idx_name in ['welcome.enabled_1', 'goodbye.enabled_1']:
            indexes_to_drop.append(idx_name)
        
        # Drop old compound indexes
        elif 'chat_id_1_welcome.enabled_1' in idx_name:
            indexes_to_drop.append(idx_name)
        elif 'chat_id_1_goodbye.enabled_1' in idx_name:
            indexes_to_drop.append(idx_name)
        
        # Drop old updated_at if unnamed
        elif idx_name == 'updated_at_1':
            indexes_to_drop.append(idx_name)
    
    if indexes_to_drop:
        print(f"\n{Colors.BOLD}Dropping {len(indexes_to_drop)} conflicting index(es):{Colors.END}")
        for idx_name in indexes_to_drop:
            await drop_index_safe(collection, idx_name)
    else:
        print_success("No conflicting indexes found")
    
    print()
    
    # Step 5: Create new optimized indexes
    print_info("Step 5: Creating optimized indexes...")
    
    # Refresh index list
    existing_indexes = await list_indexes(collection)
    existing_index_names = {idx.get('name') for idx in existing_indexes}
    
    created_count = 0
    
    # Index 1: Primary unique chat_id
    if 'idx_chat_id' not in existing_index_names:
        if await create_index_safe(collection, "chat_id", "idx_chat_id", unique=True):
            created_count += 1
    else:
        print_info("Index 'idx_chat_id' already exists, skipping")
    
    # Index 2: Compound index for welcome queries
    if 'idx_chat_welcome' not in existing_index_names:
        if await create_index_safe(
            collection,
            [("chat_id", 1), ("welcome.enabled", 1)],
            "idx_chat_welcome"
        ):
            created_count += 1
    else:
        print_info("Index 'idx_chat_welcome' already exists, skipping")
    
    # Index 3: Updated_at for maintenance
    if 'idx_updated_at' not in existing_index_names:
        if await create_index_safe(collection, "updated_at", "idx_updated_at"):
            created_count += 1
    else:
        print_info("Index 'idx_updated_at' already exists, skipping")
    
    if created_count > 0:
        print_success(f"Created {created_count} new index(es)")
    
    print()
    
    # Step 6: Verify final state
    print_info("Step 6: Verifying final indexes...")
    
    final_indexes = await list_indexes(collection)
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}Final index configuration:{Colors.END}")
    for idx in final_indexes:
        name = idx.get('name')
        keys = idx.get('key')
        unique = idx.get('unique', False)
        unique_str = f" {Colors.YELLOW}(unique){Colors.END}" if unique else ""
        print(f"   • {name}: {keys}{unique_str}")
    
    # Close connection
    client.close()
    
    print()
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}")
    print_success("Index cleanup completed successfully!")
    print(f"{Colors.GREEN}{Colors.BOLD}{'='*60}{Colors.END}")
    print()
    print_info("You can now start your bot: python3 main.py")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Script cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
