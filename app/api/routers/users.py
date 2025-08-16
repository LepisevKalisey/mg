from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import get_current_admin, get_current_user
from ..models import UserCreate, UserResponse, UserUpdate

router = APIRouter()


@router.get("/", response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(get_current_admin)):
    """Get all users. Admin only."""
    # In a real application, you would fetch users from the database
    # For now, we'll just return a dummy list
    return [
        UserResponse(
            id=1,
            username="admin",
            email="admin@example.com",
            is_active=True,
            is_admin=True,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        ),
        UserResponse(
            id=2,
            username="user",
            email="user@example.com",
            is_active=True,
            is_admin=False,
            created_at="2023-01-01T00:00:00",
            updated_at="2023-01-01T00:00:00"
        )
    ]


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    # In a real application, you would fetch the user from the database
    # For now, we'll just return a dummy user based on the current user's username
    return UserResponse(
        id=1 if current_user["username"] == "admin" else 2,
        username=current_user["username"],
        email=f"{current_user['username']}@example.com",
        is_active=True,
        is_admin=current_user["username"] == "admin",
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, current_user: dict = Depends(get_current_user)):
    """Get user by ID."""
    # In a real application, you would fetch the user from the database
    # For now, we'll just return a dummy user based on the ID
    if user_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Only admins can view other users
    if user_id != (1 if current_user["username"] == "admin" else 2) and current_user["username"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return UserResponse(
        id=user_id,
        username="admin" if user_id == 1 else "user",
        email="admin@example.com" if user_id == 1 else "user@example.com",
        is_active=True,
        is_admin=user_id == 1,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate, current_user: dict = Depends(get_current_user)):
    """Update user."""
    # In a real application, you would update the user in the database
    # For now, we'll just return a dummy user based on the ID
    if user_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Only admins can update other users
    if user_id != (1 if current_user["username"] == "admin" else 2) and current_user["username"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    return UserResponse(
        id=user_id,
        username=user.username or ("admin" if user_id == 1 else "user"),
        email=user.email or ("admin@example.com" if user_id == 1 else "user@example.com"),
        is_active=user.is_active if user.is_active is not None else True,
        is_admin=user.is_admin if user.is_admin is not None else (user_id == 1),
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-02T00:00:00"
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: dict = Depends(get_current_admin)):
    """Delete user. Admin only."""
    # In a real application, you would delete the user from the database
    # For now, we'll just check if the user exists
    if user_id not in [1, 2]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent deleting the admin user
    if user_id == 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin user"
        )
    
    return None