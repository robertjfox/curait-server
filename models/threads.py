from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime


class ThreadBase(BaseModel):
    context: Dict[str, Any] = {}
    comments: List[Dict[str, Any]] = []  # JSONB field for user comments with message and timestamp
    explore_idea_id: Optional[str] = None  # Link to explore idea


class ThreadCreate(ThreadBase):
    user_id: str


class ThreadUpdate(BaseModel):
    context: Optional[Dict[str, Any]] = None


class Thread(ThreadBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ThreadSummary(BaseModel):
    """Lightweight thread info for listing"""
    id: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True 