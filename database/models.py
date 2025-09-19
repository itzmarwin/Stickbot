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


@dataclass
class UserData:
    """Represents user data in the database"""
    user_id: int
    bot_id: int
    packs: List[StickerPack]
    _id: Optional[ObjectId] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for MongoDB insertion"""
        data = {
            'user_id': self.user_id,
            'bot_id': self.bot_id,
            'packs': [pack.to_dict() for pack in self.packs]
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
