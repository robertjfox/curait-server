from pydantic import BaseModel
from typing import Optional


class AvatarResponse(BaseModel):
    image_url: str


class CurrentAvatarResponse(BaseModel):
    image_url: Optional[str] = None


