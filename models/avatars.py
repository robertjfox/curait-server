from pydantic import BaseModel


class AvatarResponse(BaseModel):
    image_url: str


