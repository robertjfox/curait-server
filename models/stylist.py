from typing import Dict, List, Optional
from pydantic import BaseModel, field_validator, Field
from .shopping import SearchResultItem
import re


_HEX_RE = re.compile(r'^#(?:[0-9A-Fa-f]{6})$')


class Colors(BaseModel):
    dark: str = "#222222"
    light: str = "#EFEFEF"

    @field_validator('dark', 'light', mode='before')
    @classmethod
    def _validate_hex(cls, value, info):
        s = str(value or '').strip().upper() if hasattr(str(value or ''), 'upper') else str(value or '').strip().upper()
        if _HEX_RE.match(s):
            return s
        # Safe defaults
        return '#222222' if info.field_name == 'dark' else '#EFEFEF'


class OutfitItem(BaseModel):
    type: str
    keywords: Optional[str] = None
    search_results: Optional[List[SearchResultItem]] = None


class Outfit(BaseModel):
    name: str
    description: str
    items: Dict[str, OutfitItem]


class OutfitsResponse(BaseModel):
    outfits: Dict[str, Outfit] 