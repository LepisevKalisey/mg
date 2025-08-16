"""Posts database module."""

from datetime import datetime
from typing import List, Optional

from app.db import Database, get_db


class RawPost:
    """Raw post model."""

    def __init__(
        self,
        id: Optional[int] = None,
        source_id: int = 0,
        message_id: int = 0,
        text: str = "",
        html: Optional[str] = None,
        posted_at: Optional[datetime] = None,
        fetched_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a raw post.

        Args:
            id: Post ID.
            source_id: Source ID.
            message_id: Telegram message ID.
            text: Post text.
            html: Post HTML (optional).
            posted_at: Post timestamp.
            fetched_at: Fetch timestamp.
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.source_id = source_id
        self.message_id = message_id
        self.text = text
        self.html = html
        self.posted_at = posted_at
        self.fetched_at = fetched_at
        self.created_at = created_at
        self.updated_at = updated_at


class PostsRepository:
    """Repository for raw_posts table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, post_id: int) -> Optional[RawPost]:
        """Get a post by ID.

        Args:
            post_id: Post ID.

        Returns:
            Post or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE id = :id
            """,
            {"id": post_id},
        )
        if not rows:
            return None

        row = rows[0]
        return RawPost(
            id=row[0],
            source_id=row[1],
            message_id=row[2],
            text=row[3],
            html=row[4],
            posted_at=row[5],
            fetched_at=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def get_by_source_and_message_id(self, source_id: int, message_id: int) -> Optional[RawPost]:
        """Get a post by source ID and message ID.

        Args:
            source_id: Source ID.
            message_id: Telegram message ID.

        Returns:
            Post or None if not found.
        """
        rows = self.db.execute(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE source_id = :source_id AND message_id = :message_id
            """,
            {"source_id": source_id, "message_id": message_id},
        )
        if not rows:
            return None

        row = rows[0]
        return RawPost(
            id=row[0],
            source_id=row[1],
            message_id=row[2],
            text=row[3],
            html=row[4],
            posted_at=row[5],
            fetched_at=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    def get_by_source(self, source_id: int, limit: int = 100, offset: int = 0) -> List[RawPost]:
        """Get posts by source ID.

        Args:
            source_id: Source ID.
            limit: Maximum number of posts to return.
            offset: Offset for pagination.

        Returns:
            List of posts.
        """
        rows = self.db.execute(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE source_id = :source_id
            ORDER BY posted_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"source_id": source_id, "limit": limit, "offset": offset},
        )
        posts = []
        for row in rows:
            posts.append(
                RawPost(
                    id=row[0],
                    source_id=row[1],
                    message_id=row[2],
                    text=row[3],
                    html=row[4],
                    posted_at=row[5],
                    fetched_at=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return posts

    def get_latest_by_source(self, source_id: int, limit: int = 10) -> List[RawPost]:
        """Get latest posts by source ID.

        Args:
            source_id: Source ID.
            limit: Maximum number of posts to return.

        Returns:
            List of posts.
        """
        return self.get_by_source(source_id, limit, 0)

    def get_latest(self, limit: int = 100, offset: int = 0) -> List[RawPost]:
        """Get latest posts across all sources.

        Args:
            limit: Maximum number of posts to return.
            offset: Offset for pagination.

        Returns:
            List of posts.
        """
        rows = self.db.execute(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts
            ORDER BY posted_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"limit": limit, "offset": offset},
        )
        posts = []
        for row in rows:
            posts.append(
                RawPost(
                    id=row[0],
                    source_id=row[1],
                    message_id=row[2],
                    text=row[3],
                    html=row[4],
                    posted_at=row[5],
                    fetched_at=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return posts

    def create(self, post: RawPost) -> RawPost:
        """Create a new post.

        Args:
            post: Post to create.

        Returns:
            Created post with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO raw_posts (source_id, message_id, text, html, posted_at, fetched_at)
            VALUES (:source_id, :message_id, :text, :html, :posted_at, :fetched_at)
            RETURNING id, created_at, updated_at
            """,
            {
                "source_id": post.source_id,
                "message_id": post.message_id,
                "text": post.text,
                "html": post.html,
                "posted_at": post.posted_at,
                "fetched_at": post.fetched_at or datetime.now(),
            },
        )
        post.id = rows[0][0]
        post.created_at = rows[0][1]
        post.updated_at = rows[0][2]
        return post

    def update(self, post: RawPost) -> RawPost:
        """Update an existing post.

        Args:
            post: Post to update.

        Returns:
            Updated post.

        Raises:
            ValueError: If post ID is not set.
        """
        if post.id is None:
            raise ValueError("Post ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE raw_posts
            SET source_id = :source_id, message_id = :message_id, text = :text, html = :html,
                posted_at = :posted_at, fetched_at = :fetched_at, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": post.id,
                "source_id": post.source_id,
                "message_id": post.message_id,
                "text": post.text,
                "html": post.html,
                "posted_at": post.posted_at,
                "fetched_at": post.fetched_at,
            },
        )
        return post

    def delete(self, post_id: int) -> None:
        """Delete a post.

        Args:
            post_id: Post ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM raw_posts WHERE id = :id",
            {"id": post_id},
        )

    def delete_by_source(self, source_id: int) -> None:
        """Delete all posts for a source.

        Args:
            source_id: Source ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM raw_posts WHERE source_id = :source_id",
            {"source_id": source_id},
        )

    # Async methods

    async def get_async(self, post_id: int) -> Optional[RawPost]:
        """Get a post by ID asynchronously.

        Args:
            post_id: Post ID.

        Returns:
            Post or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE id = :id
            """,
            {"id": post_id},
        )
        if not rows:
            return None

        row = rows[0]
        return RawPost(
            id=row[0],
            source_id=row[1],
            message_id=row[2],
            text=row[3],
            html=row[4],
            posted_at=row[5],
            fetched_at=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    async def get_by_source_and_message_id_async(self, source_id: int, message_id: int) -> Optional[RawPost]:
        """Get a post by source ID and message ID asynchronously.

        Args:
            source_id: Source ID.
            message_id: Telegram message ID.

        Returns:
            Post or None if not found.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE source_id = :source_id AND message_id = :message_id
            """,
            {"source_id": source_id, "message_id": message_id},
        )
        if not rows:
            return None

        row = rows[0]
        return RawPost(
            id=row[0],
            source_id=row[1],
            message_id=row[2],
            text=row[3],
            html=row[4],
            posted_at=row[5],
            fetched_at=row[6],
            created_at=row[7],
            updated_at=row[8],
        )

    async def get_by_source_async(self, source_id: int, limit: int = 100, offset: int = 0) -> List[RawPost]:
        """Get posts by source ID asynchronously.

        Args:
            source_id: Source ID.
            limit: Maximum number of posts to return.
            offset: Offset for pagination.

        Returns:
            List of posts.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts WHERE source_id = :source_id
            ORDER BY posted_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"source_id": source_id, "limit": limit, "offset": offset},
        )
        posts = []
        for row in rows:
            posts.append(
                RawPost(
                    id=row[0],
                    source_id=row[1],
                    message_id=row[2],
                    text=row[3],
                    html=row[4],
                    posted_at=row[5],
                    fetched_at=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return posts

    async def get_latest_by_source_async(self, source_id: int, limit: int = 10) -> List[RawPost]:
        """Get latest posts by source ID asynchronously.

        Args:
            source_id: Source ID.
            limit: Maximum number of posts to return.

        Returns:
            List of posts.
        """
        return await self.get_by_source_async(source_id, limit, 0)

    async def get_latest_async(self, limit: int = 100, offset: int = 0) -> List[RawPost]:
        """Get latest posts across all sources asynchronously.

        Args:
            limit: Maximum number of posts to return.
            offset: Offset for pagination.

        Returns:
            List of posts.
        """
        rows = await self.db.execute_async(
            """
            SELECT id, source_id, message_id, text, html, posted_at, fetched_at, created_at, updated_at 
            FROM raw_posts
            ORDER BY posted_at DESC
            LIMIT :limit OFFSET :offset
            """,
            {"limit": limit, "offset": offset},
        )
        posts = []
        for row in rows:
            posts.append(
                RawPost(
                    id=row[0],
                    source_id=row[1],
                    message_id=row[2],
                    text=row[3],
                    html=row[4],
                    posted_at=row[5],
                    fetched_at=row[6],
                    created_at=row[7],
                    updated_at=row[8],
                )
            )
        return posts

    async def create_async(self, post: RawPost) -> RawPost:
        """Create a new post asynchronously.

        Args:
            post: Post to create.

        Returns:
            Created post with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO raw_posts (source_id, message_id, text, html, posted_at, fetched_at)
            VALUES (:source_id, :message_id, :text, :html, :posted_at, :fetched_at)
            RETURNING id, created_at, updated_at
            """,
            {
                "source_id": post.source_id,
                "message_id": post.message_id,
                "text": post.text,
                "html": post.html,
                "posted_at": post.posted_at,
                "fetched_at": post.fetched_at or datetime.now(),
            },
        )
        post.id = rows[0][0]
        post.created_at = rows[0][1]
        post.updated_at = rows[0][2]
        return post

    async def update_async(self, post: RawPost) -> RawPost:
        """Update an existing post asynchronously.

        Args:
            post: Post to update.

        Returns:
            Updated post.

        Raises:
            ValueError: If post ID is not set.
        """
        if post.id is None:
            raise ValueError("Post ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE raw_posts
            SET source_id = :source_id, message_id = :message_id, text = :text, html = :html,
                posted_at = :posted_at, fetched_at = :fetched_at, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": post.id,
                "source_id": post.source_id,
                "message_id": post.message_id,
                "text": post.text,
                "html": post.html,
                "posted_at": post.posted_at,
                "fetched_at": post.fetched_at,
            },
        )
        return post

    async def delete_async(self, post_id: int) -> None:
        """Delete a post asynchronously.

        Args:
            post_id: Post ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM raw_posts WHERE id = :id",
            {"id": post_id},
        )

    async def delete_by_source_async(self, source_id: int) -> None:
        """Delete all posts for a source asynchronously.

        Args:
            source_id: Source ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM raw_posts WHERE source_id = :source_id",
            {"source_id": source_id},
        )