"""Settings database module."""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db import Database, get_db


class SettingsRepository:
    """Repository for settings table."""

    def __init__(self, db: Optional[Database] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
        """
        self.db = db or get_db()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a setting by key.

        Args:
            key: Setting key.

        Returns:
            Setting value or None if not found.
        """
        rows = self.db.execute(
            "SELECT value FROM settings WHERE key = :key",
            {"key": key},
        )
        if not rows:
            return None
        return rows[0][0]

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        """Get all settings.

        Returns:
            Dictionary of settings.
        """
        rows = self.db.execute("SELECT key, value FROM settings")
        return {row[0]: row[1] for row in rows}

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set a setting.

        Args:
            key: Setting key.
            value: Setting value.
        """
        self.db.execute_with_transaction(
            """
            INSERT INTO settings (key, value) VALUES (:key, :value)
            ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = NOW()
            """,
            {"key": key, "value": json.dumps(value)},
        )

    def delete(self, key: str) -> None:
        """Delete a setting.

        Args:
            key: Setting key.
        """
        self.db.execute_with_transaction(
            "DELETE FROM settings WHERE key = :key",
            {"key": key},
        )

    async def get_async(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a setting by key asynchronously.

        Args:
            key: Setting key.

        Returns:
            Setting value or None if not found.
        """
        rows = await self.db.execute_async(
            "SELECT value FROM settings WHERE key = :key",
            {"key": key},
        )
        if not rows:
            return None
        return rows[0][0]

    async def get_all_async(self) -> Dict[str, Dict[str, Any]]:
        """Get all settings asynchronously.

        Returns:
            Dictionary of settings.
        """
        rows = await self.db.execute_async("SELECT key, value FROM settings")
        return {row[0]: row[1] for row in rows}

    async def set_async(self, key: str, value: Dict[str, Any]) -> None:
        """Set a setting asynchronously.

        Args:
            key: Setting key.
            value: Setting value.
        """
        await self.db.execute_with_transaction_async(
            """
            INSERT INTO settings (key, value) VALUES (:key, :value)
            ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = NOW()
            """,
            {"key": key, "value": json.dumps(value)},
        )

    async def delete_async(self, key: str) -> None:
        """Delete a setting asynchronously.

        Args:
            key: Setting key.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM settings WHERE key = :key",
            {"key": key},
        )