from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_admin, get_current_user
from ..models import DigestCreate, DigestResponse, DigestUpdate

router = APIRouter()


@router.get("/", response_model=List[DigestResponse])
async def get_digests(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get all digests with pagination."""
    # In a real application, you would fetch digests from the database
    # For now, we'll just return a dummy list
    return [
        DigestResponse(
            id=1,
            title="Daily Digest - 2023-01-01",
            description="Daily digest for January 1, 2023",
            content="This is the content of the digest",
            published=True,
            publish_date="2023-01-01T12:00:00",
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        DigestResponse(
            id=2,
            title="Daily Digest - 2023-01-02",
            description="Daily digest for January 2, 2023",
            content="This is the content of the digest",
            published=True,
            publish_date="2023-01-02T12:00:00",
            created_at="2023-01-02T00:00:00",
            updated_at="2023-01-02T00:00:00"
        )
    ]


@router.post("/", response_model=DigestResponse, status_code=status.HTTP_201_CREATED)
async def create_digest(digest: DigestCreate, current_user: dict = Depends(get_current_admin)):
    """Create a new digest. Admin only."""
    # In a real application, you would store the digest in the database
    # For now, we'll just return a dummy digest
    return DigestResponse(
        id=3,
        title=digest.title,
        description=digest.description,
        content=digest.content,
        published=digest.published,
        publish_date=digest.publish_date,
        created_at="2023-01-03T00:00:00",
        updated_at="2023-01-03T00:00:00"
    )


@router.get("/{digest_id}", response_model=DigestResponse)
async def get_digest(digest_id: int, current_user: dict = Depends(get_current_user)):
    """Get digest by ID."""
    # In a real application, you would fetch the digest from the database
    # For now, we'll just return a dummy digest based on the ID
    if digest_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found"
        )
    
    return DigestResponse(
        id=digest_id,
        title=f"Daily Digest - 2023-01-{digest_id:02d}",
        description=f"Daily digest for January {digest_id}, 2023",
        content="This is the content of the digest",
        published=True,
        publish_date=f"2023-01-{digest_id:02d}T12:00:00",
        created_at=f"2023-01-{digest_id:02d}T00:00:00",
        updated_at=f"2023-01-{digest_id:02d}T00:00:00"
    )


@router.put("/{digest_id}", response_model=DigestResponse)
async def update_digest(digest_id: int, digest: DigestUpdate, current_user: dict = Depends(get_current_admin)):
    """Update digest. Admin only."""
    # In a real application, you would update the digest in the database
    # For now, we'll just return a dummy digest based on the ID
    if digest_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found"
        )
    
    return DigestResponse(
        id=digest_id,
        title=digest.title or f"Daily Digest - 2023-01-{digest_id:02d}",
        description=digest.description or f"Daily digest for January {digest_id}, 2023",
        content=digest.content or "This is the content of the digest",
        published=digest.published if digest.published is not None else True,
        publish_date=digest.publish_date or f"2023-01-{digest_id:02d}T12:00:00",
        created_at=f"2023-01-{digest_id:02d}T00:00:00",
        updated_at="2023-01-03T00:00:00"
    )


@router.delete("/{digest_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_digest(digest_id: int, current_user: dict = Depends(get_current_admin)):
    """Delete digest. Admin only."""
    # In a real application, you would delete the digest from the database
    # For now, we'll just check if the digest exists
    if digest_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found"
        )
    
    return None


@router.post("/{digest_id}/publish", response_model=DigestResponse)
async def publish_digest(digest_id: int, current_user: dict = Depends(get_current_admin)):
    """Publish a digest. Admin only."""
    # In a real application, you would update the digest in the database
    # For now, we'll just return a dummy digest based on the ID
    if digest_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Digest not found"
        )
    
    return DigestResponse(
        id=digest_id,
        title=f"Daily Digest - 2023-01-{digest_id:02d}",
        description=f"Daily digest for January {digest_id}, 2023",
        content="This is the content of the digest",
        published=True,
        publish_date=f"2023-01-{digest_id:02d}T12:00:00",
        created_at=f"2023-01-{digest_id:02d}T00:00:00",
        updated_at="2023-01-03T00:00:00"
    )