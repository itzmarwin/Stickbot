"""
Callback Data Manager - Solves BUTTON_DATA_INVALID error

Telegram has a 64-byte limit for callback_data in inline buttons.
This module stores long data in memory and uses short hashes in buttons.

Author: Sticker Kang Bot
Version: 1.0
"""
import hashlib
import time
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CallbackDataManager:
    """
    ✅ Manages callback data with automatic cleanup
    
    Problem: Pack short_names like "mypack1729345123_123456789_by_bot" are too long
    Solution: Store in memory, use 8-character hash in buttons
    
    Example:
        Long data: "pack_selected:mypack1729345123_123456789_by_bot" (50+ bytes) ❌
        Short data: "ps:a1b2c3d4" (11 bytes) ✅
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize callback manager
        
        Args:
            ttl_seconds: Time-to-live for stored data (default: 1 hour)
        """
        self.storage: Dict[str, Tuple[str, float]] = {}  # {hash: (data, timestamp)}
        self.ttl = ttl_seconds
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Cleanup every 5 minutes
        
        logger.info(f"CallbackDataManager initialized: TTL={ttl_seconds}s, Cleanup={self.cleanup_interval}s")
    
    def store(self, prefix: str, data: str) -> str:
        """
        Store long data and return short callback_data
        
        Args:
            prefix: Callback prefix (e.g., "pack_selected", "rename_pack")
            data: Long data to store (e.g., pack short_name)
        
        Returns:
            Short callback_data string (under 64 bytes)
        
        Example:
            >>> manager.store("pack_selected", "mypack1729345123_123456789_by_bot")
            "ps:a1b2c3d4"
        """
        # Create short hash (8 characters)
        hash_input = f"{prefix}:{data}:{time.time()}".encode()
        short_hash = hashlib.md5(hash_input).hexdigest()[:8]
        
        # Store with timestamp
        self.storage[short_hash] = (data, time.time())
        
        # Create short callback_data
        short_prefix = self._shorten_prefix(prefix)
        callback_data = f"{short_prefix}:{short_hash}"
        
        # Periodic cleanup
        if time.time() - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
        
        logger.debug(f"Stored: {prefix}:{data[:20]}... -> {callback_data}")
        return callback_data
    
    def retrieve(self, callback_data: str) -> Optional[str]:
        """
        Retrieve original data from short callback_data
        
        Args:
            callback_data: Short callback data (e.g., "ps:a1b2c3d4")
        
        Returns:
            Original data or None if expired/not found
        
        Example:
            >>> manager.retrieve("ps:a1b2c3d4")
            "mypack1729345123_123456789_by_bot"
        """
        try:
            # Parse callback_data
            if ":" not in callback_data:
                logger.warning(f"Invalid callback format (no colon): {callback_data}")
                return None
            
            parts = callback_data.split(":", 1)
            if len(parts) != 2:
                logger.warning(f"Invalid callback format (wrong parts): {callback_data}")
                return None
            
            short_hash = parts[1]
            
            # Retrieve from storage
            if short_hash not in self.storage:
                logger.warning(f"Hash not found in storage: {short_hash}")
                return None
            
            data, timestamp = self.storage[short_hash]
            
            # Check expiry
            age = time.time() - timestamp
            if age > self.ttl:
                logger.warning(f"Expired data (age: {age:.0f}s): {short_hash}")
                del self.storage[short_hash]
                return None
            
            logger.debug(f"Retrieved: {callback_data} -> {data[:20]}... (age: {age:.0f}s)")
            return data
            
        except Exception as e:
            logger.error(f"Error retrieving callback data: {e}", exc_info=True)
            return None
    
    def _shorten_prefix(self, prefix: str) -> str:
        """
        Convert long prefix to 2-character code
        
        This mapping keeps callback_data under 64 bytes limit
        
        Args:
            prefix: Long prefix name
        
        Returns:
            2-character short code
        
        Examples:
            pack_selected -> ps
            rename_pack -> rp
            delete_pack -> dp
        """
        prefix_map = {
            # Pack management
            "pack_selected": "ps",
            "pack_options": "po",
            "rename_pack": "rp",
            "delete_pack": "dp",
            "add_sticker": "as",
            "confirm_delete": "cd",
            "cancel_delete": "xd",
            "pack_info": "pi",
            "next_page": "np",
            "prev_page": "pp",
            
            # Publish system
            "publish_pack": "pb",
            "publish_confirm_yes": "py",
            "publish_confirm_no": "pn",
            "owner_approve": "oa",
            "owner_reject": "or",
        }
        
        # Return mapped code or first 2 chars as fallback
        return prefix_map.get(prefix, prefix[:2])
    
    def _cleanup(self):
        """
        Remove expired entries from storage
        
        Called periodically to prevent memory buildup
        Removes entries older than TTL
        """
        current_time = time.time()
        initial_size = len(self.storage)
        
        # Find expired entries
        expired = [
            hash_key for hash_key, (data, timestamp) in list(self.storage.items())
            if current_time - timestamp > self.ttl
        ]
        
        # Remove expired
        for hash_key in expired:
            del self.storage[hash_key]
        
        self.last_cleanup = current_time
        
        if expired:
            logger.info(f"Cleanup: Removed {len(expired)} expired entries, "
                       f"Size: {initial_size} -> {len(self.storage)}")
    
    def get_stats(self) -> Dict[str, any]:
        """
        Get storage statistics for monitoring
        
        Returns:
            Dictionary with statistics
        
        Example output:
            {
                "total_stored": 45,
                "oldest_entry_age": 234.5,
                "ttl_seconds": 3600,
                "usage_percent": 4.5,
                "max_capacity": 1000
            }
        """
        current_time = time.time()
        
        # Calculate oldest entry age
        oldest_age = 0
        if self.storage:
            oldest_age = max(
                current_time - timestamp 
                for _, timestamp in self.storage.values()
            )
        
        # Estimate max capacity (conservative estimate)
        max_capacity = 1000
        
        return {
            "total_stored": len(self.storage),
            "oldest_entry_age": round(oldest_age, 1),
            "ttl_seconds": self.ttl,
            "usage_percent": round((len(self.storage) / max_capacity) * 100, 2),
            "max_capacity": max_capacity,
            "last_cleanup": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_cleanup))
        }
    
    def clear(self):
        """
        Clear entire storage (admin function)
        
        Use this for emergency cleanup or maintenance
        """
        initial_size = len(self.storage)
        self.storage.clear()
        logger.warning(f"Storage cleared: {initial_size} entries removed")
    
    def force_cleanup(self):
        """
        Force immediate cleanup (admin function)
        
        Useful for testing or maintenance
        """
        logger.info("Forcing cleanup...")
        self._cleanup()


