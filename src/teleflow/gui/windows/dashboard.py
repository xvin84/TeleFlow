import asyncio
import json as _json
from datetime import datetime
from typing import Any

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QCursor, QColor, QTextDocument
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QComboBox, QLineEdit,
)

import qasync

from teleflow.core.account_manager import AccountManager
from teleflow.core.chat_manager import ChatManager
from teleflow.core.message_manager import MessageManager
from teleflow.core.scheduler import SchedulerManager
from teleflow.core.sender_engine import SenderEngine
from teleflow.core.storage.db import db
from teleflow.gui.components.chat_list import ChatListWidget
from teleflow.gui.components.message_editor import MessageEditorWidget
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.utils.qt_helpers import to_telegram_html
from teleflow.gui.windows.csv_import import CSVImportWizard
from teleflow.gui.windows.csv_msg_import import CSVMessageImportWizard
from teleflow.gui.windows.login import LoginWindow
from teleflow.gui.windows.send_rules import SendRulesDialog
from teleflow.i18n import t


def _primary_btn(label: str) -> QPushButton:
    """Solid accent-blue button — accent colour is theme-invariant."""
    btn = QPushButton(label)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {TG_BASE_COLORS['accent']};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {TG_BASE_COLORS['accent_hover']}; }}
        QPushButton:disabled {{ background-color: #a2c9f4; color: white; }}
    """)
    return btn


class DashboardWindow(QMainWindow):
    """Telegram-style 2-pane dashboard."""

    def __init__(self, account_manager: AccountManager) -> None:
        super().__init__()
        self.account_manager   = account_manager
        self.chat_manager      = ChatManager()
        self.message_manager   = MessageManager()
        self.sender_engine     = SenderEngine(self.message_manager)
        self.scheduler_manager = SchedulerManager(self.sender_engine)
        import asyncio as _asyncio
        _asyncio.ensure_future(self.scheduler_manager.start())

        self.setWindowTitle(t("app.title") + " — Dashboard")
        self.resize(1100, 720)

        self.current_phone: str | None = None

        # Storage for widgets that need inline-style refresh on theme change
        self._sep_frames: list[QFrame] = []

        self._setup_ui()

        # Apply current theme stylesheet (respects dark theme loaded from DB)
        self.setStyleSheet(theme_manager.dashboard_qss())

        # Connect theme signal AFTER _setup_ui so all refs are valid
        theme_manager.theme_changed.connect(self._apply_theme)

    def closeEvent(self, event: Any) -> None:
        # hideEvent — tray_manager intercepts close and hides. We only reach
        # this if tray_manager is NOT installed (shouldn't happen after Fix 1).
        import asyncio as _asyncio
        _asyncio.ensure_future(self.scheduler_manager.shutdown())
        event.accept()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self, _theme: str = "") -> None:
        """Re-apply all inline styles after a theme switch."""
        c = TG_BASE_COLORS

        self.setStyleSheet(theme_manager.dashboard_qss())

        self._hint_label.setStyleSheet(
            f"color: {c['text_muted']}; font-size: 11px; margin: 2px 15px 4px;"
        )

        for sep in self._sep_frames:
            sep.setStyleSheet(f"color: {c['border']};")

        self._refresh_msg_list_style()
        self._refresh_logs_table_style()
        self._update_theme_btn()

        self.chat_list_widget.refresh_theme()
        self.msg_editor.refresh_theme()

    def _update_theme_btn(self) -> None:
        if theme_manager.is_dark:
            self.btn_theme.setText(t("dashboard.theme_light"))
        else:
            self.btn_theme.setText(t("dashboard.theme_dark"))

    def _refresh_msg_list_style(self) -> None:
        c = TG_BASE_COLORS
        self.msg_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: {c['bg_main']};
                outline: none;
                color: {c['text_main']};
            }}
            QListWidget::item {{
                padding: 14px 16px;
                border-bottom: 1px solid {c['border']};
                font-size: 14px;
                color: {c['text_main']};
            }}
            QListWidget::item:hover {{ background: {c['bg_sidebar']}; }}
            QListWidget::item:selected {{ background: {c['accent']}; color: white; }}
        """)

    def _refresh_logs_table_style(self) -> None:
        c = TG_BASE_COLORS
        self.logs_table.setStyleSheet(f"""
            QTableWidget {{
                background: {c['bg_main']};
                color: {c['text_main']};
                border: none;
                gridline-color: {c['border']};
                font-size: 13px;
            }}
            QHeaderView::section {{
                background: {c['bg_sidebar']};
                color: {c['text_main']};
                padding: 8px 6px;
                border: 1px solid {c['border']};
                font-weight: bold;
                font-size: 13px;
            }}
            QTableWidget::item {{
                padding: 6px 10px;
            }}
        """)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.splitter)
        self.splitter.addWidget(self._make_sidebar())
        self.splitter.addWidget(self._make_workspace())
        self.splitter.setSizes([300, 800])

        if self.nav_buttons:
            self._on_nav_clicked(0)

    def _make_sidebar(self) -> QWidget:
        w = QWidget()
        w.setObjectName("Sidebar")
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 10, 0, 10)

        self.cb_account = QComboBox()
        self.cb_account.setObjectName("AccountSelector")
        self.cb_account.currentIndexChanged.connect(self._on_account_index_changed)
        self.cb_account.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cb_account.customContextMenuRequested.connect(self._on_account_context_menu)
        ly.addWidget(self.cb_account)

        self._hint_label = QLabel(t("dashboard.hint_remove_account"))
        self._hint_label.setStyleSheet(
            f"color: {TG_BASE_COLORS['text_muted']}; font-size: 11px; margin: 2px 15px 4px;"
        )
        ly.addWidget(self._hint_label)

        nav_ly = QVBoxLayout()
        nav_ly.setContentsMargins(0, 8, 0, 0)
        nav_ly.setSpacing(4)

        self.btn_chats    = QPushButton(t("dashboard.chats"))
        self.btn_messages = QPushButton(t("dashboard.messages"))
        self.btn_logs     = QPushButton(t("dashboard.logs"))
        self.btn_settings = QPushButton(t("dashboard.settings"))

        self.nav_buttons = [self.btn_chats, self.btn_messages, self.btn_logs, self.btn_settings]
        for idx, btn in enumerate(self.nav_buttons):
            btn.setProperty("class", "SidebarMenuBtn")
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(lambda checked, i=idx: self._on_nav_clicked(i))
            nav_ly.addWidget(btn)

        ly.addLayout(nav_ly)
        ly.addStretch()

        self.btn_theme = QPushButton()
        self.btn_theme.setProperty("class", "SidebarMenuBtn")
        self.btn_theme.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_theme.clicked.connect(self._on_toggle_theme)
        self._update_theme_btn()
        ly.addWidget(self.btn_theme)

        self.btn_add_acc = QPushButton(t("dashboard.add_account"))
        self.btn_add_acc.setProperty("class", "SidebarMenuBtn")
        self.btn_add_acc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_add_acc.clicked.connect(lambda: self.open_add_account(cancellable=True))
        ly.addWidget(self.btn_add_acc)

        btn_quit = QPushButton("⏻  " + t("dashboard.quit"))
        btn_quit.setProperty("class", "SidebarMenuBtn")
        btn_quit.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        c = TG_BASE_COLORS
        btn_quit.setStyleSheet(f"""
            QPushButton[class="SidebarMenuBtn"] {{
                background-color: transparent;
                text-align: left;
                padding: 11px 20px;
                font-size: 15px;
                font-weight: 500;
                border: none;
                border-radius: 8px;
                color: {c['danger']};
                margin: 0px 10px 4px;
            }}
            QPushButton[class="SidebarMenuBtn"]:hover {{
                background-color: {c['danger_light']};
            }}
        """)
        btn_quit.clicked.connect(self._on_quit)
        ly.addWidget(btn_quit)
        return w

    def _make_workspace(self) -> QWidget:
        w = QWidget()
        w.setAutoFillBackground(True)
        ly = QVBoxLayout(w)
        ly.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        ly.addWidget(self.stack)

        self._build_chats_view()
        self._build_messages_view()
        self._build_logs_view()
        self._build_settings_view()
        return w

    # ── View builders ──────────────────────────────────────────────────────────

    def _build_chats_view(self) -> None:
        view = QWidget()
        ly = QVBoxLayout(view)
        ly.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(20, 12, 20, 12)
        title = QLabel(t("dashboard.chats"))
        title.setProperty("class", "WorkspaceHeader")

        self.btn_import_csv = _primary_btn(t("dashboard.btn_import_csv"))
        self.btn_import_csv.clicked.connect(self._on_import_csv)

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.btn_import_csv)
        ly.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {TG_BASE_COLORS['border']};")
        self._sep_frames.append(sep)
        ly.addWidget(sep)

        self.chat_list_widget = ChatListWidget()
        self.chat_list_widget.sync_requested.connect(self._on_sync_chats)
        ly.addWidget(self.chat_list_widget)
        self.stack.addWidget(view)

    def _build_messages_view(self) -> None:
        view = QWidget()
        ly = QVBoxLayout(view)
        ly.setContentsMargins(0, 0, 0, 0)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(20, 12, 20, 12)
        title = QLabel(t("dashboard.messages"))
        title.setProperty("class", "WorkspaceHeader")

        self.btn_import_msg = _primary_btn(t("dashboard.btn_import_csv"))
        self.btn_import_msg.clicked.connect(self._on_import_msg_csv)

        self.btn_new_msg = _primary_btn(t("dashboard.btn_new_template"))
        self.btn_new_msg.clicked.connect(self._on_new_message)

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.btn_import_msg)
        hdr.addWidget(self.btn_new_msg)
        ly.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {TG_BASE_COLORS['border']};")
        self._sep_frames.append(sep)
        ly.addWidget(sep)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.msg_list = QListWidget()
        self._refresh_msg_list_style()
        self.msg_list.itemSelectionChanged.connect(self._on_msg_selection_changed)

        self.msg_editor = MessageEditorWidget()
        self.msg_editor.save_requested.connect(self._on_save_message)
        self.msg_editor.delete_requested.connect(self._on_delete_message)
        self.msg_editor.rules_requested.connect(self._on_open_rules)
        self.msg_editor.send_now_requested.connect(self._on_send_now)

        splitter.addWidget(self.msg_list)
        splitter.addWidget(self.msg_editor)
        splitter.setSizes([220, 580])
        ly.addWidget(splitter)
        self.stack.addWidget(view)

    def _build_logs_view(self) -> None:
        view = QWidget()
        ly = QVBoxLayout(view)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(20, 12, 20, 12)
        title = QLabel(t("dashboard.logs"))
        title.setProperty("class", "WorkspaceHeader")

        self.btn_refresh_logs = _primary_btn(t("dashboard.btn_refresh"))
        self.btn_refresh_logs.clicked.connect(
            lambda: asyncio.ensure_future(self._on_refresh_logs())
        )

        hdr.addWidget(title)
        hdr.addStretch()
        hdr.addWidget(self.btn_refresh_logs)
        ly.addLayout(hdr)

        # ── Filter bar ──────────────────────────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(20, 0, 20, 8)
        filter_bar.setSpacing(10)

        self.logs_search = QLineEdit()
        self.logs_search.setPlaceholderText(t("dashboard.logs_search"))
        self.logs_search.setFixedHeight(32)
        self.logs_search.textChanged.connect(self._apply_logs_filter)

        self.logs_status_filter = QComboBox()
        self.logs_status_filter.setFixedHeight(32)
        self.logs_status_filter.setFixedWidth(160)
        self.logs_status_filter.addItems([
            t("dashboard.status_all"),
            t("dashboard.status_success"),
            t("dashboard.status_error"),
            t("dashboard.status_rate_limited"),
        ])
        self.logs_status_filter.currentIndexChanged.connect(self._apply_logs_filter)

        btn_export = _primary_btn(t("dashboard.btn_export_csv"))
        btn_export.setFixedHeight(32)
        btn_export.clicked.connect(self._on_export_logs)

        filter_bar.addWidget(self.logs_search)
        filter_bar.addWidget(self.logs_status_filter)
        filter_bar.addWidget(btn_export)
        ly.addLayout(filter_bar)

        self.logs_table = QTableWidget()
        self.logs_table.setColumnCount(6)
        self.logs_table.setHorizontalHeaderLabels(
            [t("dashboard.log_col_time"), t("dashboard.log_col_account"),
             t("dashboard.log_col_chat"), t("dashboard.log_col_message"),
             t("dashboard.log_col_status"), t("dashboard.log_col_error")]
        )
        h = self.logs_table.horizontalHeader()
        if h:
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
            h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            self.logs_table.setColumnWidth(2, 250)
            self.logs_table.setColumnWidth(3, 200)
        self.logs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.logs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.logs_table.setAlternatingRowColors(True)
        vh = self.logs_table.verticalHeader()
        if vh:
            vh.setVisible(False)
        self._refresh_logs_table_style()
        ly.addWidget(self.logs_table)
        self.stack.addWidget(view)

    def _build_settings_view(self) -> None:
        """Settings panel — all sections inline."""
        from PyQt6.QtWidgets import QScrollArea, QSizePolicy, QSpacerItem  # noqa: PLC0415
        from teleflow.gui.windows.settings import (  # noqa: PLC0415
            _PasswordSection, _InterfaceSection,
            _NotificationsSection, _AutostartSection, _card,
        )

        view = QWidget()
        ly = QVBoxLayout(view)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(0)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(20, 12, 20, 12)
        title = QLabel(t("dashboard.settings"))
        title.setProperty("class", "WorkspaceHeader")
        hdr.addWidget(title)
        hdr.addStretch()
        ly.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {TG_BASE_COLORS['border']};")
        self._sep_frames.append(sep)
        ly.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_ly = QVBoxLayout(content)
        content_ly.setContentsMargins(24, 20, 24, 20)
        content_ly.setSpacing(14)

        iface_section = _InterfaceSection()
        notif_section = _NotificationsSection()
        auto_section  = _AutostartSection()
        for section in (_PasswordSection(self.account_manager), iface_section,
                        notif_section, auto_section):
            content_ly.addWidget(_card(section))
        content_ly.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        scroll.setWidget(content)
        ly.addWidget(scroll, stretch=1)

        from PyQt6.QtGui import QCursor as _QCursor  # noqa: PLC0415
        bot = QHBoxLayout()
        bot.setContentsMargins(24, 10, 24, 16)
        c = TG_BASE_COLORS
        btn_save = QPushButton(t("settings.btn_save_all"))
        btn_save.setFixedHeight(40)
        btn_save.setCursor(_QCursor(Qt.CursorShape.PointingHandCursor))
        btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {c['accent']}; color: white; border: none;
                border-radius: 8px; font-size: 13px; font-weight: 600; padding: 0 24px;
            }}
            QPushButton:hover {{ background: {c['accent_hover']}; }}
        """)

        self._settings_iface = iface_section
        self._settings_notif = notif_section
        self._settings_auto  = auto_section
        btn_save.clicked.connect(lambda: asyncio.ensure_future(self._on_save_settings()))
        bot.addStretch()
        bot.addWidget(btn_save)
        ly.addLayout(bot)
        self.stack.addWidget(view)


    # ── Navigation ─────────────────────────────────────────────────────────────

    def _on_nav_clicked(self, index: int) -> None:
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.stack.setCurrentIndex(index)

    # ── Theme toggle ──────────────────────────────────────────────────────────

    @qasync.asyncSlot()
    async def _on_toggle_theme(self) -> None:
        theme_manager.toggle()
        await theme_manager.save_to_db()

    def _on_quit(self) -> None:
        """Quit the application gracefully via the sidebar button."""
        import asyncio as _asyncio
        _asyncio.ensure_future(self.scheduler_manager.shutdown())
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()  # type: ignore[union-attr]

    async def _on_save_settings(self) -> None:
        from teleflow.i18n import set_locale as _set_locale  # noqa: PLC0415

        vals = self._settings_iface.get_values()
        for k, v in vals.items():
            await db.set_setting(k, v)
        theme_manager.set_theme(vals.get("theme", "dark"))

        new_locale = vals.get("locale", "ru")
        _set_locale(new_locale)
        await db.set_setting("locale", new_locale)

        for k, v in self._settings_notif.get_values().items():
            await db.set_setting(k, v)

        auto_vals = self._settings_auto.get_values()
        if "_autostart" in auto_vals:
            from teleflow.gui.windows.settings import _autostart_set  # noqa: PLC0415
            try:
                _autostart_set(auto_vals["_autostart"])
            except Exception as e:
                QMessageBox.warning(self, t("dashboard.settings"), t("settings.autostart_error", error=str(e)))
                return

        QMessageBox.information(self, t("dashboard.settings"), t("settings.saved_ok"))

    # ── Accounts ───────────────────────────────────────────────────────────────

    @qasync.asyncSlot()
    async def populate_accounts(self) -> None:
        self.cb_account.blockSignals(True)
        self.cb_account.clear()
        for acc in await self.account_manager.get_all_accounts():
            icon = "🟢" if acc["status"] == "online" else "🔴"
            self.cb_account.addItem(f"{icon} {acc['phone']}", userData=acc["phone"])
        self.cb_account.blockSignals(False)

        if self.cb_account.count() > 0:
            self.current_phone = self.cb_account.itemData(0)
            await self._load_local_chats()
            await self._load_local_messages()
            await self._on_refresh_logs()

    def _on_account_index_changed(self, idx: int) -> None:
        if idx >= 0:
            phone = self.cb_account.itemData(idx)
            if phone and phone != self.current_phone:
                self.current_phone = phone
                asyncio.ensure_future(self._load_local_chats())
                asyncio.ensure_future(self._load_local_messages())
                asyncio.ensure_future(self._on_refresh_logs())

    def _on_account_context_menu(self, pos: QPoint) -> None:
        idx = self.cb_account.currentIndex()
        if idx < 0:
            return
        phone = self.cb_account.itemData(idx)
        if not phone:
            return
        menu = QMenu(self)
        action = menu.addAction(t("dashboard.remove_account_menu", phone=phone))
        if menu.exec(self.cb_account.mapToGlobal(pos)) == action:
            reply = QMessageBox.question(
                self,
                t("dashboard.remove_account_title"),
                t("dashboard.remove_account_confirm", phone=phone),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                asyncio.ensure_future(self._do_remove_account(phone))

    async def _do_remove_account(self, phone: str) -> None:
        await self.account_manager.remove_account(phone)
        await self.populate_accounts()

    def open_add_account(self, cancellable: bool = True, is_first_launch: bool = False) -> None:
        wizard = LoginWindow(
            self.account_manager,
            cancellable=cancellable,
            is_first_launch=is_first_launch,
            parent=self,
        )
        if wizard.exec() == QDialog.DialogCode.Accepted:
            asyncio.ensure_future(self.populate_accounts())

    # ── Chats ──────────────────────────────────────────────────────────────────

    async def _load_local_chats(self) -> None:
        if not self.current_phone:
            return
        chats = await self.chat_manager.get_chats_for_account(self.current_phone)
        self.chat_list_widget.populate(chats)

    @qasync.asyncSlot()
    async def _on_sync_chats(self) -> None:
        if not self.current_phone:
            return
        client = self.account_manager.active_clients.get(self.current_phone)
        if not client:
            QMessageBox.warning(self, t("app.warning"), t("dashboard.account_not_connected"))
            return
        self.chat_list_widget.btn_sync.setEnabled(False)
        self.chat_list_widget.btn_sync.setText(t("dashboard.sync_in_progress"))
        if await self.chat_manager.sync_dialogs(client):
            await self._load_local_chats()
        else:
            QMessageBox.warning(self, t("dashboard.sync"), t("dashboard.sync_error"))
        self.chat_list_widget.btn_sync.setEnabled(True)
        self.chat_list_widget.btn_sync.setText("🔄 " + t("dashboard.sync"))

    def _on_import_csv(self) -> None:
        if not self.current_phone:
            return
        if CSVImportWizard(self.current_phone, parent=self).exec():
            asyncio.ensure_future(self._load_local_chats())

    # ── Messages ───────────────────────────────────────────────────────────────

    async def _load_local_messages(self) -> None:
        if not self.current_phone:
            return
        self.msg_list.clear()
        for msg in await self.message_manager.get_messages_for_account(self.current_phone):
            media_count = 0
            mp = msg.get("media_path")
            if mp:
                try:
                    parsed = _json.loads(mp)
                    media_count = len(parsed) if isinstance(parsed, list) else 1
                except Exception:
                    media_count = 1
            suffix = f"  📎{media_count}" if media_count else ""
            item = QListWidgetItem(f"{msg['title']}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, msg)
            self.msg_list.addItem(item)

    def _on_new_message(self) -> None:
        self.msg_list.clearSelection()
        self.msg_editor.activate_new()

    def _on_msg_selection_changed(self) -> None:
        items = self.msg_list.selectedItems()
        if not items:
            self.msg_editor.clear()
            return
        msg = items[0].data(Qt.ItemDataRole.UserRole)
        self.msg_editor.load_message(
            msg_id=msg["id"],
            title=msg["title"],
            text=msg["text_content"] or "",
            media_path=msg.get("media_path"),
        )

    @qasync.asyncSlot(object, str, str, object)
    async def _on_save_message(
        self, msg_id: int | None, title: str, text: str, media_json: str | None
    ) -> None:
        if not self.current_phone:
            return
        if msg_id:
            await self.message_manager.update_message(msg_id, title, text, media_json)
            QMessageBox.information(self, t("dashboard.saved"), t("dashboard.template_updated"))
        else:
            await self.message_manager.create_message(self.current_phone, title, text, media_json)
            QMessageBox.information(self, t("dashboard.created"), t("dashboard.template_created"))
        await self._load_local_messages()

    @qasync.asyncSlot(int)
    async def _on_delete_message(self, msg_id: int) -> None:
        if await self.message_manager.delete_message(msg_id):
            await self._load_local_messages()
            self.msg_editor.clear()

    def _on_open_rules(self, msg_id: int) -> None:
        """Open SendRulesDialog — unified chats + schedules + send-now window."""
        if not self.current_phone:
            return
        client = self.account_manager.active_clients.get(self.current_phone)
        if not client:
            QMessageBox.warning(self, t("app.warning"), t("dashboard.account_not_connected"))
            return

        # FIX: QTextEdit.document() can return None in PyQt6 stubs.
        # In practice it always returns a valid document, so we assert.
        doc: QTextDocument | None = self.msg_editor.inp_text.document()
        assert doc is not None, "QTextEdit.document() returned None unexpectedly"

        dialog = SendRulesDialog(
            msg_id=msg_id,
            msg_title=self.msg_editor.inp_title.text() or t("messages.title_placeholder"),
            msg_document=doc,
            media_paths=self.msg_editor.media_gallery.get_paths(),
            phone=self.current_phone,
            client=client,
            scheduler=self.scheduler_manager,
            sender_engine=self.sender_engine,
            message_manager=self.message_manager,
            parent=self,
        )
        dialog.exec()

    @qasync.asyncSlot(int)
    async def _on_send_now(self, msg_id: int) -> None:
        if not self.current_phone:
            return
        client = self.account_manager.active_clients.get(self.current_phone)
        if not client:
            QMessageBox.warning(self, t("app.warning"), t("dashboard.account_not_connected"))
            return
        self.msg_editor.btn_send_now.setEnabled(False)
        self.msg_editor.btn_send_now.setText(t("dashboard.sending"))
        try:
            assigned = await self.message_manager.get_assigned_chats_for_message(msg_id)
            if not [a for a in assigned if a.get("is_active")]:
                QMessageBox.warning(self, t("dashboard.error"), t("dashboard.no_chats_assigned"))
                return
            paths = self.msg_editor.media_gallery.get_paths()
            media_raw = _json.dumps(paths) if paths else None

            # FIX: document() can be None per stubs; assert for type safety
            doc: QTextDocument | None = self.msg_editor.inp_text.document()
            assert doc is not None
            text = to_telegram_html(doc)

            await self.sender_engine.send_message_now(
                client, self.current_phone, msg_id, text, media_raw)  # type: ignore[arg-type]
            QMessageBox.information(self, t("dashboard.send_done"), t("dashboard.send_done_msg"))
        except Exception as e:
            QMessageBox.warning(self, t("dashboard.error"), str(e))
        finally:
            self.msg_editor.btn_send_now.setEnabled(True)
            self.msg_editor.btn_send_now.setText(t("messages.btn_send_now_short"))

    def _on_import_msg_csv(self) -> None:
        if not self.current_phone:
            return
        if CSVMessageImportWizard(self.current_phone, parent=self).exec():
            asyncio.ensure_future(self._load_local_messages())

    # ── Logs ───────────────────────────────────────────────────────────────────

    def _apply_logs_filter(self) -> None:
        """Filter logs_table rows by search text and status combobox."""
        search = self.logs_search.text().strip().lower()
        status_idx = self.logs_status_filter.currentIndex()
        status_map = {0: None, 1: "success", 2: "failed", 3: "rate_limited"}
        filter_status = status_map.get(status_idx)

        for row in range(self.logs_table.rowCount()):
            hide = False
            if filter_status:
                status_item = self.logs_table.item(row, 4)
                row_status = (status_item.text() if status_item else "").lower()
                if filter_status not in row_status:
                    hide = True
            if not hide and search:
                chat_item = self.logs_table.item(row, 2)
                msg_item  = self.logs_table.item(row, 3)
                chat_text = (chat_item.text() if chat_item else "").lower()
                msg_text  = (msg_item.text() if msg_item else "").lower()
                if search not in chat_text and search not in msg_text:
                    hide = True
            self.logs_table.setRowHidden(row, hide)

    def _on_export_logs(self) -> None:
        """Export visible log rows to a CSV file."""
        import csv  # noqa: PLC0415
        from PyQt6.QtWidgets import QFileDialog  # noqa: PLC0415
        path, _ = QFileDialog.getSaveFileName(
            self, t("dashboard.logs_export_title"),
            t("dashboard.export_logs_filename"), "CSV (*.csv)"
        )
        if not path:
            return
        headers = [
            t("dashboard.log_col_time"), t("dashboard.log_col_account"),
            t("dashboard.log_col_chat"), t("dashboard.log_col_message"),
            t("dashboard.log_col_status"), t("dashboard.log_col_error"),
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for row in range(self.logs_table.rowCount()):
                    if self.logs_table.isRowHidden(row):
                        continue
                    cells = []
                    for col in range(self.logs_table.columnCount()):
                        item = self.logs_table.item(row, col)
                        cells.append(item.text() if item else "")
                    writer.writerow(cells)
            QMessageBox.information(self, t("dashboard.logs_export_title"),
                                    t("dashboard.logs_exported", path=path))
        except Exception as e:
            QMessageBox.warning(self, t("app.warning"),
                                t("dashboard.logs_export_error", error=str(e)))

    async def _on_refresh_logs(self) -> None:
        if not self.current_phone:
            return
        cursor = await db.execute(
            """
            SELECT sl.sent_at, sl.account_phone,
                COALESCE(c.title,  '(удалён) #'||CAST(sl.chat_id    AS TEXT)) AS chat_name,
                COALESCE(m.title,  '(удалён) #'||CAST(sl.message_id AS TEXT)) AS msg_title,
                sl.status, sl.error_message
            FROM send_logs sl
            LEFT JOIN chats    c ON c.id = sl.chat_id
            LEFT JOIN messages m ON m.id = sl.message_id
            WHERE sl.account_phone = ?
            ORDER BY sl.sent_at DESC LIMIT 200
            """,
            (self.current_phone,),
        )
        rows = list(await cursor.fetchall())
        self.logs_table.setRowCount(len(rows))
        status_colors = theme_manager.status_colors()
        for ri, row in enumerate(rows):
            sent_at, account, chat_name, msg_title, status, error = row
            try:
                ts = datetime.fromisoformat(str(sent_at)).strftime("%d.%m.%Y %H:%M:%S")
            except Exception:
                ts = str(sent_at)
            sl = str(status).lower()
            emoji = {"success": "✅", "rate_limited": "⏳", "failed": "❌"}.get(sl, "")
            cells = [ts, str(account), str(chat_name), str(msg_title), f"{emoji} {status}", str(error or "")]
            for ci, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if sl in status_colors:
                    bg, fg = status_colors[sl]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                self.logs_table.setItem(ri, ci, item)
        self.logs_table.resizeRowsToContents()