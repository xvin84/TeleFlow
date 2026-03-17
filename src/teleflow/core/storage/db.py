import aiosqlite
from pathlib import Path
from teleflow.utils.logger import logger
from typing import Optional, Any

class DatabaseManager:
    """Async manager for the application's SQLite database."""

    def __init__(self, db_path: str | Path = "teleflow.db") -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Establish the database connection and initialize tables."""
        if self._conn is None:
            logger.info(f"Connecting to database at {self.db_path}")
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._init_schema()

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database connection closed.")

    async def _init_schema(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        if not self._conn:
            raise RuntimeError("Database not connected.")
            
        logger.debug("Initializing database schema...")
        
        # Accounts table
        # We store api_id and api_hash alongside the session string to re-authenticate seamlessly
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                api_id INTEGER NOT NULL,
                api_hash TEXT NOT NULL,
                session_string TEXT NOT NULL,
                status TEXT DEFAULT 'offline',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # Settings table
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        
        # Chats table
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_phone TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                title TEXT,
                type TEXT NOT NULL,
                access_hash INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_phone, chat_id)
            )
            """
        )
        
        # Messages table
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_phone TEXT NOT NULL,
                title TEXT NOT NULL,
                text_content TEXT,
                media_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # Chat-Message Links table
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_message_links (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        
        # Send Logs table
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS send_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_phone TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
            )
            """
        )
        

        # Schedules metadata table.
        # APScheduler persists job state in teleflow_scheduler.db.
        # This table mirrors schedule metadata for UI display/management.
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id              TEXT PRIMARY KEY,
                msg_id          INTEGER NOT NULL,
                account_phone   TEXT NOT NULL,
                mode            TEXT NOT NULL,
                config_json     TEXT NOT NULL,
                description     TEXT NOT NULL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (msg_id) REFERENCES messages(id) ON DELETE CASCADE
            )
            """
        )

        await self._conn.commit()
        logger.debug("Schema initialized.")

    async def execute(self, query: str, parameters: tuple = ()) -> aiosqlite.Cursor:  # type: ignore[type-arg]
        """Execute a query returning a cursor."""
        if not self._conn:
            await self.connect()
        assert self._conn is not None
        return await self._conn.execute(query, parameters)
        
    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._conn:
            await self._conn.commit()

    # Settings API
    async def get_setting(self, key: str, default: Any = None) -> Any:
        cursor = await self.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return row['value'] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        await self.commit()


    # ── Schedules API ─────────────────────────────────────────────────────────

    async def save_schedule(
        self,
        schedule_id: str,
        msg_id: int,
        account_phone: str,
        mode: str,
        config_json: str,
        description: str,
    ) -> None:
        await self.execute(
            """INSERT OR REPLACE INTO schedules
               (id, msg_id, account_phone, mode, config_json, description)
               VALUES (?, ?, ?, ?, ?, ?)
            """,
            (schedule_id, msg_id, account_phone, mode, config_json, description),
        )
        await self.commit()

    async def delete_schedule(self, schedule_id: str) -> None:
        await self.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await self.commit()

    async def delete_schedules_for_message(self, msg_id: int) -> None:
        await self.execute("DELETE FROM schedules WHERE msg_id = ?", (msg_id,))
        await self.commit()

    async def delete_schedules_for_account(self, phone: str) -> None:
        await self.execute("DELETE FROM schedules WHERE account_phone = ?", (phone,))
        await self.commit()

    async def list_schedules_for_message(self, msg_id: int) -> list[dict]:  # type: ignore[type-arg]
        cursor = await self.execute(
            "SELECT * FROM schedules WHERE msg_id = ? ORDER BY created_at DESC",
            (msg_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def list_all_schedules(self) -> list[dict]:  # type: ignore[type-arg]
        cursor = await self.execute("SELECT * FROM schedules ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

# Single global instance
db = DatabaseManager()
