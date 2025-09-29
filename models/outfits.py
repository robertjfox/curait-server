from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime


class OutfitBase(BaseModel):
    thread_id: str
    name: str
    is_cached: bool = False  # Flag to indicate if outfit is cached


class OutfitCreate(OutfitBase):
    is_cached: bool = False


class OutfitUpdate(BaseModel):
    name: Optional[str] = None
    is_cached: Optional[bool] = None


class Outfit(OutfitBase):
    id: str
    created_at: datetime
    updated_at: datetime
    feedback: Optional[str] = None
    default_rendering_url: Optional[str] = None
    vton_image_url: Optional[str] = None

    class Config:
        from_attributes = True
