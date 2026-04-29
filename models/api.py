from typing import List, Optional
from pydantic import BaseModel


class ThreadCreateRequest(BaseModel):
    user_id: str


class ThreadChatRequest(BaseModel):
    message: str


class VirtualTryOnRequest(BaseModel):
    user_id: str
    thread_id: Optional[str] = None
    thumbnails: List[str]
    outfit_id: Optional[str] = None


class PromptSuggestionsResponse(BaseModel):
    success: bool
    user_id: str
    prompts: List[str]
