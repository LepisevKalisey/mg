"""Summaries database module."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from app.db import Database, get_db


class SummaryStatus(str, Enum):
    """Status of a summary."""

    PENDING = "pending"  # Waiting to be processed
    PROCESSING = "processing"  # Being processed by LLM
    COMPLETED = "completed"  # Successfully processed
    FAILED = "failed"  # Processing failed
    APPROVED = "approved"  # Approved by moderator
    REJECTED = "rejected"  # Rejected by moderator


class Summary:
    """Summary model."""

    def __init__(
        self,
        id: Optional[int] = None,
        topic_id: int = 0,
        raw_post_id: int = 0,
        title: str = "",
        content: str = "",
        status: str = SummaryStatus.PENDING,
        error: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a summary.

        Args:
            id: Summary ID.
            topic_id: Topic ID.
            raw_post_id: Raw post ID.
            title: Summary title.
            content: Summary content.
            status: Summary status.
            error: Error message if status is FAILED.
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.topic_id = topic_id
        self.raw_post_id = raw_post_id
        self.title = title
        self.content = content
        self.status = status
        self.error = error
        self.created_at = created_at
        self.updated_at = updated_at


class SummariesRepository:
    """Repository for summaries table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, summary_id: int) -> Optional[Summary]:
        """Get a summary by ID.

        Args:
            summary_id: Summary ID.

        Returns:
            Summary or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE id = :id
            """,
            {"id": summary_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Summary(
            id=row[0],
            topic_id=row[1],
            raw_post_id=row[2],
            title=row[3],
            content=row[4],
            status=row[5],
            error=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def get_by_post(self, raw_post_id: int) -> Optional[Summary]:
        """Get a summary by raw post ID.

        Args:
            raw_post_id: Raw post ID.

        Returns:
            Summary or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE raw_post_id = :raw_post_id
            """,
            {"raw_post_id": raw_post_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Summary(
            id=row[0],
            topic_id=row[1],
            raw_post_id=row[2],
            title=row[3],
            content=row[4],
            status=row[5],
            error=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def get_by_topic(self, topic_id: int, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Summary]:
        """Get summaries by topic ID.

        Args:
            topic_id: Topic ID.
            status: Filter by status (optional).
            limit: Maximum number of summaries to return.
            offset: Offset for pagination.

        Returns:
            List of summaries.
        """
        query = """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE topic_id = :topic_id
        """
        params = {"topic_id": topic_id, "limit": limit, "offset": offset}

        if status is not None:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        rows = self.db.execute(query, params)
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    def get_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Summary]:
        """Get summaries by status.

        Args:
            status: Summary status.
            limit: Maximum number of summaries to return.
            offset: Offset for pagination.

        Returns:
            List of summaries.
        """
        rows = self.db.execute(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE status = :status
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"status": status, "limit": limit, "offset": offset},
        )
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    def get_pending(self, limit: int = 10) -> List[Summary]:
        """Get pending summaries.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of pending summaries.
        """
        return self.get_by_status(SummaryStatus.PENDING, limit)

    def get_latest(self, limit: int = 10) -> List[Summary]:
        """Get latest completed or approved summaries.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of summaries.
        """
        rows = self.db.execute(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries 
            WHERE status IN (:completed, :approved)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {
                "completed": SummaryStatus.COMPLETED,
                "approved": SummaryStatus.APPROVED,
                "limit": limit,
            },
        )
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    def create(self, summary: Summary) -> Summary:
        """Create a new summary.

        Args:
            summary: Summary to create.

        Returns:
            Created summary with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO summaries (topic_id, raw_post_id, title, content, status, error)
            VALUES (:topic_id, :raw_post_id, :title, :content, :status, :error)
            RETURNING id, created_at, updated_at
            """,
            {
                "topic_id": summary.topic_id,
                "raw_post_id": summary.raw_post_id,
                "title": summary.title,
                "content": summary.content,
                "status": summary.status,
                "error": summary.error,
            },
        )
        summary.id = rows[0][0]
        summary.created_at = rows[0][1]
        summary.updated_at = rows[0][2]
        return summary

    def update(self, summary: Summary) -> Summary:
        """Update an existing summary.

        Args:
            summary: Summary to update.

        Returns:
            Updated summary.

        Raises:
            ValueError: If summary ID is not set.
        """
        if summary.id is None:
            raise ValueError("Summary ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE summaries
            SET topic_id = :topic_id, raw_post_id = :raw_post_id, title = :title, 
                content = :content, status = :status, error = :error, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": summary.id,
                "topic_id": summary.topic_id,
                "raw_post_id": summary.raw_post_id,
                "title": summary.title,
                "content": summary.content,
                "status": summary.status,
                "error": summary.error,
            },
        )
        return summary

    def update_status(self, summary_id: int, status: str, error: Optional[str] = None) -> None:
        """Update the status of a summary.

        Args:
            summary_id: Summary ID.
            status: New status.
            error: Error message if status is FAILED.
        """
        self.db.execute_with_transaction(
            """
            UPDATE summaries
            SET status = :status, error = :error, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": summary_id, "status": status, "error": error},
        )

    def delete(self, summary_id: int) -> None:
        """Delete a summary.

        Args:
            summary_id: Summary ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM summaries WHERE id = :id",
            {"id": summary_id},
        )

    # Async methods

    async def get_async(self, summary_id: int) -> Optional[Summary]:
        """Get a summary by ID asynchronously.

        Args:
            summary_id: Summary ID.

        Returns:
            Summary or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE id = :id
            """,
            {"id": summary_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Summary(
            id=row[0],
            topic_id=row[1],
            raw_post_id=row[2],
            title=row[3],
            content=row[4],
            status=row[5],
            error=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    async def get_by_post_async(self, raw_post_id: int) -> Optional[Summary]:
        """Get a summary by raw post ID asynchronously.

        Args:
            raw_post_id: Raw post ID.

        Returns:
            Summary or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE raw_post_id = :raw_post_id
            """,
            {"raw_post_id": raw_post_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Summary(
            id=row[0],
            topic_id=row[1],
            raw_post_id=row[2],
            title=row[3],
            content=row[4],
            status=row[5],
            error=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    async def get_by_topic_async(self, topic_id: int, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Summary]:
        """Get summaries by topic ID asynchronously.

        Args:
            topic_id: Topic ID.
            status: Filter by status (optional).
            limit: Maximum number of summaries to return.
            offset: Offset for pagination.

        Returns:
            List of summaries.
        """
        query = """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE topic_id = :topic_id
        """
        params = {"topic_id": topic_id, "limit": limit, "offset": offset}

        if status is not None:
            query += " AND status = :status"
            params["status"] = status

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        rows = await self.db.execute_async(query, params)
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    async def get_by_status_async(self, status: str, limit: int = 100, offset: int = 0) -> List[Summary]:
        """Get summaries by status asynchronously.

        Args:
            status: Summary status.
            limit: Maximum number of summaries to return.
            offset: Offset for pagination.

        Returns:
            List of summaries.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries WHERE status = :status
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"status": status, "limit": limit, "offset": offset},
        )
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    async def get_pending_async(self, limit: int = 10) -> List[Summary]:
        """Get pending summaries asynchronously.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of pending summaries.
        """
        return await self.get_by_status_async(SummaryStatus.PENDING, limit)

    async def get_latest_async(self, limit: int = 10) -> List[Summary]:
        """Get latest completed or approved summaries asynchronously.

        Args:
            limit: Maximum number of summaries to return.

        Returns:
            List of summaries.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, topic_id, raw_post_id, title, content, status, error, created_at, updated_at 
            FROM summaries 
            WHERE status IN (:completed, :approved)
            ORDER BY created_at DESC
            LIMIT :limit
            """,
            {
                "completed": SummaryStatus.COMPLETED,
                "approved": SummaryStatus.APPROVED,
                "limit": limit,
            },
        )
        summaries = []
        for row in rows:
            summaries.append(
                Summary(
                    id=row[0],
                    topic_id=row[1],
                    raw_post_id=row[2],
                    title=row[3],
                    content=row[4],
                    status=row[5],
                    error=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return summaries

    async def create_async(self, summary: Summary) -> Summary:
        """Create a new summary asynchronously.

        Args:
            summary: Summary to create.

        Returns:
            Created summary with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO summaries (topic_id, raw_post_id, title, content, status, error)
            VALUES (:topic_id, :raw_post_id, :title, :content, :status, :error)
            RETURNING id, created_at, updated_at
            """,
            {
                "topic_id": summary.topic_id,
                "raw_post_id": summary.raw_post_id,
                "title": summary.title,
                "content": summary.content,
                "status": summary.status,
                "error": summary.error,
            },
        )
        summary.id = rows[0][0]
        summary.created_at = rows[0][1]
        summary.updated_at = rows[0][2]
        return summary

    async def update_async(self, summary: Summary) -> Summary:
        """Update an existing summary asynchronously.

        Args:
            summary: Summary to update.

        Returns:
            Updated summary.

        Raises:
            ValueError: If summary ID is not set.
        """
        if summary.id is None:
            raise ValueError("Summary ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE summaries
            SET topic_id = :topic_id, raw_post_id = :raw_post_id, title = :title, 
                content = :content, status = :status, error = :error, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": summary.id,
                "topic_id": summary.topic_id,
                "raw_post_id": summary.raw_post_id,
                "title": summary.title,
                "content": summary.content,
                "status": summary.status,
                "error": summary.error,
            },
        )
        return summary

    async def update_status_async(self, summary_id: int, status: str, error: Optional[str] = None) -> None:
        """Update the status of a summary asynchronously.

        Args:
            summary_id: Summary ID.
            status: New status.
            error: Error message if status is FAILED.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE summaries
            SET status = :status, error = :error, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": summary_id, "status": status, "error": error},
        )

    async def delete_async(self, summary_id: int) -> None:
        """Delete a summary asynchronously.

        Args:
            summary_id: Summary ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM summaries WHERE id = :id",
            {"id": summary_id},
        )