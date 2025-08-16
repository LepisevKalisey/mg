from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_admin, get_current_user
from ..models import SummaryCreate, SummaryResponse, SummaryUpdate

router = APIRouter()


@router.get("/", response_model=List[SummaryResponse])
async def get_summaries(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    topic_id: int = None,
    source_id: int = None,
    current_user: dict = Depends(get_current_user)
):
    """Get all summaries with pagination and optional filtering."""
    # In a real application, you would fetch summaries from the database
    # For now, we'll just return a dummy list
    summaries = [
        SummaryResponse(
            id=1,
            title="Summary 1",
            content="This is the content of summary 1",
            source_id=1,
            source_name="Telegram Channel 1",
            topic_id=1,
            topic_name="Technology",
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        SummaryResponse(
            id=2,
            title="Summary 2",
            content="This is the content of summary 2",
            source_id=2,
            source_name="Telegram Channel 2",
            topic_id=2,
            topic_name="Business",
            created_at="2023-01-02T00:00:00",
            updated_at="2023-01-02T00:00:00"
        )
    ]
    
    # Filter by topic_id if provided
    if topic_id is not None:
        summaries = [s for s in summaries if s.topic_id == topic_id]
    
    # Filter by source_id if provided
    if source_id is not None:
        summaries = [s for s in summaries if s.source_id == source_id]
    
    return summaries


@router.post("/", response_model=SummaryResponse, status_code=status.HTTP_201_CREATED)
async def create_summary(summary: SummaryCreate, current_user: dict = Depends(get_current_admin)):
    """Create a new summary. Admin only."""
    # In a real application, you would store the summary in the database
    # For now, we'll just return a dummy summary
    return SummaryResponse(
        id=3,
        title=summary.title,
        content=summary.content,
        source_id=summary.source_id,
        source_name="Telegram Channel 1" if summary.source_id == 1 else "Telegram Channel 2",
        topic_id=summary.topic_id,
        topic_name="Technology" if summary.topic_id == 1 else "Business",
        created_at="2023-01-03T00:00:00",
        updated_at="2023-01-03T00:00:00"
    )


@router.get("/{summary_id}", response_model=SummaryResponse)
async def get_summary(summary_id: int, current_user: dict = Depends(get_current_user)):
    """Get summary by ID."""
    # In a real application, you would fetch the summary from the database
    # For now, we'll just return a dummy summary based on the ID
    if summary_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found"
        )
    
    summaries = {
        1: SummaryResponse(
            id=1,
            title="Summary 1",
            content="This is the content of summary 1",
            source_id=1,
            source_name="Telegram Channel 1",
            topic_id=1,
            topic_name="Technology",
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        2: SummaryResponse(
            id=2,
            title="Summary 2",
            content="This is the content of summary 2",
            source_id=2,
            source_name="Telegram Channel 2",
            topic_id=2,
            topic_name="Business",
            created_at="2023-01-02T00:00:00",
            updated_at="2023-01-02T00:00:00"
        )
    }
    
    return summaries[summary_id]


@router.put("/{summary_id}", response_model=SummaryResponse)
async def update_summary(summary_id: int, summary: SummaryUpdate, current_user: dict = Depends(get_current_admin)):
    """Update summary. Admin only."""
    # In a real application, you would update the summary in the database
    # For now, we'll just return a dummy summary based on the ID
    if summary_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found"
        )
    
    summaries = {
        1: {
            "title": "Summary 1",
            "content": "This is the content of summary 1",
            "source_id": 1,
            "topic_id": 1
        },
        2: {
            "title": "Summary 2",
            "content": "This is the content of summary 2",
            "source_id": 2,
            "topic_id": 2
        }
    }
    
    return SummaryResponse(
        id=summary_id,
        title=summary.title or summaries[summary_id]["title"],
        content=summary.content or summaries[summary_id]["content"],
        source_id=summary.source_id or summaries[summary_id]["source_id"],
        source_name="Telegram Channel 1" if (summary.source_id or summaries[summary_id]["source_id"]) == 1 else "Telegram Channel 2",
        topic_id=summary.topic_id or summaries[summary_id]["topic_id"],
        topic_name="Technology" if (summary.topic_id or summaries[summary_id]["topic_id"]) == 1 else "Business",
        created_at=f"2023-01-{summary_id:02d}T00:00:00",
        updated_at="2023-01-03T00:00:00"
    )


@router.delete("/{summary_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_summary(summary_id: int, current_user: dict = Depends(get_current_admin)):
    """Delete summary. Admin only."""
    # In a real application, you would delete the summary from the database
    # For now, we'll just check if the summary exists
    if summary_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Summary not found"
        )
    
    return None