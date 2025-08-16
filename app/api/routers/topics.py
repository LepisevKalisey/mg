from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_admin, get_current_user
from ..models import TopicCreate, TopicResponse, TopicUpdate

router = APIRouter()


@router.get("/", response_model=List[TopicResponse])
async def get_topics(current_user: dict = Depends(get_current_user)):
    """Get all topics."""
    # In a real application, you would fetch topics from the database
    # For now, we'll just return a dummy list
    return [
        TopicResponse(
            id=1,
            name="Technology",
            description="Technology news and updates",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        TopicResponse(
            id=2,
            name="Business",
            description="Business news and updates",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        )
    ]


@router.post("/", response_model=TopicResponse, status_code=status.HTTP_201_CREATED)
async def create_topic(topic: TopicCreate, current_user: dict = Depends(get_current_admin)):
    """Create a new topic. Admin only."""
    # In a real application, you would store the topic in the database
    # For now, we'll just return a dummy topic
    return TopicResponse(
        id=3,
        name=topic.name,
        description=topic.description,
        is_active=topic.is_active,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: int, current_user: dict = Depends(get_current_user)):
    """Get topic by ID."""
    # In a real application, you would fetch the topic from the database
    # For now, we'll just return a dummy topic based on the ID
    if topic_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    topics = {
        1: TopicResponse(
            id=1,
            name="Technology",
            description="Technology news and updates",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        2: TopicResponse(
            id=2,
            name="Business",
            description="Business news and updates",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        )
    }
    
    return topics[topic_id]


@router.put("/{topic_id}", response_model=TopicResponse)
async def update_topic(topic_id: int, topic: TopicUpdate, current_user: dict = Depends(get_current_admin)):
    """Update topic. Admin only."""
    # In a real application, you would update the topic in the database
    # For now, we'll just return a dummy topic based on the ID
    if topic_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    topics = {
        1: {
            "name": "Technology",
            "description": "Technology news and updates"
        },
        2: {
            "name": "Business",
            "description": "Business news and updates"
        }
    }
    
    return TopicResponse(
        id=topic_id,
        name=topic.name or topics[topic_id]["name"],
        description=topic.description or topics[topic_id]["description"],
        is_active=topic.is_active if topic.is_active is not None else True,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-02T00:00:00"
    )


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: int, current_user: dict = Depends(get_current_admin)):
    """Delete topic. Admin only."""
    # In a real application, you would delete the topic from the database
    # For now, we'll just check if the topic exists
    if topic_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    return None