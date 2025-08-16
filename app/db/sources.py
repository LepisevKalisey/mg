"""Sources database module."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from app.db import Database, get_db


class SourceType(str, Enum):
    """Types of sources."""

    TELEGRAM_CHANNEL = "telegram_channel"
    TELEGRAM_GROUP = "telegram_group"
    TELEGRAM_USER = "telegram_user"


class TrustLevel(int, Enum):
    """Trust levels for sources."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Source:
    """Source model."""

    def __init__(
        self,
        id: Optional[int] = None,
        type: str = "",
        tg_id: int = 0,
        username: Optional[str] = None,
        title: str = "",
        enabled: bool = True,
        trust_level: Optional[int] = None,
        added_by: Optional[int] = None,
        added_at: Optional[datetime] = None,
    ):
        """Initialize a source.

        Args:
            id: Source ID.
            type: Source type.
            tg_id: Telegram channel/group/user ID.
            username: Telegram username (optional).
            title: Source title/name.
            enabled: Whether the source is enabled.
            trust_level: Trust level of the source.
            added_by: ID of the user who added this source.
            added_at: Timestamp when the source was added.
        """
        self.id = id
        self.type = type
        self.tg_id = tg_id
        self.username = username
        self.title = title
        self.enabled = enabled
        self.trust_level = trust_level
        self.added_by = added_by
        self.added_at = added_at


