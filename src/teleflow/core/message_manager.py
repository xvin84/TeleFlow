from teleflow.core.storage.db import db
from teleflow.utils.logger import logger
from typing import List, Dict, Any, Optional

class MessageManager:
    """Manages message templates and their assignments to chats."""
    
    def __init__(self) -> None:
        pass

    async def create_message(self, phone: str, title: str, text_content: str, media_path: Optional[str] = None) -> Optional[int]:
        """Create a new message template for an account."""
        try:
            cursor = await db.execute(
                """
                INSERT INTO messages (account_phone, title, text_content, media_path)
                VALUES (?, ?, ?, ?)
                """,
                (phone, title, text_content, media_path)
            )
            await db.commit()
            logger.info(f"Created message template '{title}' for {phone}")
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to create message for {phone}: {e}")
            return None

    async def update_message(self, msg_id: int, title: str, text_content: str, media_path: Optional[str] = None) -> bool:
        """Update an existing message template."""
        try:
            await db.execute(
                """
                UPDATE messages 
                SET title = ?, text_content = ?, media_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, text_content, media_path, msg_id)
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update message {msg_id}: {e}")
            return False

    async def delete_message(self, msg_id: int) -> bool:
        """Delete a message template and cascade its links."""
        try:
            await db.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete message {msg_id}: {e}")
            return False

    async def get_messages_for_account(self, phone: str) -> List[Dict[str, Any]]:
        """Get all message templates for a given account."""
        try:
            cursor = await db.execute(
                "SELECT id, title, text_content, media_path, created_at, updated_at FROM messages WHERE account_phone = ? ORDER BY updated_at DESC",
                (phone,)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch messages for {phone}: {e}")
            return []
            
    async def assign_message_to_chats(self, msg_id: int, chat_ids: List[int]) -> bool:
        """Assign a message to multiple db chat entries (using the internal db `id`, not telegram `chat_id`)."""
        try:
            for c_id in chat_ids:
                await db.execute(
                    """
                    INSERT INTO chat_message_links (chat_id, message_id)
                    VALUES (?, ?)
                    ON CONFLICT(chat_id, message_id) DO NOTHING
                    """,
                    (c_id, msg_id)
                )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to assign message {msg_id} to chats: {e}")
            return False

    async def update_message_assignments(self, msg_id: int, chat_ids: List[int]) -> bool:
        """Replace all chat assignments for a message with a new list."""
        try:
            # Delete all existing links
            await db.execute("DELETE FROM chat_message_links WHERE message_id = ?", (msg_id,))
            
            # Insert the new ones
            for c_id in chat_ids:
                await db.execute(
                    """
                    INSERT INTO chat_message_links (chat_id, message_id, is_active)
                    VALUES (?, ?, 1)
                    """,
                    (c_id, msg_id)
                )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update assignments for message {msg_id}: {e}")
            return False
            
    async def get_assigned_chats_for_message(self, msg_id: int) -> List[Dict[str, Any]]:
        """Get all chats assigned to a specific message template."""
        try:
            query = """
                SELECT c.id as db_chat_id, c.title, c.type, c.chat_id, l.is_active 
                FROM chats c
                JOIN chat_message_links l ON c.id = l.chat_id
                WHERE l.message_id = ?
            """
            cursor = await db.execute(query, (msg_id,))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to fetch assigned chats for message {msg_id}: {e}")
            return []
