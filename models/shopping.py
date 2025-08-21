from typing import Optional
from pydantic import BaseModel


class SearchResultItem(BaseModel):
    title: str
    price: str
    link: str
    imageUrl: str
    source: str
    rating: Optional[float] = None
    ratingCount: Optional[int] = None
    delivery: Optional[str] = None
    ranking: Optional[int] = None  # AI-generated ranking score (1-10) 