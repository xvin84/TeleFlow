"""
TrayManager — системный трей и системные уведомления.

Системный трей: pystray (Win/Linux X11).
Wayland fallback: pystray не работает на Wayland без XWayland —
  определяем это и тихо отключаем трей (иконка в taskbar остаётся).

Уведомления: plyer.notification для Win/Linux desktop notifications.
Fallback: если plyer недоступен — только лог.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from typing import TYPE_CHECKING, Any, Callable

from teleflow.utils.logger import logger

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QApplication, QMainWindow

# ── Notification helpers ───────────────────────────────────────────────────────

def _notify(title: str, message: str, timeout: int = 5) -> None:
    """Show a desktop notification. Silent fallback if plyer is unavailable."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message, app_name="TeleFlow", timeout=timeout)
    except Exception:
        logger.debug(f"[Notify] {title}: {message}")


async def _notify_if_enabled(event_key: str, title: str, message: str) -> None:
    from teleflow.core.storage.db import db as _db  # noqa: PLC0415
    if (await _db.get_setting("notify_enabled", "1")) != "1":
        return
    if (await _db.get_setting(event_key, "1")) != "1":
        return
    _notify(title, message)


def notify_send_success(chat_name: str) -> None:
    asyncio.ensure_future(_notify_if_enabled("notify_success", "✅ TeleFlow",
                                             f"Сообщение отправлено в {chat_name}"))


def notify_send_error(chat_name: str, reason: str) -> None:
    asyncio.ensure_future(_notify_if_enabled("notify_error", "❌ TeleFlow",
                                             f"Ошибка отправки в {chat_name}: {reason}"))


def notify_flood_wait(phone: str, seconds: int) -> None:
    asyncio.ensure_future(_notify_if_enabled("notify_flood", "⏸ TeleFlow",
                                             f"Аккаунт {phone} приостановлен на {seconds}с (FloodWait)"))


def notify_account_added(phone: str) -> None:
    _notify("🔑 TeleFlow", f"Аккаунт {phone} добавлен")


# ── TrayManager ───────────────────────────────────────────────────────────────

class TrayManager:
    """
    Manages the system tray icon.

    - Supported on Windows and Linux/X11.
    - Automatically disabled on Wayland (no XWayland) — app runs without tray.
    - The tray runs in its own daemon thread so it doesn't block the Qt loop.
    - Call stop() before process exit (connect to QApplication.aboutToQuit) to
      cleanly terminate pystray's internal threads and avoid hanging on exit.

    IMPORTANT: The event loop reference is captured at construction time
    (main thread) and reused in tray callbacks. Never call asyncio.get_event_loop()
    from the pystray thread — it will fail because pystray runs in a separate thread
    with no asyncio event loop set.
    """

    def __init__(self, app: "QApplication", window: "QMainWindow") -> None:
        self._app    = app
        self._window = window
        self._icon: Any = None  # pystray.Icon — typed as Any; pystray has no stubs
        self._thread: threading.Thread | None = None
        self._available = False
        # Capture the main event loop NOW, while we're in the main Qt/qasync thread.
        # The pystray callbacks will use this reference via call_soon_threadsafe.
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = None

    def start(self) -> None:
        """Try to start the tray icon. Silently no-ops if unavailable."""
        if not self._can_use_tray():
            logger.info("TrayManager: tray not available on this platform/session — skipping.")
            return
        try:
            self._start_tray()
            self._available = True
            # Override close to hide instead of quit (only when tray works)
            self._window.closeEvent = self._make_close_event()  # type: ignore[method-assign]
        except Exception as e:
            logger.info(
                f"TrayManager: system tray unavailable ({type(e).__name__}: {e}) "
                "— running without tray. Install a GNOME tray extension to enable it."
            )
            self._available = False
            if self._icon is not None:
                try:
                    self._icon.stop()
                except Exception:
                    pass
                self._icon = None

    def stop(self) -> None:
        """Stop the tray icon and release its threads. Call before process exit."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
        self._icon = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    # ── Internal ───────────────────────────────────────────────────────────────

    def _can_use_tray(self) -> bool:
        """Return True if pystray is importable and session likely supports it."""
        import os  # noqa: PLC0415
        try:
            import pystray  # noqa: F401
        except ImportError:
            logger.info("TrayManager: pystray not installed — tray disabled.")
            return False

        if sys.platform.startswith("linux"):
            desktop     = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
            x_display   = os.environ.get("DISPLAY", "")
            wayland_env = os.environ.get("WAYLAND_DISPLAY", "")

            # GNOME has no system tray by default (neither on X11 nor Wayland).
            if "GNOME" in desktop:
                logger.info(
                    "TrayManager: GNOME detected — system tray not available by default. "
                    "Install 'AppIndicator and KStatusNotifierItem Support' GNOME extension to enable it."
                )
                return False

            # Pure Wayland without any X server — xorg backend won't work
            if wayland_env and not x_display:
                logger.info("TrayManager: Wayland without DISPLAY — tray disabled.")
                return False

        return True

    def _build_icon_image(self) -> Any:
        """Build a simple PIL image for the tray icon."""
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(41, 182, 246, 255))
        draw.polygon([(20, 40), (44, 24), (44, 44)], fill=(255, 255, 255, 255))
        return img

    def _build_menu(self) -> Any:
        """
        Build the tray menu.

        IMPORTANT: Capture self._loop here (set in __init__ from the main thread).
        All callbacks will run in the pystray thread — use call_soon_threadsafe
        to schedule work on the Qt/qasync event loop safely.
        """
        import pystray

        loop = self._loop

        def _show(_icon: Any, _item: Any) -> None:
            if loop and loop.is_running():
                loop.call_soon_threadsafe(self._show_window)

        def _pause_all(_icon: Any, _item: Any) -> None:
            logger.info("TrayManager: pause-all requested via tray")

        def _quit(_icon: Any, _item: Any) -> None:
            self.stop()
            if loop and loop.is_running():
                loop.call_soon_threadsafe(self._app.quit)

        return pystray.Menu(
            pystray.MenuItem("Показать TeleFlow", _show, default=True),
            pystray.MenuItem("Поставить всё на паузу", _pause_all),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", _quit),
        )

    def _start_tray(self) -> None:
        import pystray
        import time

        image = self._build_icon_image()
        menu  = self._build_menu()
        self._icon = pystray.Icon("TeleFlow", image, "TeleFlow", menu)

        _error: list[Exception] = []

        original_run_detached = self._icon.run_detached

        def _patched_run() -> None:
            try:
                original_run_detached()
            except Exception as e:
                _error.append(e)

        self._icon.run_detached = _patched_run
        self._icon.run_detached()

        # Give the tray thread a moment to fail if it's going to
        time.sleep(0.3)

        if _error:
            raise _error[0]

        running = getattr(self._icon, "_running", True)
        if not running:
            raise RuntimeError("pystray icon failed to start (not running after 300ms)")

        logger.info("TrayManager: tray icon started.")

    def _show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def _make_close_event(self) -> Callable[..., None]:
        from PyQt6.QtGui import QCloseEvent

        def _close(event: QCloseEvent) -> None:
            event.ignore()
            self._window.hide()
            if self._icon is not None:
                try:
                    self._icon.notify("TeleFlow работает в фоне")
                except Exception:
                    pass

        return _close