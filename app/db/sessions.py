"""Sessions database module."""

from datetime import datetime
from typing import List, Optional

from app.db import Database, get_db


class Session:
    """Telegram session model."""

    def __init__(
        self,
        id: Optional[int] = None,
        phone: str = "",
        session_string: str = "",
        is_active: bool = True,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a session.

        Args:
            id: Session ID.
            phone: Phone number associated with the session.
            session_string: Telethon session string.
            is_active: Whether the session is active.
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.phone = phone
        self.session_string = session_string
        self.is_active = is_active
        self.created_at = created_at
        self.updated_at = updated_at


class SessionsRepository:
    """Repository for master_sessions table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, session_id: int) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: Session ID.

        Returns:
            Session or None if not found.
        """
        rows = self.db.execute(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE id = :id",
            {"id": session_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_by_phone(self, phone: str) -> Optional[Session]:
        """Get a session by phone number.

        Args:
            phone: Phone number.

        Returns:
            Session or None if not found.
        """
        rows = self.db.execute(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE phone = :phone",
            {"phone": phone},
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_active(self) -> Optional[Session]:
        """Get an active session.

        Returns:
            Active session or None if not found.
        """
        rows = self.db.execute(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE is_active = TRUE LIMIT 1",
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    def get_all(self) -> List[Session]:
        """Get all sessions.

        Returns:
            List of sessions.
        """
        rows = self.db.execute(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions ORDER BY created_at DESC",
        )
        sessions = []
        for row in rows:
            sessions.append(
                Session(
                    id=row[0],
                    phone=row[1],
                    session_string=row[2],
                    is_active=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return sessions

    def create(self, session: Session) -> Session:
        """Create a new session.

        Args:
            session: Session to create.

        Returns:
            Created session with ID.
        """
        rows = self.db.execute_with_transaction(
            """
            INSERT INTO master_sessions (phone, session_string, is_active)
            VALUES (:phone, :session_string, :is_active)
            RETURNING id, created_at, updated_at
            """,
            {
                "phone": session.phone,
                "session_string": session.session_string,
                "is_active": session.is_active,
            },
        )
        session.id = rows[0][0]
        session.created_at = rows[0][1]
        session.updated_at = rows[0][2]
        return session

    def update(self, session: Session) -> Session:
        """Update an existing session.

        Args:
            session: Session to update.

        Returns:
            Updated session.

        Raises:
            ValueError: If session ID is not set.
        """
        if session.id is None:
            raise ValueError("Session ID must be set for update")

        self.db.execute_with_transaction(
            """
            UPDATE master_sessions
            SET phone = :phone, session_string = :session_string, is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": session.id,
                "phone": session.phone,
                "session_string": session.session_string,
                "is_active": session.is_active,
            },
        )
        return session

    def set_active(self, session_id: int, active: bool = True) -> None:
        """Set a session as active or inactive.

        Args:
            session_id: Session ID.
            active: Whether to set as active or inactive.
        """
        self.db.execute_with_transaction(
            """
            UPDATE master_sessions
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": session_id, "is_active": active},
        )

    def delete(self, session_id: int) -> None:
        """Delete a session.

        Args:
            session_id: Session ID.
        """
        self.db.execute_with_transaction(
            "DELETE FROM master_sessions WHERE id = :id",
            {"id": session_id},
        )

    # Async methods

    async def get_async(self, session_id: int) -> Optional[Session]:
        """Get a session by ID asynchronously.

        Args:
            session_id: Session ID.

        Returns:
            Session or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE id = :id",
            {"id": session_id},
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_by_phone_async(self, phone: str) -> Optional[Session]:
        """Get a session by phone number asynchronously.

        Args:
            phone: Phone number.

        Returns:
            Session or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE phone = :phone",
            {"phone": phone},
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_active_async(self) -> Optional[Session]:
        """Get an active session asynchronously.

        Returns:
            Active session or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions WHERE is_active = TRUE LIMIT 1",
        )
        if not rows:
            return None

        row = rows[0]
        return Session(
            id=row[0],
            phone=row[1],
            session_string=row[2],
            is_active=row[3],
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_all_async(self) -> List[Session]:
        """Get all sessions asynchronously.

        Returns:
            List of sessions.
        """
        rows = await self.db.execute_async(
            "SELECT id, phone, session_string, is_active, created_at, updated_at FROM master_sessions ORDER BY created_at DESC",
        )
        sessions = []
        for row in rows:
            sessions.append(
                Session(
                    id=row[0],
                    phone=row[1],
                    session_string=row[2],
                    is_active=row[3],
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return sessions

    async def create_async(self, session: Session) -> Session:
        """Create a new session asynchronously.

        Args:
            session: Session to create.

        Returns:
            Created session with ID.
        """
        rows = await self.db.execute_with_transaction_async(
            """
            INSERT INTO master_sessions (phone, session_string, is_active)
            VALUES (:phone, :session_string, :is_active)
            RETURNING id, created_at, updated_at
            """,
            {
                "phone": session.phone,
                "session_string": session.session_string,
                "is_active": session.is_active,
            },
        )
        session.id = rows[0][0]
        session.created_at = rows[0][1]
        session.updated_at = rows[0][2]
        return session

    async def update_async(self, session: Session) -> Session:
        """Update an existing session asynchronously.

        Args:
            session: Session to update.

        Returns:
            Updated session.

        Raises:
            ValueError: If session ID is not set.
        """
        if session.id is None:
            raise ValueError("Session ID must be set for update")

        await self.db.execute_with_transaction_async(
            """
            UPDATE master_sessions
            SET phone = :phone, session_string = :session_string, is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {
                "id": session.id,
                "phone": session.phone,
                "session_string": session.session_string,
                "is_active": session.is_active,
            },
        )
        return session

    async def set_active_async(self, session_id: int, active: bool = True) -> None:
        """Set a session as active or inactive asynchronously.

        Args:
            session_id: Session ID.
            active: Whether to set as active or inactive.
        """
        await self.db.execute_with_transaction_async(
            """
            UPDATE master_sessions
            SET is_active = :is_active, updated_at = NOW()
            WHERE id = :id
            """,
            {"id": session_id, "is_active": active},
        )

    async def delete_async(self, session_id: int) -> None:
        """Delete a session asynchronously.

        Args:
            session_id: Session ID.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM master_sessions WHERE id = :id",
            {"id": session_id},
        )