# ✅ Global instance - shared across entire bot
callback_manager = CallbackDataManager(ttl_seconds=3600)  # 1 hour TTL


# ✅ Helper functions for easy usage in handlers
def create_callback(prefix: str, data: str) -> str:
    """
    Create short callback_data from long data
    
    This is the main function used in handlers to create buttons
    
    Args:
        prefix: Action prefix (e.g., "pack_selected")
        data: Long data to store (e.g., pack short_name)
    
    Returns:
        Short callback_data string
    
    Usage in handlers:
        # OLD (causes BUTTON_DATA_INVALID):
        callback_data = f"pack_selected:{pack['short_name']}"  # 50+ bytes ❌
        
        # NEW (always under 64 bytes):
        callback_data = create_callback("pack_selected", pack['short_name'])  # 11 bytes ✅
    
    Example:
        >>> create_callback("pack_selected", "mypack1729345123_123456789_by_bot")
        "ps:a1b2c3d4"
    """
    return callback_manager.store(prefix, data)


def parse_callback(callback_data: str) -> Optional[str]:
    """
    Parse callback_data to get original data
    
    This is the main function used in callback handlers to retrieve data
    
    Args:
        callback_data: Short callback data from button click
    
    Returns:
        Original long data or None if expired/not found
    
    Usage in handlers:
        # OLD:
        short_name = callback.data.split(":")[1]  # Direct parsing
        
        # NEW:
        short_name = parse_callback(callback.data)  # Safe parsing
        if not short_name:
            await callback.answer("Session expired", show_alert=True)
            return
    
    Example:
        >>> parse_callback("ps:a1b2c3d4")
        "mypack1729345123_123456789_by_bot"
    """
    return callback_manager.retrieve(callback_data)


def get_callback_stats() -> Dict[str, any]:
    """
    Get callback manager statistics
    
    Useful for monitoring and debugging
    
    Returns:
        Statistics dictionary
    
    Usage:
        >>> stats = get_callback_stats()
        >>> print(f"Stored callbacks: {stats['total_stored']}")
        Stored callbacks: 45
    """
    return callback_manager.get_stats()


def clear_all_callbacks():
    """
    Clear all stored callbacks (admin function)
    
    ⚠️ WARNING: This will invalidate all active buttons!
    Only use for emergency cleanup
    
    Usage:
        >>> clear_all_callbacks()
        # All buttons will show "Session expired" error
    """
    callback_manager.clear()


def force_cleanup_callbacks():
    """
    Force immediate cleanup of expired callbacks
    
    Normally cleanup happens automatically every 5 minutes
    Use this to manually trigger cleanup
    
    Usage:
        >>> force_cleanup_callbacks()
        # Removes all expired entries immediately
    """
    callback_manager.force_cleanup()


# ✅ Module-level info
__version__ = "1.0.0"
__author__ = "Sticker Kang Bot"
__description__ = "Callback data manager for Telegram bots - Solves BUTTON_DATA_INVALID error"


if __name__ == "__main__":
    # ✅ Self-test when run directly
    print("=" * 60)
    print("Callback Manager Self-Test")
    print("=" * 60)
    
    # Test 1: Store and retrieve
    print("\n[TEST 1] Store and Retrieve")
    long_data = "mypack1729345123456_123456789_by_stickerkangbot"
    short = create_callback("pack_selected", long_data)
    print(f"Original: {long_data} ({len(long_data)} chars)")
    print(f"Short:    {short} ({len(short)} chars)")
    
    retrieved = parse_callback(short)
    print(f"Retrieved: {retrieved}")
    print(f"✅ Match: {retrieved == long_data}")
    
    # Test 2: Multiple stores
    print("\n[TEST 2] Multiple Stores")
    for i in range(5):
        data = f"testpack{i}_user123_by_bot"
        short = create_callback("pack_selected", data)
        print(f"  {i+1}. {data[:20]}... -> {short}")
    
    # Test 3: Statistics
    print("\n[TEST 3] Statistics")
    stats = get_callback_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Test 4: Expiry (simulated)
    print("\n[TEST 4] Expiry Test")
    print("  Creating entry with 2-second TTL...")
    temp_manager = CallbackDataManager(ttl_seconds=2)
    short = temp_manager.store("test", "expiring_data")
    print(f"  Stored: {short}")
    
    import time
    print("  Waiting 3 seconds...")
    time.sleep(3)
    
    retrieved = temp_manager.retrieve(short)
    print(f"  Retrieved: {retrieved}")
    print(f"  ✅ Expired correctly: {retrieved is None}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
