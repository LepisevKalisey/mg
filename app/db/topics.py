"""Topics database module."""

from datetime import datetime
from typing import List, Optional

from app.db import Database, get_db


class Topic:
    """Topic model."""

    def __init__(
        self,
        id: Optional[int] = None,
        title: str = "",
        description: Optional[str] = None,
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a topic.

        Args:
            id: Topic ID.
            title: Topic title.
            description: Topic description (optional).
            is_active: Whether the topic is active.
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.title = title
        self.description = description
        self.is_active = is_active
        self.created_at = created_at
        self.updated_at = updated_at


class TopicsRepository:
    """Repository for topics table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, topic_id: int) -> Optional[Topic]:
        """Get a topic by ID.

        Args:
            topic_id: Topic ID.

        Returns:
            Topic or None if not found.
        """
        rows = self.db.execute(
            "SELECT id, title, description, is_active, created_at, updated_at FROM topics WHERE id = :id",
            {"id": topic_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Topic(
            id=row[0],
            title=row[1],
            description=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_by_title(self, title: str) -> Optional[Topic]:
        """Get a topic by title.

        Args:
            title: Topic title.

        Returns:
            Topic or None if not found.
        """
        rows = self.db.execute(
            "SELECT id, title, description, is_active, created_at, updated_at FROM topics WHERE title = :title",
            {"title": title},
        )
        if not rows:
            return None

        row = rows[0]
        return Topic(
            id=row[0],
            title=row[1],
            description=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_all(self, active_only: bool = False) -> List[Topic]:
        """Get all topics.

        Args:
            active_only: If True, return only active topics.

        Returns:
            List of topics.
        """
        query = "SELECT id, title, description, is_active, created_at, updated_at FROM topics"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY title"

        rows = self.db.execute(query)
        topics = []
        for row in rows:
            topics.append(
                Topic(
                    id=row[0],
                    title=row[1],
                    description=row[2],
                    is_active=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return topics

    def create(self, topic: Topic) -> Topic:
        """Create a new topic.

        Args:
            topic: Topic to create.

        Returns:
            Created topic with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO topics (title, description, is_active)
            VALUES (:title, :description, :is_active)
            RETURNING id, created_at, updated_at
            """,
            {
                "title": topic.title,
                "description": topic.description,
                "is_active": topic.is_active,
            },
        )
        topic.id = rows[0][0]
        topic.created_at = rows[0][1]
        topic.updated_at = rows[0][2]
        return topic

    def update(self, topic: Topic) -> Topic:
        """Update an existing topic.

        Args:
            topic: Topic to update.

        Returns:
            Updated topic.

        Raises:
            ValueError: If topic ID is not set.
        """
        if topic.id is None:
            raise ValueError("Topic ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE topics
            SET title = :title, description = :description, is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": topic.id,
                "title": topic.title,
                "description": topic.description,
                "is_active": topic.is_active,
            },
        )
        return topic

    def set_active(self, topic_id: int, active: bool = True) -> None:
        """Set a topic as active or inactive.

        Args:
            topic_id: Topic ID.
            active: Whether to set as active or inactive.
        """
        self.db.execute_with_transaction(
            """
            UPDATE topics
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": topic_id, "is_active": active},
        )

    def delete(self, topic_id: int) -> None:
        """Delete a topic.

        Args:
            topic_id: Topic ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM topics WHERE id = :id",
            {"id": topic_id},
        )

    # Async methods

    async def get_async(self, topic_id: int) -> Optional[Topic]:
        """Get a topic by ID asynchronously.

        Args:
            topic_id: Topic ID.

        Returns:
            Topic or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT id, title, description, is_active, created_at, updated_at FROM topics WHERE id = :id",
            {"id": topic_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Topic(
            id=row[0],
            title=row[1],
            description=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_by_title_async(self, title: str) -> Optional[Topic]:
        """Get a topic by title asynchronously.

        Args:
            title: Topic title.

        Returns:
            Topic or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT id, title, description, is_active, created_at, updated_at FROM topics WHERE title = :title",
            {"title": title},
        )
        if not rows:
            return None

        row = rows[0]
        return Topic(
            id=row[0],
            title=row[1],
            description=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_all_async(self, active_only: bool = False) -> List[Topic]:
        """Get all topics asynchronously.

        Args:
            active_only: If True, return only active topics.

        Returns:
            List of topics.
        """
        query = "SELECT id, title, description, is_active, created_at, updated_at FROM topics"
        if active_only:
            query += " WHERE is_active = TRUE"
        query += " ORDER BY title"

        rows = await self.db.execute_async(query)
        topics = []
        for row in rows:
            topics.append(
                Topic(
                    id=row[0],
                    title=row[1],
                    description=row[2],
                    is_active=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return topics

    async def create_async(self, topic: Topic) -> Topic:
        """Create a new topic asynchronously.

        Args:
            topic: Topic to create.

        Returns:
            Created topic with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO topics (title, description, is_active)
            VALUES (:title, :description, :is_active)
            RETURNING id, created_at, updated_at
            """,
            {
                "title": topic.title,
                "description": topic.description,
                "is_active": topic.is_active,
            },
        )
        topic.id = rows[0][0]
        topic.created_at = rows[0][1]
        topic.updated_at = rows[0][2]
        return topic

    async def update_async(self, topic: Topic) -> Topic:
        """Update an existing topic asynchronously.

        Args:
            topic: Topic to update.

        Returns:
            Updated topic.

        Raises:
            ValueError: If topic ID is not set.
        """
        if topic.id is None:
            raise ValueError("Topic ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE topics
            SET title = :title, description = :description, is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": topic.id,
                "title": topic.title,
                "description": topic.description,
                "is_active": topic.is_active,
            },
        )
        return topic

    async def set_active_async(self, topic_id: int, active: bool = True) -> None:
        """Set a topic as active or inactive asynchronously.

        Args:
            topic_id: Topic ID.
            active: Whether to set as active or inactive.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE topics
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": topic_id, "is_active": active},
        )

    async def delete_async(self, topic_id: int) -> None:
        """Delete a topic asynchronously.

        Args:
            topic_id: Topic ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM topics WHERE id = :id",
            {"id": topic_id},
        )