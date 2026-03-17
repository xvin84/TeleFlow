"""
SenderEngine — отправка сообщений через Telethon.

Поддерживает:
- Текстовые сообщения без медиа
- 1 файл (любой тип)
- Несколько изображений → album (send_file с list)
- Видео → отдельные send_file с caption
- Документы (pdf, docx и т.д.) → send_file с force_document=True
- Смешанные наборы: изображения в album + остальные по одному
- Retry-логика: 3 попытки с exponential backoff при сетевых ошибках
"""

import asyncio
import json
import os
from telethon.errors.rpcerrorlist import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
)
from telethon.errors import RPCError
from teleflow.core.telegram.client import TeleflowClient
from teleflow.core.message_manager import MessageManager
from teleflow.core.storage.db import db
from teleflow.utils.logger import logger
from teleflow.gui.tray_manager import notify_send_success, notify_send_error, notify_flood_wait

# ─── File type sets ───────────────────────────────────────────────────────────
IMAGE_EXTS    = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv"}
AUDIO_EXTS    = {".mp3", ".ogg", ".wav", ".m4a", ".flac"}
# All other extensions → sent as documents (force_document=True)

# Retry config
_MAX_RETRIES   = 3
_RETRY_BACKOFF = (5.0, 15.0, 30.0)  # seconds between attempts


