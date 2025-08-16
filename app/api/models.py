from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, validator


# Authentication models
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str


# User models
class UserBase(BaseModel):
    username: str
    email: str
    is_active: bool = True
    is_admin: bool = False


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# Source models
class SourceBase(BaseModel):
    name: str
    url: str
    type: str = Field(..., description="Type of source: telegram, rss, web")
    language: str
    priority: int = 1
    categories: List[str] = []
    active: bool = True


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    priority: Optional[int] = None
    categories: Optional[List[str]] = None
    active: Optional[bool] = None


class SourceResponse(SourceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# Topic models
class TopicBase(BaseModel):
    name: str
    description: Optional[str] = None


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class TopicResponse(TopicBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# Summary models
class SummaryBase(BaseModel):
    source_id: int
    content: str
    original_content: str
    topic_id: Optional[int] = None
    approved: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    cost_cents: int = 0


class SummaryCreate(SummaryBase):
    pass


class SummaryUpdate(BaseModel):
    content: Optional[str] = None
    topic_id: Optional[int] = None
    approved: Optional[bool] = None


class SummaryResponse(SummaryBase):
    id: int
    created_at: datetime
    updated_at: datetime
    source: Optional[SourceResponse] = None
    topic: Optional[TopicResponse] = None

    class Config:
        orm_mode = True


# Digest models
class DigestBase(BaseModel):
    title: str
    content: str
    published: bool = False
    scheduled_for: Optional[datetime] = None


class DigestCreate(DigestBase):
    summary_ids: List[int] = []


class DigestUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None
    scheduled_for: Optional[datetime] = None
    summary_ids: Optional[List[int]] = None


class DigestResponse(DigestBase):
    id: int
    created_at: datetime
    updated_at: datetime
    summaries: List[SummaryResponse] = []

    class Config:
        orm_mode = True