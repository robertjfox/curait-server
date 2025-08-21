from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime

MessageRole = Literal["user", "assistant", "system"]


class MessageBase(BaseModel):
    role: MessageRole
    content: str
    metadata: Dict[str, Any] = {}


class MessageCreate(MessageBase):
    thread_id: str


class MessageUpdate(BaseModel):
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class Message(MessageBase):
    id: str
    thread_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageWithOutfits(Message):
    """Message with associated outfits for styling responses"""
    outfits: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class ConversationMessage(BaseModel):
    """Simplified message format for OpenAI chat completions"""
    role: MessageRole
    content: str

    class Config:
        from_attributes = True 