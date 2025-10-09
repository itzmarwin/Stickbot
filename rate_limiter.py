import time
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.user_requests: Dict[int, float] = {}
    
    def is_limited(self, user_id: int, limit_seconds: int = 3) -> bool:
        """Check if user is rate limited"""
        current_time = time.time()
        last_request = self.user_requests.get(user_id, 0)
        
        if current_time - last_request < limit_seconds:
            return True
            
        self.user_requests[user_id] = current_time
        return False

# Global instance
rate_limiter = RateLimiter()

async def is_rate_limited(user_id: int) -> bool:
    return rate_limiter.is_limited(user_id)
