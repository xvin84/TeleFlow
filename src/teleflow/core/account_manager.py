from typing import List, Dict, Any
from teleflow.core.storage.db import db
from teleflow.utils.crypto import make_session_manager, SessionManager, _NO_PASSWORD_SENTINEL
from teleflow.core.telegram.client import TeleflowClient
from teleflow.utils.logger import logger
from teleflow.core.dispatch import register_client, unregister_client


class AccountManager:
    """Manages Telegram accounts, their sessions, and statuses."""

    def __init__(self, session_password: str | None, salt: bytes) -> None:
        """
        Args:
            session_password: The user's application password, or ``None`` when
                no password has been set.  Used as the encryption key for
                stored Telegram sessions.
            salt: Per-installation random salt fetched from DB settings.
        """
        self._password = session_password
        self._salt = salt
        self.session_manager: SessionManager = make_session_manager(session_password, salt)
        self.active_clients: Dict[str, TeleflowClient] = {}

    async def load_accounts(self) -> None:
        """Load all accounts from the database and connect them."""
        cursor = await db.execute("SELECT phone, api_id, api_hash, session_string, status FROM accounts")
        rows = await cursor.fetchall()
        
        for row in rows:
            phone = row["phone"]
            try:
                decrypted_session = self.session_manager.decrypt(row["session_string"])
                client = TeleflowClient(
                    phone=phone,
                    api_id=row["api_id"],
                    api_hash=row["api_hash"],
                    session_string=decrypted_session
                )
                
                # Check connection in background
                is_authorized = await client.connect()
                if is_authorized:
                    self.active_clients[phone] = client
                    register_client(phone, client)
                    await self.update_status(phone, "online")
                else:
                    logger.warning(f"Account {phone} failed to authorize on load.")
                    await self.update_status(phone, "error")
                    
            except Exception as e:
                logger.error(f"Failed to load account {phone}: {e}")
                await self.update_status(phone, "error")

    async def update_status(self, phone: str, status: str) -> None:
        """Update account status in the database."""
        await db.execute(
            "UPDATE accounts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE phone = ?",
            (status, phone)
        )
        await db.commit()

    async def add_account(self, phone: str, api_id: int, api_hash: str, session_string: str) -> None:
        """Add a newly authenticated account to the database."""
        encrypted_session = self.session_manager.encrypt(session_string)
        
        # If the account exists, update it
        try:
            await db.execute(
                """
                INSERT INTO accounts (phone, api_id, api_hash, session_string, status)
                VALUES (?, ?, ?, ?, 'online')
                ON CONFLICT(phone) DO UPDATE SET 
                    api_id=excluded.api_id,
                    api_hash=excluded.api_hash,
                    session_string=excluded.session_string,
                    status='online',
                    updated_at=CURRENT_TIMESTAMP
                """,
                (phone, api_id, api_hash, encrypted_session)
            )
            await db.commit()
            
            # Add to active clients
            self.active_clients[phone] = TeleflowClient(
                phone=phone, 
                api_id=api_id, 
                api_hash=api_hash, 
                session_string=session_string
            )
            await self.active_clients[phone].connect()
            register_client(phone, self.active_clients[phone])
            logger.info(f"Account {phone} added and connected successfully.")
        except Exception as e:
            logger.error(f"Error adding account {phone}: {e}")
            raise

    async def remove_account(self, phone: str) -> None:
        """Remove an account and gracefully disconnect it."""
        if phone in self.active_clients:
            await self.active_clients[phone].disconnect()
            del self.active_clients[phone]
            unregister_client(phone)
            
        await db.execute("DELETE FROM accounts WHERE phone = ?", (phone,))
        await db.commit()
        logger.info(f"Account {phone} removed.")

    async def get_all_accounts(self) -> List[Dict[str, Any]]:
        """Retrieve a list of all accounts."""
        cursor = await db.execute("SELECT id, phone, status, updated_at FROM accounts ORDER BY updated_at DESC")
        return [dict(row) for row in await cursor.fetchall()]

    async def change_password(self, new_password: str | None) -> None:
        """Re-encrypt all stored sessions under a new password.

        Call this after updating ``app_password_hash`` in the DB so that
        existing sessions remain accessible with the new key.

        Args:
            new_password: The new application password, or ``None`` / empty
                string to remove password protection.
        """
        cursor = await db.execute("SELECT phone, session_string FROM accounts")
        rows = await cursor.fetchall()

        new_mgr = make_session_manager(new_password, self._salt)

        for row in rows:
            phone = row["phone"]
            try:
                # Decrypt with old key, re-encrypt with new key
                plaintext = self.session_manager.decrypt(row["session_string"])
                new_encrypted = new_mgr.encrypt(plaintext)
                await db.execute(
                    "UPDATE accounts SET session_string = ? WHERE phone = ?",
                    (new_encrypted, phone),
                )
                logger.info(f"Re-encrypted session for {phone}")
            except Exception as e:
                logger.error(f"Failed to re-encrypt session for {phone}: {e}")
                raise

        await db.commit()

        # Swap the active session manager to the new one
        self._password = new_password
        self.session_manager = new_mgr
        logger.info("All sessions re-encrypted successfully.")

