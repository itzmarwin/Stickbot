import time
from collections import OrderedDict
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Memory-safe rate limiter with automatic cleanup
    Prevents memory leak from unlimited user_requests dict growth
    """
    def __init__(self, max_entries: int = 10000, cleanup_threshold: float = 1.2):
        """
        Args:
            max_entries: Maximum number of user entries to keep in memory
            cleanup_threshold: Trigger cleanup when entries exceed max_entries * this value
        """
        self.user_requests: OrderedDict[int, float] = OrderedDict()
        self.max_entries = max_entries
        self.cleanup_threshold = int(max_entries * cleanup_threshold)
        self.last_cleanup = time.time()
        self.cleanup_interval = 3600  # Cleanup every hour minimum
        
        logger.info(f"RateLimiter initialized: max_entries={max_entries}, cleanup_threshold={self.cleanup_threshold}")
    
    def is_limited(self, user_id: int, limit_seconds: int = 3) -> bool:
        """
        Check if user is rate limited
        
        Args:
            user_id: Telegram user ID
            limit_seconds: Minimum seconds between requests
            
        Returns:
            True if user should be rate limited, False otherwise
        """
        current_time = time.time()
        
        # ✅ FIX 1: Periodic cleanup to prevent memory leak
        if len(self.user_requests) > self.cleanup_threshold:
            self._aggressive_cleanup(current_time, limit_seconds)
        elif current_time - self.last_cleanup > self.cleanup_interval:
            self._periodic_cleanup(current_time, limit_seconds * 10)
        
        # Check if user is rate limited
        last_request = self.user_requests.get(user_id, 0)
        
        if current_time - last_request < limit_seconds:
            return True
        
        # ✅ FIX 2: Update request time and maintain OrderedDict
        # Remove old entry if exists (to re-add at end)
        if user_id in self.user_requests:
            del self.user_requests[user_id]
        
        self.user_requests[user_id] = current_time
        
        # ✅ FIX 3: Hard limit on dict size
        if len(self.user_requests) > self.max_entries * 1.5:
            # Emergency cleanup - remove oldest 30%
            remove_count = int(len(self.user_requests) * 0.3)
            for _ in range(remove_count):
                self.user_requests.popitem(last=False)
            logger.warning(f"Emergency cleanup: removed {remove_count} old entries")
        
        return False
    
    def _periodic_cleanup(self, current_time: float, max_age: float):
        """
        Regular cleanup of old entries
        Removes entries older than max_age seconds
        """
        initial_size = len(self.user_requests)
        
        to_remove = [
            uid for uid, timestamp in list(self.user_requests.items())
            if current_time - timestamp > max_age
        ]
        
        for uid in to_remove:
            del self.user_requests[uid]
        
        self.last_cleanup = current_time
        
        removed = len(to_remove)
        if removed > 0:
            logger.info(f"Periodic cleanup: removed {removed} old entries (age > {max_age}s), "
                       f"size: {initial_size} -> {len(self.user_requests)}")
    
    def _aggressive_cleanup(self, current_time: float, limit_seconds: float):
        """
        Aggressive cleanup when threshold exceeded
        Removes oldest 50% of entries
        """
        initial_size = len(self.user_requests)
        target_size = self.max_entries // 2
        remove_count = initial_size - target_size
        
        if remove_count > 0:
            # Remove oldest entries
            for _ in range(remove_count):
                if len(self.user_requests) > 0:
                    self.user_requests.popitem(last=False)
            
            logger.warning(f"Aggressive cleanup: removed {remove_count} entries, "
                          f"size: {initial_size} -> {len(self.user_requests)}")
        
        self.last_cleanup = current_time
    
    def reset_user(self, user_id: int):
        """Reset rate limit for specific user (admin use)"""
        if user_id in self.user_requests:
            del self.user_requests[user_id]
            logger.info(f"Rate limit reset for user {user_id}")
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            "total_users": len(self.user_requests),
            "max_entries": self.max_entries,
            "cleanup_threshold": self.cleanup_threshold,
            "memory_usage_mb": len(self.user_requests) * 16 / (1024 * 1024)  # Rough estimate
        }

# Global instance
rate_limiter = RateLimiter(max_entries=10000)  # ✅ Configurable limit

async def is_rate_limited(user_id: int, limit_seconds: int = 3) -> bool:
    """
    Check if user is rate limited
    
    Args:
        user_id: Telegram user ID
        limit_seconds: Minimum seconds between requests (default: 3)
        
    Returns:
        True if user should be rate limited, False otherwise
    """
    return rate_limiter.is_limited(user_id, limit_seconds)

async def reset_rate_limit(user_id: int):
    """Reset rate limit for a user (admin function)"""
    rate_limiter.reset_user(user_id)

def get_rate_limiter_stats() -> Dict:
    """Get rate limiter statistics (for monitoring)"""
    return rate_limiter.get_stats()
