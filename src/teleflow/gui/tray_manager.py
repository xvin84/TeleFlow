"""
TrayManager — системный трей и системные уведомления.

Системный трей: PyQt6.QtWidgets.QSystemTrayIcon (Win/Linux/Mac).
Не требует pystray, PIL или отдельного треда.
Работает на GNOME X11/Wayland с libappindicator (если установлена),
а также на KDE Plasma, XFCE, и всех окружениях с нормальным трей-сокетом.

Если трей недоступен (нет иконки в области уведомлений) —
приложение всё равно скрывается при нажатии X,
а кнопка «Выйти» в sidebar обеспечивает явный выход.

Уведомления: QSystemTrayIcon.showMessage() (встроено в Qt).
Fallback: если showMessage недоступна — только лог.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PyQt6.QtGui import QIcon, QPainter, QColor, QBrush, QPen
from PyQt6.QtCore import Qt

from teleflow.utils.logger import logger

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow


# ── Notification helpers ───────────────────────────────────────────────────────

_tray_ref: QSystemTrayIcon | None = None   # set by TrayManager.start()


def _notify_qt(title: str, message: str, timeout_ms: int = 4000) -> None:
    """Show notification via the Qt tray icon (thread-safe only from Qt thread)."""
    if _tray_ref is not None and _tray_ref.isVisible():
        try:
            _tray_ref.showMessage(title, message,
                                  QSystemTrayIcon.MessageIcon.Information,
                                  timeout_ms)
            return
        except Exception:
            pass
    logger.debug(f"[Notify] {title}: {message}")


async def _notify_if_enabled(event_key: str, title: str, message: str) -> None:
    from teleflow.core.storage.db import db as _db  # noqa: PLC0415
    if (await _db.get_setting("notify_enabled", "1")) != "1":
        return
    if (await _db.get_setting(event_key, "1")) != "1":
        return
    _notify_qt(title, message)


def _schedule_notify(event_key: str, title: str, message: str) -> None:
    """Schedule a notification coroutine safely from any context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(_notify_if_enabled(event_key, title, message))
            )
        else:
            asyncio.ensure_future(_notify_if_enabled(event_key, title, message))
    except Exception:
        pass


def notify_send_success(chat_name: str) -> None:
    _schedule_notify("notify_success", "✅ TeleFlow", f"Сообщение отправлено в {chat_name}")


def notify_send_error(chat_name: str, reason: str) -> None:
    _schedule_notify("notify_error", "❌ TeleFlow", f"Ошибка отправки в {chat_name}: {reason}")


def notify_flood_wait(phone: str, seconds: int) -> None:
    _schedule_notify("notify_flood", "⏸ TeleFlow",
                     f"Аккаунт {phone} приостановлен на {seconds}с (FloodWait)")


def notify_account_added(phone: str) -> None:
    _notify_qt("🔑 TeleFlow", f"Аккаунт {phone} добавлен")


# ── TrayManager ───────────────────────────────────────────────────────────────

class TrayManager:
    """
    Manages the system tray icon using Qt's QSystemTrayIcon.

    - No extra dependencies (pystray/PIL not needed).
    - Works on X11 and Wayland (with XWayland or libappindicator).
    - Runs purely on the Qt main thread — no threading issues.
    - Always installs a hide-on-close event so pressing X hides the window.
      Use the «Выйти» button in the sidebar to actually quit.
    """

    def __init__(self, app: "QApplication", window: "QMainWindow") -> None:
        self._app    = app
        self._window = window
        self._icon: QSystemTrayIcon | None = None
        self._available = False

    def start(self) -> None:
        """Install hide-on-close and try to show a tray icon."""
        # Always install: X hides, sidebar button quits.
        self._window.closeEvent = self._make_close_event()  # type: ignore[method-assign]

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info(
                "TrayManager: QSystemTrayIcon — no system tray available. "
                "Running without tray (use the Quit button in the sidebar to exit)."
            )
            return

        try:
            self._icon = QSystemTrayIcon(self._build_qt_icon(), self._app)
            self._icon.setToolTip("TeleFlow")
            self._icon.setContextMenu(self._build_qt_menu())
            # Double-click or left-click → show window
            self._icon.activated.connect(self._on_tray_activated)
            self._icon.show()
            self._available = True
            logger.info("TrayManager: QSystemTrayIcon started.")
            # Expose for notification helpers
            global _tray_ref
            _tray_ref = self._icon
        except Exception as e:
            logger.warning(f"TrayManager: could not create QSystemTrayIcon ({e})")
            self._available = False

    def stop(self) -> None:
        """Hide the tray icon. Call before process exit."""
        global _tray_ref
        _tray_ref = None
        if self._icon is not None:
            try:
                self._icon.hide()
            except Exception:
                pass
            self._icon = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    # ── Internal ───────────────────────────────────────────────────────────────

    def _build_qt_icon(self) -> QIcon:
        """Render TeleFlow icon via QPainter (no PIL required)."""
        from PyQt6.QtGui import QPixmap, QPolygon  # noqa: PLC0415
        from PyQt6.QtCore import QPoint  # noqa: PLC0415
        px = QPixmap(64, 64)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(41, 182, 246)))
        p.setPen(QPen(Qt.PenStyle.NoPen))
        p.drawEllipse(2, 2, 60, 60)
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.drawPolygon(QPolygon([QPoint(20, 40), QPoint(44, 32), QPoint(20, 24)]))
        p.end()
        return QIcon(px)

    def _build_qt_menu(self) -> QMenu:
        menu = QMenu()
        act_show = menu.addAction("Показать TeleFlow")
        act_show.triggered.connect(self._show_window)
        menu.addSeparator()
        act_quit = menu.addAction("Выход")
        act_quit.triggered.connect(self._on_quit)
        return menu

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def _on_quit(self) -> None:
        self.stop()
        self._app.quit()

    def _make_close_event(self) -> Callable[..., None]:
        from PyQt6.QtGui import QCloseEvent

        def _close(event: QCloseEvent) -> None:
            event.ignore()
            self._window.hide()
            if self._available and self._icon is not None:
                try:
                    self._icon.showMessage(
                        "TeleFlow",
                        "TeleFlow работает в фоновом режиме",
                        QSystemTrayIcon.MessageIcon.Information,
                        3000,
                    )
                except Exception:
                    pass

        return _close