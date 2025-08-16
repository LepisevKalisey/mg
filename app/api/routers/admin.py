from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_admin

router = APIRouter()


@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_admin)):
    """Get system statistics. Admin only."""
    # In a real application, you would fetch statistics from the database
    # For now, we'll just return a dummy statistics
    return {
        "users": 2,
        "sources": 2,
        "topics": 2,
        "summaries": 2,
        "digests": 2
    }


@router.post("/rebuild-index")
async def rebuild_index(current_user: dict = Depends(get_current_admin)):
    """Rebuild search index. Admin only."""
    # In a real application, you would rebuild the search index
    # For now, we'll just return a success message
    return {"message": "Search index rebuilt successfully"}


@router.post("/clear-cache")
async def clear_cache(current_user: dict = Depends(get_current_admin)):
    """Clear system cache. Admin only."""
    # In a real application, you would clear the cache
    # For now, we'll just return a success message
    return {"message": "Cache cleared successfully"}


@router.post("/trigger-digest")
async def trigger_digest(current_user: dict = Depends(get_current_admin)):
    """Manually trigger digest generation. Admin only."""
    # In a real application, you would trigger the digest generation
    # For now, we'll just return a success message
    return {"message": "Digest generation triggered successfully"}