from typing import Optional
from pydantic import BaseModel


class VirtualTryOnResponse(BaseModel):
    """Simple response for virtual try-on API"""
    image_url: str
    
    
class VirtualTryOnStreamingResult(BaseModel):
    """Simple streaming result for virtual try-on"""
    outfit_id: str
    image_url: str