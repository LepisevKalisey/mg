from __future__ import annotations

"""Admin module for MG Digest.

This module provides functionality for the admin interface.
"""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.common.config import load_config
from app.common.logging import setup_logging
from app.db.digests import DigestRepository
from app.db.sources import SourceRepository
from app.db.topics import TopicRepository
from app.db.users import UserRepository
from app.worker.digest import generate_digest, publish_digest

logger = setup_logging()

# Define API router
router = APIRouter(prefix="/api/admin", tags=["admin"])


# Models for request and response
class DigestCreate(BaseModel):
    """Model for creating a digest."""
    title: str
    description: str
    start_date: str
    end_date: str
    topics: List[int] = []
    sources: List[int] = []


class DigestUpdate(BaseModel):
    """Model for updating a digest."""
    title: Optional[str] = None
    description: Optional[str] = None
    published: Optional[bool] = None


class SourceCreate(BaseModel):
    """Model for creating a source."""
    name: str
    url: str
    enabled: bool = True


class SourceUpdate(BaseModel):
    """Model for updating a source."""
    name: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None


class TopicCreate(BaseModel):
    """Model for creating a topic."""
    name: str
    keywords: List[str] = []


class TopicUpdate(BaseModel):
    """Model for updating a topic."""
    name: Optional[str] = None
    keywords: Optional[List[str]] = None


class UserCreate(BaseModel):
    """Model for creating a user."""
    username: str
    email: str
    password: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    """Model for updating a user."""
    email: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_subscriber: Optional[bool] = None


# API endpoints for digests
@router.get("/digests")
async def get_digests() -> List[Dict]:
    """Get all digests."""
    digest_repo = DigestRepository()
    digests = await digest_repo.get_digests()
    return [digest.to_dict() for digest in digests]


@router.get("/digests/{digest_id}")
async def get_digest(digest_id: int) -> Dict:
    """Get a digest by ID."""
    digest_repo = DigestRepository()
    digest = await digest_repo.get_digest(digest_id)
    
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Digest not found: {digest_id}"
        )
    
    return digest.to_dict()


@router.post("/digests")
async def create_digest(digest: DigestCreate) -> Dict:
    """Create a new digest."""
    try:
        # Generate the digest
        result = await generate_digest(
            title=digest.title,
            description=digest.description,
            start_date=digest.start_date,
            end_date=digest.end_date,
            topic_ids=digest.topics,
            source_ids=digest.sources
        )
        
        return result
    except Exception as e:
        logger.error(f"Error creating digest: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating digest: {str(e)}"
        )


@router.put("/digests/{digest_id}")
async def update_digest(digest_id: int, digest: DigestUpdate) -> Dict:
    """Update a digest."""
    digest_repo = DigestRepository()
    existing_digest = await digest_repo.get_digest(digest_id)
    
    if not existing_digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Digest not found: {digest_id}"
        )
    
    # Update the digest
    update_data = {k: v for k, v in digest.dict().items() if v is not None}
    updated_digest = await digest_repo.update_digest(digest_id=digest_id, **update_data)
    
    return updated_digest.to_dict()


@router.delete("/digests/{digest_id}")
async def delete_digest(digest_id: int) -> Dict:
    """Delete a digest."""
    digest_repo = DigestRepository()
    existing_digest = await digest_repo.get_digest(digest_id)
    
    if not existing_digest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Digest not found: {digest_id}"
        )
    
    # Delete the digest
    await digest_repo.delete_digest(digest_id)
    
    return {"message": f"Digest deleted: {digest_id}"}


@router.post("/digests/{digest_id}/publish")
async def publish_digest_endpoint(digest_id: int) -> Dict:
    """Publish a digest."""
    try:
        # Publish the digest
        result = await publish_digest(digest_id)
        
        return result
    except Exception as e:
        logger.error(f"Error publishing digest: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error publishing digest: {str(e)}"
        )


# API endpoints for sources
@router.get("/sources")
async def get_sources() -> List[Dict]:
    """Get all sources."""
    source_repo = SourceRepository()
    sources = await source_repo.get_sources()
    return [source.to_dict() for source in sources]


@router.get("/sources/{source_id}")
async def get_source(source_id: int) -> Dict:
    """Get a source by ID."""
    source_repo = SourceRepository()
    source = await source_repo.get_source(source_id)
    
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}"
        )
    
    return source.to_dict()


