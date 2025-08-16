from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Union

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from app.common.config import load_config
from app.common.logging import setup_logging
from app.db.digests import DigestRepository
from app.db.sources import SourceRepository
from app.db.summaries import SummaryRepository
from app.db.topics import TopicRepository

from .auth import AuthHandler, get_current_user, get_current_admin
from .models import (
    DigestCreate, DigestResponse, DigestUpdate,
    SourceCreate, SourceResponse, SourceUpdate,
    SummaryCreate, SummaryResponse, SummaryUpdate,
    TopicCreate, TopicResponse, TopicUpdate,
    UserCreate, UserResponse, UserUpdate,
    Token, TokenData
)
from .rate_limiter import RateLimiter

logger = setup_logging()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = load_config()
    api_config = config.get("api", {})
    server_config = api_config.get("server", {})
    cors_config = api_config.get("cors", {})
    auth_config = api_config.get("auth", {})
    rate_limit_config = api_config.get("rate_limit", {})
    
    # Create FastAPI app
    app = FastAPI(
        title="MG Digest API",
        description="API for managing MG Digest system",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        debug=server_config.get("debug", False)
    )
    
    # Configure CORS
    if cors_config.get("enabled", True):
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_config.get("allow_origins", ["*"]),
            allow_credentials=cors_config.get("allow_credentials", True),
            allow_methods=cors_config.get("allow_methods", ["*"]),
            allow_headers=cors_config.get("allow_headers", ["*"]),
            max_age=cors_config.get("max_age", 600)
        )
    
    # Configure rate limiting
    if rate_limit_config.get("enabled", True):
        rate_limiter = RateLimiter(
            requests=rate_limit_config.get("requests", 100),
            window=rate_limit_config.get("window", 60)
        )
        
        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            client_ip = request.client.host
            if not rate_limiter.is_allowed(client_ip):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded"}
                )
            return await call_next(request)
    
    # Configure authentication
    auth_handler = AuthHandler(
        secret_key=os.environ.get("MASTER_KEY", "default-insecure-key"),
        algorithm=auth_config.get("algorithm", "HS256"),
        access_token_expire_minutes=auth_config.get("access_token_expire_minutes", 30)
    )
    
    # Exception handlers
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )
    
    # Include routers
    from .routers import admin, auth, digests, sources, summaries, topics, users
    
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(digests.router, prefix="/api/digests", tags=["digests"])
    app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
    app.include_router(summaries.router, prefix="/api/summaries", tags=["summaries"])
    app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
    app.include_router(users.router, prefix="/api/users", tags=["users"])
    
    @app.get("/api/health")
    async def health_check():
        return {"status": "ok"}
    
    return app


async def run_app():
    """Run the FastAPI application using uvicorn."""
    import uvicorn
    
    config = load_config()
    api_config = config.get("api", {})
    server_config = api_config.get("server", {})
    
    host = server_config.get("host", "0.0.0.0")
    port = int(os.environ.get("API_PORT", server_config.get("port", 8000)))
    workers = server_config.get("workers", 1)
    
    logger.info(f"Starting API server on {host}:{port} with {workers} workers")
    
    config = uvicorn.Config(
        "app.api.app:create_app()",
        host=host,
        port=port,
        workers=workers,
        log_level="info",
        reload=server_config.get("debug", False),
        factory=True
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_app())