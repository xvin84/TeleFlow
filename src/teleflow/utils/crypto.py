import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from teleflow.utils.logger import logger


# Sentinel used when the user has not set an application password.
# Combined with a unique per-installation salt this is much better than a
# hardcoded string, even though it is not secret in itself.
_NO_PASSWORD_SENTINEL = "teleflow_no_app_password"


def generate_salt(length: int = 32) -> bytes:
    """Generate a cryptographically-secure random salt."""
    return os.urandom(length)


def salt_to_hex(salt: bytes) -> str:
    """Encode salt bytes to a hex string for DB storage."""
    return salt.hex()


def salt_from_hex(hex_str: str) -> bytes:
    """Decode a hex-encoded salt back to bytes."""
    return bytes.fromhex(hex_str)


class SessionManager:
    """Manages encryption and decryption of Telegram session strings.

    The encryption key is derived from:
      - ``password``: the user's app password, or ``_NO_PASSWORD_SENTINEL``
        when no password is set.
      - ``salt``: a random per-installation salt stored in the DB settings
        under the key ``app_salt``.  It must never change once sessions have
        been encrypted; changing it (or changing the password without
        re-encrypting) will make existing sessions unreadable.

    Call :py:func:`SessionManager.reencrypt_all` when the user changes or
    removes their application password so that stored sessions are migrated to
    the new key.
    """

    def __init__(self, password: str, salt: bytes) -> None:
        """
        Args:
            password: Plain-text application password, or empty string /
                ``_NO_PASSWORD_SENTINEL`` when the user has not set one.
            salt: Per-installation random salt (from DB ``app_salt``).
        """
        self._salt = salt
        self._key = self._derive_key(password, salt)
        self._fernet = Fernet(self._key)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive a Fernet-compatible key from the given password and salt."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = kdf.derive(password.encode("utf-8"))
        return base64.urlsafe_b64encode(key)

    def encrypt(self, data: str) -> str:
        """Encrypt a string and return the ciphertext."""
        try:
            return self._fernet.encrypt(data.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to encrypt data: {e}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string and return the plaintext."""
        try:
            return self._fernet.decrypt(encrypted_data.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error("Failed to decrypt data. Invalid key or corrupted data.")
            raise ValueError(f"Decryption failed: {e}")

    def reencrypt(self, encrypted_data: str, new_password: str) -> str:
        """Decrypt with the current key and re-encrypt with a new password.

        Used when the user changes or removes their application password so
        that previously-stored sessions remain accessible.
        """
        plaintext = self.decrypt(encrypted_data)
        new_mgr = SessionManager(password=new_password, salt=self._salt)
        return new_mgr.encrypt(plaintext)


def make_session_manager(password: str | None, salt: bytes) -> SessionManager:
    """Convenience factory.

    Args:
        password: The user's app password, or ``None`` / empty string when no
            password has been set.
        salt: Per-installation salt from ``db.get_setting('app_salt')``.
    """
    effective_password = password if password else _NO_PASSWORD_SENTINEL
    return SessionManager(password=effective_password, salt=salt)

