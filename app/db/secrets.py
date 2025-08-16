"""Secrets database module."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from app.common.crypto import decrypt, encrypt
from app.db import Database, get_db


class SecretKind(str, Enum):
    """Types of secrets."""

    LLM_API_KEY = "llm_api_key"
    TELETHON_SESSION = "telethon_session"


class Secret:
    """Secret model."""

    def __init__(
        self,
        id: Optional[int] = None,
        kind: str = "",
        name: str = "",
        value: str = "",
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize a secret.

        Args:
            id: Secret ID.
            kind: Secret kind.
            name: Secret name.
            value: Secret value (decrypted).
            created_at: Creation timestamp.
            updated_at: Last update timestamp.
        """
        self.id = id
        self.kind = kind
        self.name = name
        self.value = value
        self.created_at = created_at
        self.updated_at = updated_at


class SecretsRepository:
    """Repository for secrets table."""

    def __init__(self, db: Optional[Database] = None, master_key: Optional[bytes] = None):
        """Initialize the repository.

        Args:
            db: Database instance. If not provided, the global instance will be used.
            master_key: Master key for encryption/decryption. If not provided, encryption/decryption will fail.
        """
        self.db = db or get_db()
        self.master_key = master_key

    def get(self, kind: str, name: str) -> Optional[Secret]:
        """Get a secret by kind and name.

        Args:
            kind: Secret kind.
            name: Secret name.

        Returns:
            Secret or None if not found.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for decryption")

        rows = self.db.execute(
            "SELECT id, kind, name, enc_value, created_at, updated_at FROM secrets WHERE kind = :kind AND name = :name",
            {"kind": kind, "name": name},
        )
        if not rows:
            return None

        row = rows[0]
        decrypted_value = decrypt(row[3], self.master_key)
        return Secret(
            id=row[0],
            kind=row[1],
            name=row[2],
            value=decrypted_value.decode("utf-8"),
            created_at=row[4],
            updated_at=row[5],
        )

    def get_all_by_kind(self, kind: str) -> List[Secret]:
        """Get all secrets of a specific kind.

        Args:
            kind: Secret kind.

        Returns:
            List of secrets.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for decryption")

        rows = self.db.execute(
            "SELECT id, kind, name, enc_value, created_at, updated_at FROM secrets WHERE kind = :kind",
            {"kind": kind},
        )
        secrets = []
        for row in rows:
            decrypted_value = decrypt(row[3], self.master_key)
            secrets.append(
                Secret(
                    id=row[0],
                    kind=row[1],
                    name=row[2],
                    value=decrypted_value.decode("utf-8"),
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return secrets

    def set(self, secret: Secret) -> Secret:
        """Set a secret.

        Args:
            secret: Secret to set.

        Returns:
            Updated secret with ID.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for encryption")

        encrypted_value = encrypt(secret.value.encode("utf-8"), self.master_key)

        if secret.id is None:
            # Insert new secret
            rows = self.db.execute_with_transaction(
                """
                INSERT INTO secrets (kind, name, enc_value)
                VALUES (:kind, :name, :enc_value)
                RETURNING id, created_at, updated_at
                """,
                {"kind": secret.kind, "name": secret.name, "enc_value": encrypted_value},
            )
            secret.id = rows[0][0]
            secret.created_at = rows[0][1]
            secret.updated_at = rows[0][2]
        else:
            # Update existing secret
            self.db.execute_with_transaction(
                """
                UPDATE secrets
                SET enc_value = :enc_value, updated_at = NOW()
                WHERE id = :id
                RETURNING updated_at
                """,
                {"id": secret.id, "enc_value": encrypted_value},
            )

        return secret

    def delete(self, kind: str, name: str) -> None:
        """Delete a secret.

        Args:
            kind: Secret kind.
            name: Secret name.
        """
        self.db.execute_with_transaction(
            "DELETE FROM secrets WHERE kind = :kind AND name = :name",
            {"kind": kind, "name": name},
        )

    async def get_async(self, kind: str, name: str) -> Optional[Secret]:
        """Get a secret by kind and name asynchronously.

        Args:
            kind: Secret kind.
            name: Secret name.

        Returns:
            Secret or None if not found.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for decryption")

        rows = await self.db.execute_async(
            "SELECT id, kind, name, enc_value, created_at, updated_at FROM secrets WHERE kind = :kind AND name = :name",
            {"kind": kind, "name": name},
        )
        if not rows:
            return None

        row = rows[0]
        decrypted_value = decrypt(row[3], self.master_key)
        return Secret(
            id=row[0],
            kind=row[1],
            name=row[2],
            value=decrypted_value.decode("utf-8"),
            created_at=row[4],
            updated_at=row[5],
        )

    async def get_all_by_kind_async(self, kind: str) -> List[Secret]:
        """Get all secrets of a specific kind asynchronously.

        Args:
            kind: Secret kind.

        Returns:
            List of secrets.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for decryption")

        rows = await self.db.execute_async(
            "SELECT id, kind, name, enc_value, created_at, updated_at FROM secrets WHERE kind = :kind",
            {"kind": kind},
        )
        secrets = []
        for row in rows:
            decrypted_value = decrypt(row[3], self.master_key)
            secrets.append(
                Secret(
                    id=row[0],
                    kind=row[1],
                    name=row[2],
                    value=decrypted_value.decode("utf-8"),
                    created_at=row[4],
                    updated_at=row[5],
                )
            )
        return secrets

    async def set_async(self, secret: Secret) -> Secret:
        """Set a secret asynchronously.

        Args:
            secret: Secret to set.

        Returns:
            Updated secret with ID.

        Raises:
            ValueError: If master_key is not set.
        """
        if not self.master_key:
            raise ValueError("Master key is required for encryption")

        encrypted_value = encrypt(secret.value.encode("utf-8"), self.master_key)

        if secret.id is None:
            # Insert new secret
            rows = await self.db.execute_with_transaction_async(
                """
                INSERT INTO secrets (kind, name, enc_value)
                VALUES (:kind, :name, :enc_value)
                RETURNING id, created_at, updated_at
                """,
                {"kind": secret.kind, "name": secret.name, "enc_value": encrypted_value},
            )
            secret.id = rows[0][0]
            secret.created_at = rows[0][1]
            secret.updated_at = rows[0][2]
        else:
            # Update existing secret
            await self.db.execute_with_transaction_async(
                """
                UPDATE secrets
                SET enc_value = :enc_value, updated_at = NOW()
                WHERE id = :id
                RETURNING updated_at
                """,
                {"id": secret.id, "enc_value": encrypted_value},
            )

        return secret

    async def delete_async(self, kind: str, name: str) -> None:
        """Delete a secret asynchronously.

        Args:
            kind: Secret kind.
            name: Secret name.
        """
        await self.db.execute_with_transaction_async(
            "DELETE FROM secrets WHERE kind = :kind AND name = :name",
            {"kind": kind, "name": name},
        )