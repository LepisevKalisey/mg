"""Security module for handling encryption and secrets."""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional

from app.config import get_config


class Security:
    """Security class for handling encryption and secrets."""

    def __init__(self, master_key: Optional[str] = None):
        """Initialize the security module.

        Args:
            master_key: Master key for encryption. If not provided, will use the
                master_key from the configuration.
        """
        if master_key is None:
            config = get_config()
            master_key = config.get("security.master_key")

        if not master_key:
            raise ValueError("Master key is required for encryption")

        # Convert the master key to a Fernet key
        self.fernet = self._create_fernet(master_key)

    def _create_fernet(self, master_key: str) -> Fernet:
        """Create a Fernet instance from the master key.

        Args:
            master_key: Master key for encryption.

        Returns:
            Fernet instance.
        """
        # Use PBKDF2 to derive a key from the master key
        salt = b"mg_salt"  # Fixed salt for deterministic key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode()))
        return Fernet(key)

    def encrypt(self, data: str) -> str:
        """Encrypt data.

        Args:
            data: Data to encrypt.

        Returns:
            Encrypted data as a base64-encoded string.
        """
        encrypted = self.fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data.

        Args:
            encrypted_data: Encrypted data as a base64-encoded string.

        Returns:
            Decrypted data.

        Raises:
            ValueError: If the data cannot be decrypted.
        """
        try:
            encrypted = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.fernet.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Failed to decrypt data: {e}")

    def generate_token(self, length: int = 32) -> str:
        """Generate a random token.

        Args:
            length: Length of the token in bytes.

        Returns:
            Random token as a hexadecimal string.
        """
        return os.urandom(length).hex()


# Singleton instance
_security_instance = None


def get_security(master_key: Optional[str] = None) -> Security:
    """Get the security instance.

    Args:
        master_key: Master key for encryption. If not provided, will use the
            master_key from the configuration.

    Returns:
        Security instance.
    """
    global _security_instance
    if _security_instance is None:
        _security_instance = Security(master_key)
    return _security_instance