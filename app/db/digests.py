"""Digests database module."""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Tuple

from app.db import Database, get_db


class DigestStatus(str, Enum):
    """Status of a digest."""

    SCHEDULED = "scheduled"  # Scheduled for future posting
    POSTED = "posted"  # Successfully posted
    FAILED = "failed"  # Posting failed
    CANCELLED = "cancelled"  # Cancelled by user


class Digest:
    """Digest model."""

    def __init__(
        self,
        id: Optional[int] = None,
        scheduled_at: Optional[datetime] = None,
        posted_at: Optional[datetime] = None,
        target_channel_id: str = "",
        status: str = DigestStatus.SCHEDULED,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a digest.

        Args:
            id: Digest ID.
            scheduled_at: When the digest is scheduled to be posted.
            posted_at: When the digest was actually posted.
            target_channel_id: Target channel ID for posting.
            status: Digest status.
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.scheduled_at = scheduled_at
        self.posted_at = posted_at
        self.target_channel_id = target_channel_id
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at


class DigestItem:
    """Digest item model."""

    def __init__(
        self,
        id: Optional[int] = None,
        digest_id: int = 0,
        summary_id: int = 0,
        position: int = 0,
        created_at: Optional[datetime] = None,
    ):
        """Initialize a digest item.

        Args:
            id: Digest item ID.
            digest_id: Digest ID.
            summary_id: Summary ID.
            position: Position in the digest (order).
            created_at: Creation timestamp.
        """
        self.id = id
        self.digest_id = digest_id
        self.summary_id = summary_id
        self.position = position
        self.created_at = created_at


class DigestsRepository:
    """Repository for digests and digest_items tables."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, digest_id: int) -> Optional[Digest]:
        """Get a digest by ID.

        Args:
            digest_id: Digest ID.

        Returns:
            Digest or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests WHERE id = :id
            """,
            {"id": digest_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Digest(
            id=row[0],
            scheduled_at=row[1],
            posted_at=row[2],
            target_channel_id=row[3],
            status=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    def get_scheduled(self, limit: int = 10) -> List[Digest]:
        """Get scheduled digests that are due for posting.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of scheduled digests due for posting.
        """
        rows = self.db.execute(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
            LIMIT :limit
            """,
            {"status": DigestStatus.SCHEDULED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    def get_upcoming(self, limit: int = 10) -> List[Digest]:
        """Get upcoming scheduled digests.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of upcoming scheduled digests.
        """
        rows = self.db.execute(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status AND scheduled_at > NOW()
            ORDER BY scheduled_at ASC
            LIMIT :limit
            """,
            {"status": DigestStatus.SCHEDULED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    def get_recent(self, limit: int = 10) -> List[Digest]:
        """Get recently posted digests.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of recently posted digests.
        """
        rows = self.db.execute(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status
            ORDER BY posted_at DESC
            LIMIT :limit
            """,
            {"status": DigestStatus.POSTED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    def create(self, digest: Digest) -> Digest:
        """Create a new digest.

        Args:
            digest: Digest to create.

        Returns:
            Created digest with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO digests (scheduled_at, target_channel_id, status)
            VALUES (:scheduled_at, :target_channel_id, :status)
            RETURNING id, created_at, updated_at
            """,
            {
                "scheduled_at": digest.scheduled_at,
                "target_channel_id": digest.target_channel_id,
                "status": digest.status,
            },
        )
        digest.id = rows[0][0]
        digest.created_at = rows[0][1]
        digest.updated_at = rows[0][2]
        return digest

    def update(self, digest: Digest) -> Digest:
        """Update an existing digest.

        Args:
            digest: Digest to update.

        Returns:
            Updated digest.

        Raises:
            ValueError: If digest ID is not set.
        """
        if digest.id is None:
            raise ValueError("Digest ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE digests
            SET scheduled_at = :scheduled_at, posted_at = :posted_at, 
                target_channel_id = :target_channel_id, status = :status, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": digest.id,
                "scheduled_at": digest.scheduled_at,
                "posted_at": digest.posted_at,
                "target_channel_id": digest.target_channel_id,
                "status": digest.status,
            },
        )
        return digest

    def mark_posted(self, digest_id: int) -> None:
        """Mark a digest as posted.

        Args:
            digest_id: Digest ID.
        """
        self.db.execute_with_transaction(
            """
            UPDATE digests
            SET status = :status, posted_at = NOW(), updated_at = NOW()
            WHERE id = :id
            """,
            {"id": digest_id, "status": DigestStatus.POSTED},
        )

    def mark_failed(self, digest_id: int) -> None:
        """Mark a digest as failed.

        Args:
            digest_id: Digest ID.
        """
        self.db.execute_with_transaction(
            """
            UPDATE digests
            SET status = :status, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": digest_id, "status": DigestStatus.FAILED},
        )

    def cancel(self, digest_id: int) -> None:
        """Cancel a scheduled digest.

        Args:
            digest_id: Digest ID.
        """
        self.db.execute_with_transaction(
            """
            UPDATE digests
            SET status = :status, updated_at = NOW()
            WHERE id = :id AND status = :scheduled_status
            """,
            {
                "id": digest_id,
                "status": DigestStatus.CANCELLED,
                "scheduled_status": DigestStatus.SCHEDULED,
            },
        )

    def delete(self, digest_id: int) -> None:
        """Delete a digest and its items.

        Args:
            digest_id: Digest ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM digest_items WHERE digest_id = :digest_id",
            {"digest_id": digest_id},
        )
        self.db.execute_with_transaction(
            "DELETE FROM digests WHERE id = :id",
            {"id": digest_id},
        )

    # Digest items methods

    def get_items(self, digest_id: int) -> List[Tuple[DigestItem, int, str, str]]:
        """Get items for a digest with summary information.

        Args:
            digest_id: Digest ID.

        Returns:
            List of tuples (DigestItem, summary_id, title, content) ordered by position.
        """
        rows = self.db.execute(
            """
            SELECT di.id, di.digest_id, di.summary_id, di.position, di.created_at,
                   s.id, s.title, s.content
            FROM digest_items di
            JOIN summaries s ON di.summary_id = s.id
            WHERE di.digest_id = :digest_id
            ORDER BY di.position ASC
            """,
            {"digest_id": digest_id},
        )
        items = []
        for row in rows:
            item = DigestItem(
                id=row[0],
                digest_id=row[1],
                summary_id=row[2],
                position=row[3],
                created_at=row[4],
            )
            summary_id = row[5]
            title = row[6]
            content = row[7]
            items.append((item, summary_id, title, content))
        return items

    def add_item(self, digest_id: int, summary_id: int, position: Optional[int] = None) -> DigestItem:
        """Add an item to a digest.

        Args:
            digest_id: Digest ID.
            summary_id: Summary ID.
            position: Position in the digest (order). If not provided, will be added at the end.

        Returns:
            Created digest item.
        """
        # If position is not provided, add at the end
        if position is None:
            rows = self.db.execute(
                """
                SELECT COALESCE(MAX(position), 0) + 1
                FROM digest_items
                WHERE digest_id = :digest_id
                """,
                {"digest_id": digest_id},
            )
            position = rows[0][0] if rows else 1

        rows = self.db.execute_with_transaction(
            """
            INSERT INTO digest_items (digest_id, summary_id, position)
            VALUES (:digest_id, :summary_id, :position)
            RETURNING id, created_at
            """,
            {
                "digest_id": digest_id,
                "summary_id": summary_id,
                "position": position,
            },
        )
        return DigestItem(
            id=rows[0][0],
            digest_id=digest_id,
            summary_id=summary_id,
            position=position,
            created_at=rows[0][1],
        )

    def remove_item(self, item_id: int) -> None:
        """Remove an item from a digest.

        Args:
            item_id: Digest item ID.
        """
        # Get digest_id and position of the item to be removed
        rows = self.db.execute(
            """
            SELECT digest_id, position
            FROM digest_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        if not rows:
            return

        digest_id, position = rows[0]

        # Remove the item
        self.db.execute_with_transaction(
            "DELETE FROM digest_items WHERE id = :id",
            {"id": item_id},
        )

        # Reorder remaining items
        self.db.execute_with_transaction(
            """
            UPDATE digest_items
            SET position = position - 1
            WHERE digest_id = :digest_id AND position > :position
            """,
            {"digest_id": digest_id, "position": position},
        )

    def reorder_item(self, item_id: int, new_position: int) -> None:
        """Change the position of an item in a digest.

        Args:
            item_id: Digest item ID.
            new_position: New position for the item.
        """
        # Get current position and digest_id
        rows = self.db.execute(
            """
            SELECT digest_id, position
            FROM digest_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        if not rows:
            return

        digest_id, current_position = rows[0]

        # No change needed if position is the same
        if current_position == new_position:
            return

        # Adjust positions of other items
        if current_position < new_position:
            # Moving down: items between current and new position move up
            self.db.execute_with_transaction(
                """
                UPDATE digest_items
                SET position = position - 1
                WHERE digest_id = :digest_id 
                AND position > :current_position AND position <= :new_position
                """,
                {
                    "digest_id": digest_id,
                    "current_position": current_position,
                    "new_position": new_position,
                },
            )
        else:
            # Moving up: items between new and current position move down
            self.db.execute_with_transaction(
                """
                UPDATE digest_items
                SET position = position + 1
                WHERE digest_id = :digest_id 
                AND position >= :new_position AND position < :current_position
                """,
                {
                    "digest_id": digest_id,
                    "current_position": current_position,
                    "new_position": new_position,
                },
            )

        # Update the item's position
        self.db.execute_with_transaction(
            """
            UPDATE digest_items
            SET position = :new_position
            WHERE id = :id
            """,
            {"id": item_id, "new_position": new_position},
        )

    # Async methods

    async def get_async(self, digest_id: int) -> Optional[Digest]:
        """Get a digest by ID asynchronously.

        Args:
            digest_id: Digest ID.

        Returns:
            Digest or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests WHERE id = :id
            """,
            {"id": digest_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Digest(
            id=row[0],
            scheduled_at=row[1],
            posted_at=row[2],
            target_channel_id=row[3],
            status=row[4],
            created_at=row[5],
            updated_at=row[6],
        )

    async def get_scheduled_async(self, limit: int = 10) -> List[Digest]:
        """Get scheduled digests that are due for posting asynchronously.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of scheduled digests due for posting.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
            LIMIT :limit
            """,
            {"status": DigestStatus.SCHEDULED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    async def get_upcoming_async(self, limit: int = 10) -> List[Digest]:
        """Get upcoming scheduled digests asynchronously.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of upcoming scheduled digests.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status AND scheduled_at > NOW()
            ORDER BY scheduled_at ASC
            LIMIT :limit
            """,
            {"status": DigestStatus.SCHEDULED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    async def get_recent_async(self, limit: int = 10) -> List[Digest]:
        """Get recently posted digests asynchronously.

        Args:
            limit: Maximum number of digests to return.

        Returns:
            List of recently posted digests.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, scheduled_at, posted_at, target_channel_id, status, created_at, updated_at 
            FROM digests 
            WHERE status = :status
            ORDER BY posted_at DESC
            LIMIT :limit
            """,
            {"status": DigestStatus.POSTED, "limit": limit},
        )
        digests = []
        for row in rows:
            digests.append(
                Digest(
                    id=row[0],
                    scheduled_at=row[1],
                    posted_at=row[2],
                    target_channel_id=row[3],
                    status=row[4],
                    created_at=row[5],
                    updated_at=row[6],
                )
            )
        return digests

    async def create_async(self, digest: Digest) -> Digest:
        """Create a new digest asynchronously.

        Args:
            digest: Digest to create.

        Returns:
            Created digest with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO digests (scheduled_at, target_channel_id, status)
            VALUES (:scheduled_at, :target_channel_id, :status)
            RETURNING id, created_at, updated_at
            """,
            {
                "scheduled_at": digest.scheduled_at,
                "target_channel_id": digest.target_channel_id,
                "status": digest.status,
            },
        )
        digest.id = rows[0][0]
        digest.created_at = rows[0][1]
        digest.updated_at = rows[0][2]
        return digest

    async def update_async(self, digest: Digest) -> Digest:
        """Update an existing digest asynchronously.

        Args:
            digest: Digest to update.

        Returns:
            Updated digest.

        Raises:
            ValueError: If digest ID is not set.
        """
        if digest.id is None:
            raise ValueError("Digest ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE digests
            SET scheduled_at = :scheduled_at, posted_at = :posted_at, 
                target_channel_id = :target_channel_id, status = :status, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": digest.id,
                "scheduled_at": digest.scheduled_at,
                "posted_at": digest.posted_at,
                "target_channel_id": digest.target_channel_id,
                "status": digest.status,
            },
        )
        return digest

    async def mark_posted_async(self, digest_id: int) -> None:
        """Mark a digest as posted asynchronously.

        Args:
            digest_id: Digest ID.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE digests
            SET status = :status, posted_at = NOW(), updated_at = NOW()
            WHERE id = :id
            """,
            {"id": digest_id, "status": DigestStatus.POSTED},
        )

    async def mark_failed_async(self, digest_id: int) -> None:
        """Mark a digest as failed asynchronously.

        Args:
            digest_id: Digest ID.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE digests
            SET status = :status, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": digest_id, "status": DigestStatus.FAILED},
        )

    async def cancel_async(self, digest_id: int) -> None:
        """Cancel a scheduled digest asynchronously.

        Args:
            digest_id: Digest ID.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE digests
            SET status = :status, updated_at = NOW()
            WHERE id = :id AND status = :scheduled_status
            """,
            {
                "id": digest_id,
                "status": DigestStatus.CANCELLED,
                "scheduled_status": DigestStatus.SCHEDULED,
            },
        )

    async def delete_async(self, digest_id: int) -> None:
        """Delete a digest and its items asynchronously.

        Args:
            digest_id: Digest ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM digest_items WHERE digest_id = :digest_id",
            {"digest_id": digest_id},
        )
        await self.db.execute_with_transaction_async(
            "DELETE FROM digests WHERE id = :id",
            {"id": digest_id},
        )

    # Async digest items methods

    async def get_items_async(self, digest_id: int) -> List[Tuple[DigestItem, int, str, str]]:
        """Get items for a digest with summary information asynchronously.

        Args:
            digest_id: Digest ID.

        Returns:
            List of tuples (DigestItem, summary_id, title, content) ordered by position.
        """
        rows = await self.db.execute_async(
            """
            SELECT di.id, di.digest_id, di.summary_id, di.position, di.created_at,
                   s.id, s.title, s.content
            FROM digest_items di
            JOIN summaries s ON di.summary_id = s.id
            WHERE di.digest_id = :digest_id
            ORDER BY di.position ASC
            """,
            {"digest_id": digest_id},
        )
        items = []
        for row in rows:
            item = DigestItem(
                id=row[0],
                digest_id=row[1],
                summary_id=row[2],
                position=row[3],
                created_at=row[4],
            )
            summary_id = row[5]
            title = row[6]
            content = row[7]
            items.append((item, summary_id, title, content))
        return items

    async def add_item_async(self, digest_id: int, summary_id: int, position: Optional[int] = None) -> DigestItem:
        """Add an item to a digest asynchronously.

        Args:
            digest_id: Digest ID.
            summary_id: Summary ID.
            position: Position in the digest (order). If not provided, will be added at the end.

        Returns:
            Created digest item.
        """
        # If position is not provided, add at the end
        if position is None:
            rows = await self.db.execute_async(
                """
                SELECT COALESCE(MAX(position), 0) + 1
                FROM digest_items
                WHERE digest_id = :digest_id
                """,
                {"digest_id": digest_id},
            )
            position = rows[0][0] if rows else 1

        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO digest_items (digest_id, summary_id, position)
            VALUES (:digest_id, :summary_id, :position)
            RETURNING id, created_at
            """,
            {
                "digest_id": digest_id,
                "summary_id": summary_id,
                "position": position,
            },
        )
        return DigestItem(
            id=rows[0][0],
            digest_id=digest_id,
            summary_id=summary_id,
            position=position,
            created_at=rows[0][1],
        )

    async def remove_item_async(self, item_id: int) -> None:
        """Remove an item from a digest asynchronously.

        Args:
            item_id: Digest item ID.
        """
        # Get digest_id and position of the item to be removed
        rows = await self.db.execute_async(
            """
            SELECT digest_id, position
            FROM digest_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        if not rows:
            return

        digest_id, position = rows[0]

        # Remove the item
        await self.db.execute_with_transaction_async(
            "DELETE FROM digest_items WHERE id = :id",
            {"id": item_id},
        )

        # Reorder remaining items
        await self.db.execute_with_transaction_async(
            """
            UPDATE digest_items
            SET position = position - 1
            WHERE digest_id = :digest_id AND position > :position
            """,
            {"digest_id": digest_id, "position": position},
        )

    async def reorder_item_async(self, item_id: int, new_position: int) -> None:
        """Change the position of an item in a digest asynchronously.

        Args:
            item_id: Digest item ID.
            new_position: New position for the item.
        """
        # Get current position and digest_id
        rows = await self.db.execute_async(
            """
            SELECT digest_id, position
            FROM digest_items
            WHERE id = :id
            """,
            {"id": item_id},
        )
        if not rows:
            return

        digest_id, current_position = rows[0]

        # No change needed if position is the same
        if current_position == new_position:
            return

        # Adjust positions of other items
        if current_position < new_position:
            # Moving down: items between current and new position move up
            await self.db.execute_with_transaction_async(
                """
                UPDATE digest_items
                SET position = position - 1
                WHERE digest_id = :digest_id 
                AND position > :current_position AND position <= :new_position
                """,
                {
                    "digest_id": digest_id,
                    "current_position": current_position,
                    "new_position": new_position,
                },
            )
        else:
            # Moving up: items between new and current position move down
            await self.db.execute_with_transaction_async(
                """
                UPDATE digest_items
                SET position = position + 1
                WHERE digest_id = :digest_id 
                AND position >= :new_position AND position < :current_position
                """,
                {
                    "digest_id": digest_id,
                    "current_position": current_position,
                    "new_position": new_position,
                },
            )

        # Update the item's position
        await self.db.execute_with_transaction_async(
            """
            UPDATE digest_items
            SET position = :new_position
            WHERE id = :id
            """,
            {"id": item_id, "new_position": new_position},
        )