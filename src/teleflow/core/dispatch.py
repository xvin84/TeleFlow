from __future__ import annotations
import asyncio
from teleflow.utils.logger import logger

_client_registry: dict[str, object] = {}
_main_loop: asyncio.AbstractEventLoop | None = None


def register_client(phone: str, client: object) -> None:
    _client_registry[phone] = client


def unregister_client(phone: str) -> None:
    _client_registry.pop(phone, None)


def get_client(phone: str) -> object | None:
    return _client_registry.get(phone)


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def dispatch_scheduled_send(
    phone: str,
    msg_id: int,
    text_content: str,
    media_path_raw: str | None,
) -> None:
    """Called by APScheduler in its thread. Submits work to main loop and returns immediately."""
    global _main_loop

    client = get_client(phone)
    if client is None:
        logger.error(f"[dispatch] No active client for {phone}, msg_id={msg_id}")
        return

    if _main_loop is None or not _main_loop.is_running():
        logger.error("[dispatch] Main event loop not available")
        return

    from teleflow.core.message_manager import MessageManager
    from teleflow.core.sender_engine import SenderEngine

    sender = SenderEngine(MessageManager())

    # Submit to main loop — fire and forget, do NOT block with fut.result()
    # The scheduler thread returns immediately; send runs when main loop is free.
    fut = asyncio.run_coroutine_threadsafe(
        sender.send_message_now(client, phone, msg_id, text_content, media_path_raw),  # type: ignore
        _main_loop,
    )

    def _on_done(f: asyncio.Future) -> None:  # type: ignore
        exc = f.exception()
        if exc:
            logger.error(f"[dispatch] Scheduled send failed for msg {msg_id}: {exc}")
        else:
            logger.info(f"[dispatch] Scheduled send completed for msg {msg_id}")

    fut.add_done_callback(_on_done)