@router.post("/sources")
async def create_source(source: SourceCreate) -> Dict:
    """Create a new source."""
    source_repo = SourceRepository()
    
    # Create the source
    new_source = await source_repo.create_source(
        name=source.name,
        url=source.url,
        enabled=source.enabled
    )
    
    return new_source.to_dict()


@router.put("/sources/{source_id}")
async def update_source(source_id: int, source: SourceUpdate) -> Dict:
    """Update a source."""
    source_repo = SourceRepository()
    existing_source = await source_repo.get_source(source_id)
    
    if not existing_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}"
        )
    
    # Update the source
    update_data = {k: v for k, v in source.dict().items() if v is not None}
    updated_source = await source_repo.update_source(source_id=source_id, **update_data)
    
    return updated_source.to_dict()


@router.delete("/sources/{source_id}")
async def delete_source(source_id: int) -> Dict:
    """Delete a source."""
    source_repo = SourceRepository()
    existing_source = await source_repo.get_source(source_id)
    
    if not existing_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source not found: {source_id}"
        )
    
    # Delete the source
    await source_repo.delete_source(source_id)
    
    return {"message": f"Source deleted: {source_id}"}


# API endpoints for topics
@router.get("/topics")
async def get_topics() -> List[Dict]:
    """Get all topics."""
    topic_repo = TopicRepository()
    topics = await topic_repo.get_topics()
    return [topic.to_dict() for topic in topics]


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: int) -> Dict:
    """Get a topic by ID."""
    topic_repo = TopicRepository()
    topic = await topic_repo.get_topic(topic_id)
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic not found: {topic_id}"
        )
    
    return topic.to_dict()


@router.post("/topics")
async def create_topic(topic: TopicCreate) -> Dict:
    """Create a new topic."""
    topic_repo = TopicRepository()
    
    # Create the topic
    new_topic = await topic_repo.create_topic(
        name=topic.name,
        keywords=topic.keywords
    )
    
    return new_topic.to_dict()


@router.put("/topics/{topic_id}")
async def update_topic(topic_id: int, topic: TopicUpdate) -> Dict:
    """Update a topic."""
    topic_repo = TopicRepository()
    existing_topic = await topic_repo.get_topic(topic_id)
    
    if not existing_topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic not found: {topic_id}"
        )
    
    # Update the topic
    update_data = {k: v for k, v in topic.dict().items() if v is not None}
    updated_topic = await topic_repo.update_topic(topic_id=topic_id, **update_data)
    
    return updated_topic.to_dict()


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: int) -> Dict:
    """Delete a topic."""
    topic_repo = TopicRepository()
    existing_topic = await topic_repo.get_topic(topic_id)
    
    if not existing_topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Topic not found: {topic_id}"
        )
    
    # Delete the topic
    await topic_repo.delete_topic(topic_id)
    
    return {"message": f"Topic deleted: {topic_id}"}


# API endpoints for users
@router.get("/users")
async def get_users() -> List[Dict]:
    """Get all users."""
    user_repo = UserRepository()
    users = await user_repo.get_users()
    return [user.to_dict() for user in users]


@router.get("/users/{user_id}")
async def get_user(user_id: int) -> Dict:
    """Get a user by ID."""
    user_repo = UserRepository()
    user = await user_repo.get_user(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )
    
    return user.to_dict()


@router.post("/users")
async def create_user(user: UserCreate) -> Dict:
    """Create a new user."""
    user_repo = UserRepository()
    
    # Create the user
    new_user = await user_repo.create_user(
        username=user.username,
        email=user.email,
        password=user.password,  # In a real app, this would be hashed
        is_admin=user.is_admin
    )
    
    return new_user.to_dict()


@router.put("/users/{user_id}")
async def update_user(user_id: int, user: UserUpdate) -> Dict:
    """Update a user."""
    user_repo = UserRepository()
    existing_user = await user_repo.get_user(user_id)
    
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )
    
    # Update the user
    update_data = {k: v for k, v in user.dict().items() if v is not None}
    updated_user = await user_repo.update_user(user_id=user_id, **update_data)
    
    return updated_user.to_dict()


@router.delete("/users/{user_id}")
async def delete_user(user_id: int) -> Dict:
    """Delete a user."""
    user_repo = UserRepository()
    existing_user = await user_repo.get_user(user_id)
    
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {user_id}"
        )
    
    # Delete the user
    await user_repo.delete_user(user_id)
    
    return {"message": f"User deleted: {user_id}"}