import asyncio
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from teleflow.core.storage.db import db
from teleflow.core.account_manager import AccountManager
from teleflow.gui.windows.dashboard import DashboardWindow
from teleflow.gui.windows.app_lock import AppLockDialog, SetupPasswordDialog
from teleflow.gui.styles import theme_manager
from teleflow.core.dispatch import set_main_loop
from teleflow.utils.crypto import generate_salt, salt_to_hex, salt_from_hex
from teleflow.utils.password import hash_password
from teleflow.utils.logger import logger
from teleflow.gui.tray_manager import TrayManager
from teleflow.i18n import set_locale


class TeleFlowApp:
    def __init__(self) -> None:
        logger.info("Initializing TeleFlow application...")
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("TeleFlow")
        self.app.setApplicationVersion("0.1.0")
        # Prevent auto-quit when setup/lock dialogs close before dashboard is shown
        self.app.setQuitOnLastWindowClosed(False)
        self.account_manager: AccountManager | None = None
        self.dashboard: DashboardWindow | None = None

    async def run(self) -> None:
        logger.info("Connecting to database...")
        await db.connect()
        set_main_loop(asyncio.get_event_loop())

        # Load saved locale BEFORE creating any widgets so all labels use correct language
        logger.info("Loading locale preference...")
        locale = await db.get_setting("locale", "ru")
        set_locale(locale if locale in ("ru", "en") else "ru")

        logger.info("Loading theme preference...")
        await theme_manager.load_from_db()
        theme_manager.apply_to_app(self.app)

        salt = await self._ensure_app_salt()
        session_password = await self._resolve_password()

        if session_password is None:
            logger.info("Lock screen dismissed without authentication. Exiting.")
            self.app.quit()
            return

        self.account_manager = AccountManager(
            session_password=session_password if session_password else None,
            salt=salt,
        )
        logger.info("Loading accounts...")
        await self.account_manager.load_accounts()
        all_accounts = await self.account_manager.get_all_accounts()

        self.dashboard = DashboardWindow(self.account_manager)
        await self.dashboard.populate_accounts()

        # Re-enable normal quit now that the main window is ready
        self.app.setQuitOnLastWindowClosed(True)

        if not all_accounts:
            logger.info("No accounts found. Opening add-account wizard.")
            self.dashboard.show()
            QTimer.singleShot(
                0,
                lambda: self.dashboard.open_add_account(  # type: ignore[union-attr]
                    cancellable=True, is_first_launch=True
                ),
            )
        else:
            self.dashboard.show()

        # Start system tray (Wayland without XWayland: silently no-ops)
        tray = TrayManager(self.app, self.dashboard)
        tray.start()

    async def _ensure_app_salt(self) -> bytes:
        salt_hex = await db.get_setting("app_salt")
        if salt_hex:
            return salt_from_hex(salt_hex)
        logger.info("First run — generating installation salt.")
        new_salt = generate_salt()
        await db.set_setting("app_salt", salt_to_hex(new_salt))
        return new_salt

    async def _resolve_password(self) -> str | None:
        pwd_hash: str | None = await db.get_setting("app_password_hash")
        if pwd_hash:
            dialog = AppLockDialog(stored_hash=pwd_hash)
            if dialog.exec():
                return dialog.entered_password
            return None
        else:
            dialog_setup = SetupPasswordDialog()
            dialog_setup.exec()
            if dialog_setup.password_chosen:
                pwd = dialog_setup.password_chosen
                try:
                    new_hash = hash_password(pwd)
                    await db.set_setting("app_password_hash", new_hash)
                    logger.info("Application password set by user.")
                except Exception as e:
                    logger.error(f"Failed to save app password: {e}")
                return pwd
            else:
                logger.info("Password setup skipped by user.")
                return ""