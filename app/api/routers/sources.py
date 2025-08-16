from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_admin, get_current_user
from ..models import SourceCreate, SourceResponse, SourceUpdate

router = APIRouter()


@router.get("/", response_model=List[SourceResponse])
async def get_sources(current_user: dict = Depends(get_current_user)):
    """Get all sources."""
    # In a real application, you would fetch sources from the database
    # For now, we'll just return a dummy list
    return [
        SourceResponse(
            id=1,
            name="Telegram Channel 1",
            url="https://t.me/channel1",
            type="telegram",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        SourceResponse(
            id=2,
            name="Telegram Channel 2",
            url="https://t.me/channel2",
            type="telegram",
            is_active=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        )
    ]


@router.post("/", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(source: SourceCreate, current_user: dict = Depends(get_current_admin)):
    """Create a new source. Admin only."""
    # In a real application, you would store the source in the database
    # For now, we'll just return a dummy source
    return SourceResponse(
        id=3,
        name=source.name,
        url=source.url,
        type=source.type,
        is_active=source.is_active,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(source_id: int, current_user: dict = Depends(get_current_user)):
    """Get source by ID."""
    # In a real application, you would fetch the source from the database
    # For now, we'll just return a dummy source based on the ID
    if source_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )
    
    return SourceResponse(
        id=source_id,
        name=f"Telegram Channel {source_id}",
        url=f"https://t.me/channel{source_id}",
        type="telegram",
        is_active=True,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(source_id: int, source: SourceUpdate, current_user: dict = Depends(get_current_admin)):
    """Update source. Admin only."""
    # In a real application, you would update the source in the database
    # For now, we'll just return a dummy source based on the ID
    if source_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )
    
    return SourceResponse(
        id=source_id,
        name=source.name or f"Telegram Channel {source_id}",
        url=source.url or f"https://t.me/channel{source_id}",
        type=source.type or "telegram",
        is_active=source.is_active if source.is_active is not None else True,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-02T00:00:00"
    )


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: int, current_user: dict = Depends(get_current_admin)):
    """Delete source. Admin only."""
    # In a real application, you would delete the source from the database
    # For now, we'll just check if the source exists
    if source_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source not found"
        )
    
    return None