class SourcesRepository:
    """Repository for sources table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, source_id: int) -> Optional[Source]:
        """Get a source by ID.

        Args:
            source_id: Source ID.

        Returns:
            Source or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources WHERE id = :id
            """,
            {"id": source_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Source(
            id=row[0],
            type=row[1],
            tg_id=row[2],
            username=row[3],
            title=row[4],
            enabled=row[5],
            trust_level=row[6],
            added_by=row[7],
            added_at=row[8],
        )

    def get_by_tg_id(self, tg_id: int) -> Optional[Source]:
        """Get a source by Telegram ID.

        Args:
            tg_id: Telegram channel/group/user ID.

        Returns:
            Source or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources WHERE tg_id = :tg_id
            """,
            {"tg_id": tg_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Source(
            id=row[0],
            type=row[1],
            tg_id=row[2],
            username=row[3],
            title=row[4],
            enabled=row[5],
            trust_level=row[6],
            added_by=row[7],
            added_at=row[8],
        )

    def get_all(self, enabled_only: bool = False) -> List[Source]:
        """Get all sources.

        Args:
            enabled_only: If True, return only enabled sources.

        Returns:
            List of sources.
        """
        query = """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources
        """
        if enabled_only:
            query += " WHERE enabled = TRUE"
        query += " ORDER BY title"

        rows = self.db.execute(query)
        sources = []
        for row in rows:
            sources.append(
                Source(
                    id=row[0],
                    type=row[1],
                    tg_id=row[2],
                    username=row[3],
                    title=row[4],
                    enabled=row[5],
                    trust_level=row[6],
                    added_by=row[7],
                    added_at=row[8],
                )
            )
        return sources

    def create(self, source: Source) -> Source:
        """Create a new source.

        Args:
            source: Source to create.

        Returns:
            Created source with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO sources (tg_id, username, title, enabled, trust_level, added_by)
            VALUES (:tg_id, :username, :title, :enabled, :trust_level, :added_by)
            RETURNING id, added_at
            """,
            {
                "tg_id": source.tg_id,
                "username": source.username,
                "title": source.title,
                "enabled": source.enabled,
                "trust_level": source.trust_level,
                "added_by": source.added_by,
            },
        )
        source.id = rows[0][0]
        source.added_at = rows[0][1]
        return source

    def update(self, source: Source) -> Source:
        """Update an existing source.

        Args:
            source: Source to update.

        Returns:
            Updated source.

        Raises:
            ValueError: If source ID is not set.
        """
        if source.id is None:
            raise ValueError("Source ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE sources
            SET tg_id = :tg_id, username = :username, title = :title, 
                enabled = :enabled, trust_level = :trust_level
            WHERE id = :id
            """,
            {
                "id": source.id,
                "tg_id": source.tg_id,
                "username": source.username,
                "title": source.title,
                "enabled": source.enabled,
                "trust_level": source.trust_level,
            },
        )
        return source

    def set_enabled(self, source_id: int, enabled: bool = True) -> None:
        """Set a source as enabled or disabled.

        Args:
            source_id: Source ID.
            enabled: Whether to set as enabled or disabled.
        """
        self.db.execute_with_transaction(
            """
            UPDATE sources
            SET enabled = :enabled
            WHERE id = :id
            """,
            {"id": source_id, "enabled": enabled},
        )

    def delete(self, source_id: int) -> None:
        """Delete a source.

        Args:
            source_id: Source ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM sources WHERE id = :id",
            {"id": source_id},
        )

    # Async methods

    async def get_async(self, source_id: int) -> Optional[Source]:
        """Get a source by ID asynchronously.

        Args:
            source_id: Source ID.

        Returns:
            Source or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources WHERE id = :id
            """,
            {"id": source_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Source(
            id=row[0],
            type=row[1],
            tg_id=row[2],
            username=row[3],
            title=row[4],
            enabled=row[5],
            trust_level=row[6],
            added_by=row[7],
            added_at=row[8],
        )

    async def get_by_tg_id_async(self, tg_id: int) -> Optional[Source]:
        """Get a source by Telegram ID asynchronously.

        Args:
            tg_id: Telegram channel/group/user ID.

        Returns:
            Source or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources WHERE tg_id = :tg_id
            """,
            {"tg_id": tg_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Source(
            id=row[0],
            type=row[1],
            tg_id=row[2],
            username=row[3],
            title=row[4],
            enabled=row[5],
            trust_level=row[6],
            added_by=row[7],
            added_at=row[8],
        )

    async def get_all_async(self, enabled_only: bool = False) -> List[Source]:
        """Get all sources asynchronously.

        Args:
            enabled_only: If True, return only enabled sources.

        Returns:
            List of sources.
        """
        query = """
            SELECT id, 'telegram_channel' as type, tg_id, username, title, enabled, trust_level, added_by, added_at 
            FROM sources
        """
        if enabled_only:
            query += " WHERE enabled = TRUE"
        query += " ORDER BY title"

        rows = await self.db.execute_async(query)
        sources = []
        for row in rows:
            sources.append(
                Source(
                    id=row[0],
                    type=row[1],
                    tg_id=row[2],
                    username=row[3],
                    title=row[4],
                    enabled=row[5],
                    trust_level=row[6],
                    added_by=row[7],
                    added_at=row[8],
                )
            )
        return sources

    async def create_async(self, source: Source) -> Source:
        """Create a new source asynchronously.

        Args:
            source: Source to create.

        Returns:
            Created source with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO sources (tg_id, username, title, enabled, trust_level, added_by)
            VALUES (:tg_id, :username, :title, :enabled, :trust_level, :added_by)
            RETURNING id, added_at
            """,
            {
                "tg_id": source.tg_id,
                "username": source.username,
                "title": source.title,
                "enabled": source.enabled,
                "trust_level": source.trust_level,
                "added_by": source.added_by,
            },
        )
        source.id = rows[0][0]
        source.added_at = rows[0][1]
        return source

    async def update_async(self, source: Source) -> Source:
        """Update an existing source asynchronously.

        Args:
            source: Source to update.

        Returns:
            Updated source.

        Raises:
            ValueError: If source ID is not set.
        """
        if source.id is None:
            raise ValueError("Source ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE sources
            SET tg_id = :tg_id, username = :username, title = :title, 
                enabled = :enabled, trust_level = :trust_level
            WHERE id = :id
            """,
            {
                "id": source.id,
                "tg_id": source.tg_id,
                "username": source.username,
                "title": source.title,
                "enabled": source.enabled,
                "trust_level": source.trust_level,
            },
        )
        return source

    async def set_enabled_async(self, source_id: int, enabled: bool = True) -> None:
        """Set a source as enabled or disabled asynchronously.

        Args:
            source_id: Source ID.
            enabled: Whether to set as enabled or disabled.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE sources
            SET enabled = :enabled
            WHERE id = :id
            """,
            {"id": source_id, "enabled": enabled},
        )

    async def delete_async(self, source_id: int) -> None:
        """Delete a source asynchronously.

        Args:
            source_id: Source ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM sources WHERE id = :id",
            {"id": source_id},
        )