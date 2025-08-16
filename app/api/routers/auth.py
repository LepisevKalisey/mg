from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.db.sessions import SessionRepository
from app.db.settings import SettingsRepository

from ..auth import auth_handler
from ..models import Token, UserCreate, UserResponse

router = APIRouter()


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return access token."""
    # In a real application, you would validate the user credentials against the database
    # For now, we'll just check a hardcoded username and password
    if form_data.username != "admin" or form_data.password != "password":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = auth_handler.create_access_token(data={"sub": form_data.username})
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    """Register a new user."""
    # In a real application, you would check if the user already exists
    # and store the new user in the database
    # For now, we'll just return a dummy user
    hashed_password = auth_handler.get_password_hash(user.password)
    
    return UserResponse(
        id=1,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at="2023-01-01T00:00:00",
        updated_at="2023-01-01T00:00:00"
    )