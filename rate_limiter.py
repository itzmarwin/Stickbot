import time
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self):
        self.user_requests: Dict[int, float] = {}

    def is_limited(self, user_id: int, limit_seconds: int = 3) -> bool:
        current_time = time.time()
        last_request = self.user_requests.get(user_id, 0)

        if current_time - last_request < limit_seconds:
            return True

        self.user_requests[user_id] = current_time
        return False


class StickerQueue:
    def __init__(self):
        self.processing: Dict[int, float] = {}
        self.timeout = 30

    def is_processing(self, user_id: int) -> bool:
        if user_id not in self.processing:
            return False
        
        elapsed = time.time() - self.processing[user_id]
        if elapsed > self.timeout:
            del self.processing[user_id]
            return False
        
        return True

    def start_processing(self, user_id: int):
        self.processing[user_id] = time.time()

    def stop_processing(self, user_id: int):
        if user_id in self.processing:
            del self.processing[user_id]


class CopyPackQueue:
    def __init__(self):
        self.processing: Dict[int, float] = {}
        self.timeout = 300
        self.last_copy: Dict[int, float] = {}
        self.cooldown = 30

    def is_processing(self, user_id: int) -> bool:
        if user_id not in self.processing:
            return False
        
        elapsed = time.time() - self.processing[user_id]
        if elapsed > self.timeout:
            del self.processing[user_id]
            return False
        
        return True

    def can_copy(self, user_id: int) -> tuple[bool, int]:
        if user_id not in self.last_copy:
            return True, 0
        
        elapsed = time.time() - self.last_copy[user_id]
        if elapsed < self.cooldown:
            remaining = int(self.cooldown - elapsed)
            return False, remaining
        
        return True, 0

    def start_processing(self, user_id: int):
        self.processing[user_id] = time.time()
        self.last_copy[user_id] = time.time()

    def stop_processing(self, user_id: int):
        if user_id in self.processing:
            del self.processing[user_id]


rate_limiter = RateLimiter()
sticker_queue = StickerQueue()
copypack_queue = CopyPackQueue()


async def is_rate_limited(user_id: int) -> bool:
    return rate_limiter.is_limited(user_id)


async def is_sticker_processing(user_id: int) -> bool:
    return sticker_queue.is_processing(user_id)


def start_sticker_processing(user_id: int):
    sticker_queue.start_processing(user_id)


def stop_sticker_processing(user_id: int):
    sticker_queue.stop_processing(user_id)


async def is_copypack_processing(user_id: int) -> bool:
    return copypack_queue.is_processing(user_id)


async def can_copy_pack(user_id: int) -> tuple[bool, int]:
    return copypack_queue.can_copy(user_id)


def start_copypack_processing(user_id: int):
    copypack_queue.start_processing(user_id)


def stop_copypack_processing(user_id: int):
    copypack_queue.stop_processing(user_id)