def _parse_media_paths(raw: str | None) -> list[str]:
    """Parse media_path DB field into a list of local file paths."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [p for p in parsed if p and os.path.exists(p)]
        return [raw] if os.path.exists(raw) else []
    except (json.JSONDecodeError, ValueError):
        return [raw] if (raw and os.path.exists(raw)) else []


def _classify_files(paths: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """Split file paths into (images, videos, audios, documents)."""
    images, videos, audios, docs = [], [], [], []
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in IMAGE_EXTS:
            images.append(p)
        elif ext in VIDEO_EXTS:
            videos.append(p)
        elif ext in AUDIO_EXTS:
            audios.append(p)
        else:
            docs.append(p)
    return images, videos, audios, docs


class SenderEngine:
    """
    Handles actual sending of a message template to its assigned chats.
    Applies correct media send strategy and respects Telegram rate limits.
    """

    def __init__(self, message_manager: MessageManager) -> None:
        self.msg_mgr = message_manager

    # ── Logging ───────────────────────────────────────────────────────────────

    async def log_send(
        self,
        phone: str,
        db_chat_id: int,
        msg_id: int,
        status: str,
        error: str | None = None,
    ) -> None:
        """Write a send-attempt log entry to the database."""
        try:
            await db.execute(
                """
                INSERT INTO send_logs (account_phone, chat_id, message_id, status, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (phone, db_chat_id, msg_id, status, error),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to write send log: {e}")

    # ── Main send entry point ─────────────────────────────────────────────────

    async def send_message_now(
        self,
        client: TeleflowClient,
        phone: str,
        msg_id: int,
        text_content: str,
        media_path_raw: str | None,
    ) -> None:
        """
        Send the message template to all active assigned chats.
        Applies retry logic (up to 3 attempts) for transient network errors.
        """
        chats = await self.msg_mgr.get_assigned_chats_for_message(msg_id)
        active_chats = [c for c in chats if c.get("is_active")]

        if not active_chats:
            logger.info(f"[Msg {msg_id}] No active chats assigned — skipping.")
            return

        media_paths = _parse_media_paths(media_path_raw)
        logger.info(
            f"[Msg {msg_id}] Sending to {len(active_chats)} chat(s) "
            f"| media files: {len(media_paths)}"
        )

        for chat_info in active_chats:
            tg_chat_id = chat_info["chat_id"]
            db_chat_id = chat_info["db_chat_id"]

            await asyncio.sleep(2.0)  # Human-like delay between chats
            await self._send_with_retry(
                client, phone, msg_id, tg_chat_id, db_chat_id,
                text_content, media_paths,
            )

        logger.info(f"[Msg {msg_id}] Finished send job for account {phone}.")

    # ── Retry wrapper ─────────────────────────────────────────────────────────

    async def _send_with_retry(
        self,
        client: TeleflowClient,
        phone: str,
        msg_id: int,
        tg_chat_id: int,
        db_chat_id: int,
        text: str,
        media_paths: list[str],
    ) -> None:
        """Send to a single chat with retry on transient errors."""
        for attempt in range(_MAX_RETRIES):
            try:
                await self._send_to_chat(client, tg_chat_id, text, media_paths)
                await self.log_send(phone, db_chat_id, msg_id, "success")
                logger.info(f"[Msg {msg_id}] ✅ Sent to chat {tg_chat_id}")
                notify_send_success(str(tg_chat_id))
                return

            except FloodWaitError as e:
                wait = e.seconds + 1
                logger.warning(
                    f"[Msg {msg_id}] FloodWait {wait}s on chat {tg_chat_id}. Pausing…"
                )
                await self.log_send(
                    phone, db_chat_id, msg_id, "rate_limited",
                    f"FloodWait {e.seconds}s"
                )
                notify_flood_wait(phone, e.seconds)
                await asyncio.sleep(wait)
                # FloodWait is self-resolving — retry immediately after wait
                continue

            except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
                # Permission errors are permanent — no point retrying
                err = type(e).__name__
                logger.warning(
                    f"[Msg {msg_id}] No write permission in {tg_chat_id}: {err}"
                )
                await self.log_send(phone, db_chat_id, msg_id, "failed", err)
                notify_send_error(str(tg_chat_id), err)
                return

            except (ConnectionError, TimeoutError, OSError) as e:
                # Transient network error — retry with backoff
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"[Msg {msg_id}] Network error on attempt {attempt + 1}/{_MAX_RETRIES} "
                    f"for chat {tg_chat_id}: {e}. Retrying in {wait}s…"
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
                # Exhausted retries
                await self.log_send(
                    phone, db_chat_id, msg_id, "failed",
                    f"Network error after {_MAX_RETRIES} attempts: {e}"
                )
                return

            except RPCError as e:
                # Telegram API error that isn't a known permission/flood error
                logger.error(f"[Msg {msg_id}] RPC error for chat {tg_chat_id}: {e}")
                await self.log_send(phone, db_chat_id, msg_id, "failed", str(e))
                return

            except Exception as e:
                logger.error(f"[Msg {msg_id}] Unexpected error for chat {tg_chat_id}: {e}")
                await self.log_send(phone, db_chat_id, msg_id, "failed", str(e))
                return

    # ── Per-chat send logic ───────────────────────────────────────────────────

    async def _send_to_chat(
        self,
        client: TeleflowClient,
        entity: int,
        text: str,
        media_paths: list[str],
    ) -> None:
        """Choose the right Telethon send call based on media type and count."""
        tg = client.client  # underlying TelegramClient

        if not media_paths:
            await tg.send_message(entity=entity, message=text, parse_mode="html")
            return

        images, videos, audios, docs = _classify_files(media_paths)
        caption_sent = False

        # ── Images: send as album (up to 10) ──────────────────────────────
        if images:
            cap = text if not caption_sent else ""
            if len(images) == 1:
                await tg.send_file(entity=entity, file=images[0],
                                   caption=cap, parse_mode="html")
            else:
                await tg.send_file(entity=entity, file=images,
                                   caption=cap, parse_mode="html")
            caption_sent = True
            await asyncio.sleep(1.0)

        # ── Videos ────────────────────────────────────────────────────────
        for vpath in videos:
            cap = text if not caption_sent else ""
            await tg.send_file(entity=entity, file=vpath,
                               caption=cap, parse_mode="html")
            caption_sent = True
            await asyncio.sleep(1.0)

        # ── Audio ─────────────────────────────────────────────────────────
        for apath in audios:
            cap = text if not caption_sent else ""
            await tg.send_file(entity=entity, file=apath,
                               caption=cap, parse_mode="html")
            caption_sent = True
            await asyncio.sleep(1.0)

        # ── Documents ─────────────────────────────────────────────────────
        for dpath in docs:
            cap = text if not caption_sent else ""
            await tg.send_file(entity=entity, file=dpath,
                               caption=cap, parse_mode="html",
                               force_document=True)
            caption_sent = True
            await asyncio.sleep(1.0)
