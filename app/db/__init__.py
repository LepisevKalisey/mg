"""Database module for the application."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Row
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.common.config import Settings
from app.common.errors import DatabaseError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Database:
    """Database interface for the application."""

    def __init__(self, settings: Settings):
        """Initialize the database connection.

        Args:
            settings: Application settings.
        """
        self.settings = settings
        self.engine: Optional[Engine] = None
        self.async_engine: Optional[AsyncEngine] = None

    def connect(self) -> None:
        """Connect to the database."""
        try:
            self.engine = create_engine(self.settings.db_url)
            # Convert postgresql:// to postgresql+asyncpg:// for async connection
            async_url = self.settings.db_url
            if async_url.startswith('postgresql://'):
                async_url = async_url.replace('postgresql://', 'postgresql+asyncpg://')
            self.async_engine = create_async_engine(async_url, poolclass=NullPool)
            logger.info("Connected to database")
        except SQLAlchemyError as e:
            logger.error(f"Failed to connect to database: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close the database connection."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
        if self.async_engine:
            self.async_engine.dispose()
            self.async_engine = None
        logger.info("Closed database connection")

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Execute a SQL query and return the results.

        Args:
            query: SQL query to execute.
            params: Query parameters.

        Returns:
            List of rows returned by the query.

        Raises:
            DatabaseError: If the query fails.
        """
        if not self.engine:
            self.connect()
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                return list(result)
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute query: {e}")
            raise DatabaseError(f"Failed to execute query: {e}") from e

    def execute_with_transaction(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Execute a SQL query within a transaction and return the results.

        Args:
            query: SQL query to execute.
            params: Query parameters.

        Returns:
            List of rows returned by the query.

        Raises:
            DatabaseError: If the query fails.
        """
        if not self.engine:
            self.connect()
        try:
            with self.engine.begin() as conn:
                result = conn.execute(text(query), params or {})
                return list(result)
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute query with transaction: {e}")
            raise DatabaseError(f"Failed to execute query with transaction: {e}") from e

    async def execute_async(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Execute a SQL query asynchronously and return the results.

        Args:
            query: SQL query to execute.
            params: Query parameters.

        Returns:
            List of rows returned by the query.

        Raises:
            DatabaseError: If the query fails.
        """
        if not self.async_engine:
            self.connect()
        try:
            async with self.async_engine.connect() as conn:
                result = await conn.execute(text(query), params or {})
                return list(result)
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute async query: {e}")
            raise DatabaseError(f"Failed to execute async query: {e}") from e

    async def execute_with_transaction_async(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Row]:
        """Execute a SQL query within a transaction asynchronously and return the results.

        Args:
            query: SQL query to execute.
            params: Query parameters.

        Returns:
            List of rows returned by the query.

        Raises:
            DatabaseError: If the query fails.
        """
        if not self.async_engine:
            self.connect()
        try:
            async with self.async_engine.begin() as conn:
                result = await conn.execute(text(query), params or {})
                return list(result)
        except SQLAlchemyError as e:
            logger.error(f"Failed to execute async query with transaction: {e}")
            raise DatabaseError(f"Failed to execute async query with transaction: {e}") from e


# Singleton instance
_db_instance: Optional[Database] = None


def get_db(settings: Optional[Settings] = None) -> Database:
    """Get the database instance.

    Args:
        settings: Application settings. If not provided, the instance must already exist.

    Returns:
        Database instance.

    Raises:
        ValueError: If settings is not provided and the instance does not exist.
    """
    global _db_instance
    if _db_instance is None:
        if settings is None:
            raise ValueError("Settings must be provided when initializing the database")
        _db_instance = Database(settings)
        _db_instance.connect()
    return _db_instance


def close_db() -> None:
    """Close the database connection."""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
        _db_instance = None