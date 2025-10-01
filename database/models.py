from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from bson import ObjectId


@dataclass
class StickerPack:
    """Represents a sticker pack in the database"""
    pack_name: str
    pack_short_name: str
    pack_link: str
    created_at: datetime
    sticker_count: int = 1  # Track sticker count for pack limits
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB insertion"""
        data = asdict(self)
        # Convert datetime to ISO string for MongoDB
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StickerPack':
        """Create StickerPack from MongoDB document"""
        # Convert ISO string back to datetime
        if isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
    
    def is_full(self) -> bool:
        """Check if pack is full (Telegram limit: 120 stickers)"""
        return self.sticker_count >= 120
    
    def can_add_sticker(self) -> bool:
        """Check if we can add more stickers to this pack"""
        return self.sticker_count < 120


@dataclass
class UserData:
    """Represents user data in the database"""
    user_id: int
    bot_id: int
    packs: List[StickerPack]
    started: bool = False  # Track if user started the bot in private
    _id: Optional[ObjectId] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB insertion"""
        data = {
            'user_id': self.user_id,
            'bot_id': self.bot_id,
            'packs': [pack.to_dict() for pack in self.packs],
            'started': self.started
        }
        if self._id:
            data['_id'] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserData':
        """Create UserData from MongoDB document"""
        packs = [StickerPack.from_dict(pack_data) for pack_data in data.get('packs', [])]
        return cls(
            user_id=data['user_id'],
            bot_id=data['bot_id'],
            packs=packs,
            started=data.get('started', False),
            _id=data.get('_id')
        )
    
    def add_pack(self, pack: StickerPack) -> None:
        """Add a new sticker pack"""
        self.packs.append(pack)
    
    def get_pack_by_short_name(self, short_name: str) -> Optional[StickerPack]:
        """Get a pack by its short name"""
        for pack in self.packs:
            if pack.pack_short_name == short_name:
                return pack
        return None
    
    def has_packs(self) -> bool:
        """Check if user has any sticker packs"""
        return len(self.packs) > 0
    
    def get_latest_active_pack(self) -> Optional[StickerPack]:
        """Get the most recent pack that can accept more stickers"""
        # Search from newest to oldest for a pack that's not full
        for pack in reversed(self.packs):
            if pack.can_add_sticker():
                return pack
        return None
    
    def has_active_packs(self) -> bool:
        """Check if user has any packs that can accept more stickers"""
        return any(pack.can_add_sticker() for pack in self.packs)
    
    def mark_started(self) -> None:
        """Mark user as started the bot"""
        self.started = True
    
    def increment_sticker_count(self, pack_short_name: str) -> bool:
        """Increment sticker count for a pack"""
        pack = self.get_pack_by_short_name(pack_short_name)
        if pack and pack.can_add_sticker():
            pack.sticker_count += 1
            return True
        return False
    
    def get_total_stickers(self) -> int:
        """Get total number of stickers across all packs"""
        return sum(pack.sticker_count for pack in self.packs)
    
    def get_pack_count(self) -> int:
        """Get total number of packs"""
        return len(self.packs)
