from teleflow.core.telegram.client import TeleflowClient
from teleflow.core.storage.db import db
from teleflow.utils.logger import logger
from typing import List, Dict, Any, Optional

class ChatManager:
    """Manages chat dialogs, syncing them with the database."""
    
    def __init__(self) -> None:
        pass
        
    async def sync_dialogs(self, client: TeleflowClient) -> bool:
        """
        Fetches dialogs via the active Telethon client and caches them in the database.
        Returns True if successful, False otherwise.
        """
        phone = client.phone
        logger.info(f"Synchronizing dialogs for account {phone}")
        
        dialogs = await client.get_all_dialogs()
        if not dialogs:
            logger.warning(f"No dialogs found for {phone} or fetch failed.")
            return False
            
        try:
            # Upsert into chats table
            for d in dialogs:
                await db.execute(
                    """
                    INSERT INTO chats (account_phone, chat_id, title, type, access_hash)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(account_phone, chat_id) DO UPDATE SET
                        title=excluded.title,
                        type=excluded.type,
                        access_hash=excluded.access_hash,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (phone, d["id"], d["title"], d["type"], d["access_hash"])
                )
            await db.commit()
            logger.info(f"Successfully synchronized {len(dialogs)} dialogs for {phone} into database.")
            return True
        except Exception as e:
            logger.exception(f"Database error while syncing dialogs for {phone}: {e}")
            return False

    async def get_chats_for_account(self, phone: str, chat_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get cached chats for a specific account from the database.
        Optionally filter by chat_type ('User', 'Group', 'Channel').
        """
        query = "SELECT id, chat_id, title, type, access_hash FROM chats WHERE account_phone = ?"
        params = [phone]
        
        if chat_type:
            query += " AND type = ?"
            params.append(chat_type)
            
        query += " ORDER BY updated_at DESC"
        
        try:
            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch chats from db for {phone}: {e}")
            return []
