"""
Database Schemas for FluxMarket (Classifieds)

Each Pydantic model maps to a MongoDB collection (lowercased class name).
Use these for validation and to keep collections consistent.
"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, EmailStr

# Users who can post, message, and save listings
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="SHA-256 hash of password")
    avatar_url: Optional[HttpUrl] = Field(None, description="Profile avatar URL")
    location: Optional[str] = Field(None, description="City or region")
    is_active: bool = Field(True, description="Whether user is active")

# Items or services for sale or hire
class Listing(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    title: str = Field(..., max_length=140)
    description: str = Field(..., max_length=5000)
    price: float = Field(..., ge=0)
    category: str = Field(..., description="Category name")
    listing_type: Literal['sale', 'service', 'rent'] = Field('sale')
    location: Optional[str] = None
    images: List[HttpUrl] = Field(default_factory=list)
    status: Literal['active', 'sold', 'paused'] = Field('active')

# Direct messages between buyer and seller tied to a listing
class Message(BaseModel):
    listing_id: str
    from_user_id: str
    to_user_id: str
    content: str = Field(..., max_length=5000)
    read: bool = Field(False)

# Saved/favorited listings per user
class Saved(BaseModel):
    user_id: str
    listing_id: str

