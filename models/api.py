from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class ThreadCreateRequest(BaseModel):
    user_id: str


class ThreadChatRequest(BaseModel):
    message: str
    user_intent: Optional[str] = None  # "CHAT", "MODIFICATION", "GENERATE" - if None, use LLM decision
    outfit_id: Optional[str] = None  # Required when user_intent is "MODIFICATION"


class VirtualTryOnRequest(BaseModel):
    user_id: str
    outfit_id: str
    product_ids: List[str]  # Search result product IDs
    thread_id: str

