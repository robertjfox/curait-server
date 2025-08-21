from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    dob: Optional[date] = None
    location: Optional[str] = None
    gender: Optional[str] = None

    context: Optional[Dict[str, Any]] = {}


class UserCreate(UserBase):
    id: Optional[str] = None  # Auto-generated UUID if not provided


class UserUpdate(UserBase):
    pass


class User(UserBase):
    id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True 