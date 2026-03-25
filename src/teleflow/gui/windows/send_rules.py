"""
SendRulesDialog — единое окно управления правилами отправки шаблона.

Объединяет:
  • Назначение чатов (кто получает сообщение)
  • Управление расписаниями (когда отправлять)
  • Отправка «Сейчас»

Открывается из редактора сообщений по кнопке «⚙ Управление отправкой».

Fixes applied:
  - _render_schedules / _render_chats: call removeWidget() BEFORE deleteLater()
    so Qt layout indices stay consistent and the stretch item is always found
    at the correct position. Without this, ghost layout items caused incorrect
    count() values and schedules appeared not to render on the second open.
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from teleflow.core.storage.db import db
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.i18n import t
from teleflow.utils.logger import logger
from teleflow.utils.qt_helpers import to_telegram_html

if TYPE_CHECKING:
    from teleflow.core.message_manager import MessageManager
    from teleflow.core.scheduler import SchedulerManager
    from teleflow.core.telegram.client import TeleflowClient
    from PyQt6.QtGui import QTextDocument


# ── Schedule row widget ────────────────────────────────────────────────────────

class _ScheduleRow(QFrame):
    delete_clicked = pyqtSignal(str)
    edit_clicked   = pyqtSignal(str)
    pause_clicked  = pyqtSignal(str)
    resume_clicked = pyqtSignal(str)

    _MODE_ICONS = {
        "one_time":      "📅",
        "daily_fixed":   "🕐",
        "weekday":       "📆",
        "interval":      "🔁",
        "random_window": "🎲",
    }

    def __init__(
        self,
        schedule_id: str,
        description: str,
        mode: str,
        is_paused: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.schedule_id = schedule_id
        self._is_paused  = is_paused
        self._mode       = mode
        self._setup_ui(description)
        self._apply_style()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self, description: str) -> None:
        ly = QHBoxLayout(self)
        ly.setContentsMargins(12, 10, 12, 10)
        ly.setSpacing(10)

        icon = QLabel(self._MODE_ICONS.get(self._mode, "⏰"))
        icon.setStyleSheet("font-size: 18px; border: none; background: transparent;")
        icon.setFixedWidth(26)
        ly.addWidget(icon)

        info = QVBoxLayout()
        info.setSpacing(2)

        lbl = QLabel(description)
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {TG_BASE_COLORS['text_main']};"
            " border: none; background: transparent;"
        )
        info.addWidget(lbl)

        status_text = (
            t("schedule.paused") if self._is_paused
            else (t("schedule.status_done") if self._mode == "one_time"
                  else t("schedule.status_active"))
        )
        status_color = TG_BASE_COLORS["text_muted"] if self._is_paused else (
            TG_BASE_COLORS["text_muted"] if self._mode == "one_time" else TG_BASE_COLORS.get("green", "#4CAF50")
        )
        lbl_status = QLabel(status_text)
        lbl_status.setStyleSheet(
            f"font-size: 11px; color: {status_color}; border: none; background: transparent;"
        )
        info.addWidget(lbl_status)
        ly.addLayout(info)
        ly.addStretch()

        if self._mode != "one_time":
            btn_pause = self._mk_btn(
                "▶" if self._is_paused else "⏸",
                "Возобновить" if self._is_paused else "Пауза"
            )
            btn_pause.clicked.connect(
                lambda: (self.resume_clicked if self._is_paused else self.pause_clicked)
                .emit(self.schedule_id)
            )
            ly.addWidget(btn_pause)

        btn_edit = self._mk_btn("✏", "Редактировать")
        btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self.schedule_id))
        ly.addWidget(btn_edit)

        btn_del = self._mk_btn("🗑", "Удалить", danger=True)
        btn_del.clicked.connect(lambda: self.delete_clicked.emit(self.schedule_id))
        ly.addWidget(btn_del)

    def _mk_btn(self, icon: str, tip: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(icon)
        btn.setToolTip(tip)
        btn.setFixedSize(34, 32)
        c = TG_BASE_COLORS
        col = c["danger"] if danger else c["accent"]
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {c['border']};
                border-radius: 7px;
                font-size: 15px;
                color: {col};
            }}
            QPushButton:hover {{
                background: {c['bg_hover']};
                border-color: {col};
            }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _apply_style(self) -> None:
        c = TG_BASE_COLORS
        self.setStyleSheet(f"""
            QFrame {{
                background: {c['bg_sidebar']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
        """)

    def _on_theme_changed(self, _: str = "") -> None:
        self._apply_style()


# ── Chat row widget ────────────────────────────────────────────────────────────

class _ChatRow(QFrame):
    remove_clicked = pyqtSignal(int)  # chat db id

    _TYPE_ICONS = {
        "channel": "📢",
        "group":   "👥",
        "user":    "👤",
        "bot":     "🤖",
    }

    def __init__(self, chat_id: int, title: str, chat_type: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chat_db_id = chat_id
        self._setup_ui(title, chat_type)
        self._apply_style()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _setup_ui(self, title: str, chat_type: str) -> None:
        ly = QHBoxLayout(self)
        ly.setContentsMargins(12, 8, 12, 8)
        ly.setSpacing(10)

        icon = QLabel(self._TYPE_ICONS.get(chat_type, "💬"))
        icon.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        icon.setFixedWidth(22)
        ly.addWidget(icon)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"font-size: 13px; color: {TG_BASE_COLORS['text_main']};"
            " border: none; background: transparent;"
        )
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        ly.addWidget(lbl)

        type_badge = QLabel(chat_type)
        type_badge.setStyleSheet(
            f"font-size: 10px; color: {TG_BASE_COLORS['text_muted']};"
            f" background: {TG_BASE_COLORS['bg_main']};"
            " border-radius: 4px; padding: 2px 6px;"
        )
        ly.addWidget(type_badge)

        btn = QPushButton("✕")
        btn.setFixedSize(26, 26)
        c = TG_BASE_COLORS
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                font-size: 13px; color: {c['text_muted']};
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background: {c['danger_light']}; color: {c['danger']};
            }}
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Убрать чат")
        btn.clicked.connect(lambda: self.remove_clicked.emit(self.chat_db_id))
        ly.addWidget(btn)

    def _apply_style(self) -> None:
        c = TG_BASE_COLORS
        self.setStyleSheet(f"""
            QFrame {{
                background: {c['bg_sidebar']};
                border: 1px solid {c['border']};
                border-radius: 8px;
            }}
        """)

    def _on_theme_changed(self, _: str = "") -> None:
        self._apply_style()


# ── SendRulesDialog ────────────────────────────────────────────────────────────

class SendRulesDialog(QDialog):
    """
    Unified window for managing send rules of a message template.
    Handles: chat assignment, schedule management, send-now.
    """

    def __init__(
        self,
        msg_id: int,
        msg_title: str,
        msg_document: "QTextDocument",
        media_paths: list[str],
        phone: str,
        client: "TeleflowClient",
        scheduler: "SchedulerManager",
        message_manager: "MessageManager",
        sender_engine: "Any | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.msg_id          = msg_id
        self.msg_title       = msg_title
        self._doc            = msg_document
        self._media_paths    = media_paths
        self.phone           = phone
        self.client          = client
        self.scheduler       = scheduler
        self.message_manager = message_manager
        self._sender_engine  = sender_engine  # reuse existing instance

        self._chat_rows:     list[_ChatRow]     = []
        self._schedule_rows: list[_ScheduleRow] = []
        self._all_chats:     list[dict[str, Any]] = []  # all synced chats for picker

        self.setWindowTitle(f"Правила отправки — {msg_title}")
        self.resize(820, 580)
        self.setMinimumSize(700, 480)
        self.setModal(True)
        self.setStyleSheet(theme_manager.login_qss())
        theme_manager.theme_changed.connect(self._on_theme_changed)

        self._setup_ui()
        asyncio.ensure_future(self._load_all())

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        title_lbl = QLabel("⚙  Правила отправки")
        title_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {TG_BASE_COLORS['text_main']};"
        )
        subtitle = QLabel(self.msg_title)
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {TG_BASE_COLORS['text_muted']};"
        )
        hdr.addWidget(title_lbl)
        hdr.addWidget(subtitle)
        hdr.addStretch()
        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {TG_BASE_COLORS['border']};")
        root.addWidget(sep)

        # Main splitter: chats | schedules
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: " + TG_BASE_COLORS['border'] + "; }")

        splitter.addWidget(self._build_chats_panel())
        splitter.addWidget(self._build_schedules_panel())
        splitter.setSizes([340, 460])
        root.addWidget(splitter, stretch=1)

        # Bottom bar
        bot = QHBoxLayout()
        bot.setSpacing(10)

        self.btn_send_now = QPushButton("⚡  Отправить сейчас")
        self.btn_send_now.setFixedHeight(40)
        self.btn_send_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_now.clicked.connect(self._on_send_now)

        btn_close = QPushButton("Закрыть")
        btn_close.setFixedHeight(40)
        btn_close.setFixedWidth(100)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)

        self.btn_close_ref = btn_close
        self._apply_bottom_styles()
        bot.addWidget(self.btn_send_now)
        bot.addStretch()
        bot.addWidget(btn_close)
        root.addLayout(bot)

    def _build_chats_panel(self) -> QWidget:
        panel = QWidget()
        ly = QVBoxLayout(panel)
        ly.setContentsMargins(0, 0, 8, 0)
        ly.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        self.lbl_chats_header = QLabel("💬  Чаты")
        self.lbl_chats_header.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {TG_BASE_COLORS['text_main']};"
        )
        self.lbl_chats_count = QLabel("0")
        self.lbl_chats_count.setStyleSheet(
            f"font-size: 12px; color: {TG_BASE_COLORS['text_muted']};"
            f" background: {TG_BASE_COLORS['bg_sidebar']};"
            " border-radius: 10px; padding: 2px 8px;"
        )
        hdr.addWidget(self.lbl_chats_header)
        hdr.addWidget(self.lbl_chats_count)
        hdr.addStretch()
        ly.addLayout(hdr)

        # Search / add
        search_hdr = QHBoxLayout()
        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("🔍 Добавить чат...")
        self.chat_search.setFixedHeight(34)
        self.chat_search.setStyleSheet(self._inp_style())
        self.chat_search.textChanged.connect(self._on_chat_search_changed)
        search_hdr.addWidget(self.chat_search)
        ly.addLayout(search_hdr)

        # Dropdown for chat picker (hidden by default)
        self.chat_picker = QListWidget()
        self.chat_picker.setMaximumHeight(160)
        self.chat_picker.hide()
        self.chat_picker.setStyleSheet(self._list_style())
        self.chat_picker.itemClicked.connect(self._on_chat_picker_select)
        ly.addWidget(self.chat_picker)

        # Scroll area for assigned chats
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._chats_container = QWidget()
        self._chats_container.setStyleSheet("background: transparent;")
        self._chats_ly = QVBoxLayout(self._chats_container)
        self._chats_ly.setContentsMargins(0, 0, 0, 0)
        self._chats_ly.setSpacing(4)
        self._chats_ly.addStretch()
        scroll.setWidget(self._chats_container)
        ly.addWidget(scroll, stretch=1)

        self.lbl_no_chats = QLabel("\ud83d\udcac  " + t("send_rules.no_chats_assigned"))
        self.lbl_no_chats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_chats.setWordWrap(True)
        self.lbl_no_chats.setStyleSheet(
            f"font-size: 13px; color: {TG_BASE_COLORS['text_muted']}; padding: 20px;"
        )
        ly.addWidget(self.lbl_no_chats)

        return panel

    def _build_schedules_panel(self) -> QWidget:
        panel = QWidget()
        ly = QVBoxLayout(panel)
        ly.setContentsMargins(8, 0, 0, 0)
        ly.setSpacing(10)

        hdr = QHBoxLayout()
        self.lbl_sched_header = QLabel("📅  Расписания")
        self.lbl_sched_header.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {TG_BASE_COLORS['text_main']};"
        )
        self.lbl_sched_count = QLabel("0")
        self.lbl_sched_count.setStyleSheet(
            f"font-size: 12px; color: {TG_BASE_COLORS['text_muted']};"
            f" background: {TG_BASE_COLORS['bg_sidebar']};"
            " border-radius: 10px; padding: 2px 8px;"
        )
        btn_add_sched = QPushButton("＋  Добавить расписание")
        btn_add_sched.setFixedHeight(32)
        btn_add_sched.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_sched.setStyleSheet(self._accent_btn_style())
        btn_add_sched.clicked.connect(self._on_add_schedule)

        hdr.addWidget(self.lbl_sched_header)
        hdr.addWidget(self.lbl_sched_count)
        hdr.addStretch()
        hdr.addWidget(btn_add_sched)
        ly.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._scheds_container = QWidget()
        self._scheds_container.setStyleSheet("background: transparent;")
        self._scheds_ly = QVBoxLayout(self._scheds_container)
        self._scheds_ly.setContentsMargins(0, 0, 0, 0)
        self._scheds_ly.setSpacing(6)
        self._scheds_ly.addStretch()
        scroll.setWidget(self._scheds_container)
        ly.addWidget(scroll, stretch=1)

        self.lbl_no_scheds = QLabel(
            "\ud83d\udcc5  " + t("schedule.no_schedules_hint")
        )
        self.lbl_no_scheds.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_scheds.setWordWrap(True)
        self.lbl_no_scheds.setStyleSheet(
            f"font-size: 13px; color: {TG_BASE_COLORS['text_muted']}; padding: 20px;"
        )
        ly.addWidget(self.lbl_no_scheds)

        return panel

    # ── Styles ─────────────────────────────────────────────────────────────────

    def _inp_style(self) -> str:
        c = TG_BASE_COLORS
        return f"""
            QLineEdit {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                background: {c['bg_sidebar']};
                color: {c['text_main']};
            }}
            QLineEdit:focus {{ border-color: {c['accent']}; }}
        """

    def _list_style(self) -> str:
        c = TG_BASE_COLORS
        return f"""
            QListWidget {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                background: {c['bg_main']};
                color: {c['text_main']};
                font-size: 13px;
                padding: 4px;
            }}
            QListWidget::item {{ padding: 6px 8px; border-radius: 6px; }}
            QListWidget::item:hover {{ background: {c['bg_hover']}; }}
            QListWidget::item:selected {{ background: {c['accent_light']}; color: {c['accent']}; }}
        """

    def _accent_btn_style(self) -> str:
        c = TG_BASE_COLORS
        return f"""
            QPushButton {{
                background: {c['accent_light']};
                color: {c['accent']};
                border: 1.5px solid {c['accent']};
                border-radius: 8px;
                padding: 0 14px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {c['bg_hover']}; }}
        """

    def _apply_bottom_styles(self) -> None:
        c = TG_BASE_COLORS
        self.btn_send_now.setStyleSheet(f"""
            QPushButton {{
                background: {c['green']};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 0 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {c['green_hover']}; }}
            QPushButton:disabled {{ background: {c['bg_sidebar']}; color: {c['text_muted']}; }}
        """)
        self.btn_close_ref.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {c['text_muted']};
                border: 1.5px solid {c['border']};
                border-radius: 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {c['bg_hover']}; color: {c['text_main']}; }}
        """)

    def _on_theme_changed(self, _: str = "") -> None:
        self.setStyleSheet(theme_manager.login_qss())
        self._apply_bottom_styles()
        self.chat_search.setStyleSheet(self._inp_style())
        self.chat_picker.setStyleSheet(self._list_style())
        asyncio.ensure_future(self._load_all())

    # ── Data loading ───────────────────────────────────────────────────────────

    async def _load_all(self) -> None:
        await asyncio.gather(
            self._load_chats(),
            self._load_schedules(),
            self._load_all_chats_for_picker(),
        )

    async def _load_chats(self) -> None:
        rows = await self.message_manager.get_assigned_chats_for_message(self.msg_id)
        self._render_chats([r for r in rows if r.get("is_active")])

    async def _load_all_chats_for_picker(self) -> None:
        from teleflow.core.chat_manager import ChatManager  # noqa: PLC0415
        cm = ChatManager()
        self._all_chats = await cm.get_chats_for_account(self.phone)

    async def _load_schedules(self) -> None:
        rows = await db.list_schedules_for_message(self.msg_id)
        paused: set[str] = set()
        try:
            live = await self.scheduler.list_schedules()
            paused = {s["id"] for s in live if s.get("paused")}
        except Exception:
            pass
        self._render_schedules(rows, paused)

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render_chats(self, rows: list[dict[str, Any]]) -> None:
        # ── FIX: remove widgets from layout BEFORE deleteLater so Qt layout
        # indices stay correct and the stretch item is always at count()-1.
        for r in self._chat_rows:
            self._chats_ly.removeWidget(r)
            r.deleteLater()
        self._chat_rows.clear()

        n = len(rows)
        self.lbl_chats_count.setText(str(n))
        c = TG_BASE_COLORS
        if n == 0:
            badge_bg  = c["danger_light"]
            badge_fg  = c["danger"]
        else:
            badge_bg  = c["green_light"]
            badge_fg  = c["green"]
        self.lbl_chats_count.setStyleSheet(
            f"font-size: 12px; color: {badge_fg};"
            f" background: {badge_bg};"
            " border-radius: 10px; padding: 2px 8px;"
        )
        self.lbl_no_chats.setVisible(n == 0)
        self.btn_send_now.setEnabled(n > 0)
        if n == 0:
            self.btn_send_now.setToolTip(t("send_rules.no_chats_title") + ": " + t("send_rules.no_chats_msg"))
        else:
            self.btn_send_now.setToolTip("")

        # Insert rows before the stretch (which is now reliably at index 0)
        stretch_item = self._chats_ly.takeAt(self._chats_ly.count() - 1)
        for row_data in rows:
            row = _ChatRow(
                chat_id=row_data["db_chat_id"],
                title=row_data.get("title") or f"#{row_data['db_chat_id']}",
                chat_type=row_data.get("type", "user"),
            )
            row.remove_clicked.connect(self._on_remove_chat)
            self._chats_ly.addWidget(row)
            self._chat_rows.append(row)
        if stretch_item:
            self._chats_ly.addItem(stretch_item)

    def _render_schedules(self, rows: list[dict[str, Any]], paused: set[str]) -> None:
        # ── FIX: same pattern — removeWidget first, then deleteLater.
        for r in self._schedule_rows:
            self._scheds_ly.removeWidget(r)
            r.deleteLater()
        self._schedule_rows.clear()

        n = len(rows)
        self.lbl_sched_count.setText(str(n))
        self.lbl_no_scheds.setVisible(n == 0)

        stretch_item = self._scheds_ly.takeAt(self._scheds_ly.count() - 1)
        for row_data in rows:
            sid = row_data["id"]
            row = _ScheduleRow(
                schedule_id=sid,
                description=row_data["description"],
                mode=row_data["mode"],
                is_paused=sid in paused,
            )
            row.delete_clicked.connect(self._on_delete_schedule)
            row.edit_clicked.connect(self._on_edit_schedule)
            row.pause_clicked.connect(self._on_pause_schedule)
            row.resume_clicked.connect(self._on_resume_schedule)
            self._scheds_ly.addWidget(row)
            self._schedule_rows.append(row)
        if stretch_item:
            self._scheds_ly.addItem(stretch_item)

    # ── Chat actions ───────────────────────────────────────────────────────────

    def _on_chat_search_changed(self, text: str) -> None:
        text = text.strip().lower()
        self.chat_picker.clear()
        if not text or not self._all_chats:
            self.chat_picker.hide()
            return

        assigned_db_ids = {r.chat_db_id for r in self._chat_rows}

        matches = [
            c for c in self._all_chats
            if text in (c.get("title") or "").lower()
            and c.get("id") not in assigned_db_ids
        ][:12]

        if not matches:
            self.chat_picker.hide()
            return

        type_icons = {"channel": "📢", "group": "👥", "user": "👤", "bot": "🤖"}
        for c in matches:
            icon = type_icons.get(c.get("type", ""), "💬")
            item = QListWidgetItem(f"{icon}  {c.get('title', str(c.get('chat_id', '?')))}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.chat_picker.addItem(item)
        self.chat_picker.show()

    def _on_chat_picker_select(self, item: QListWidgetItem) -> None:
        chat_data = item.data(Qt.ItemDataRole.UserRole)
        if not chat_data:
            return
        self.chat_picker.hide()
        self.chat_search.clear()
        asyncio.ensure_future(self._add_chat(chat_data))

    async def _add_chat(self, chat_data: dict[str, Any]) -> None:
        db_chat_id = chat_data.get("id")
        if db_chat_id is None:
            return

        chat_type = chat_data.get("type", "")
        if chat_type in ("channel", "group"):
            tg_chat_id = chat_data.get("chat_id")
            if tg_chat_id and not await self._check_can_send(tg_chat_id):
                # FIX: use QTimer to avoid locking up qasync event loop with nested Qt event loop
                QTimer.singleShot(0, lambda: QMessageBox.warning(
                    self, "Нет прав",
                    f"Нет прав для отправки в «{chat_data.get('title', str(tg_chat_id))}».\n"
                    "Убедитесь, что вы являетесь администратором с правом отправки сообщений."
                ))
                return

        rows = await self.message_manager.get_assigned_chats_for_message(self.msg_id)
        current_ids = [r["db_chat_id"] for r in rows if r.get("is_active")]
        if db_chat_id not in current_ids:
            current_ids.append(db_chat_id)
        await self.message_manager.update_message_assignments(self.msg_id, current_ids)
        await self._load_chats()

    async def _check_can_send(self, tg_chat_id: int) -> bool:
        """Return True if the account can send messages to this chat."""
        try:
            perms = await self.client.client.get_permissions(tg_chat_id)
            return bool(getattr(perms, "post_messages", True))
        except Exception:
            return True

    def _on_remove_chat(self, chat_db_id: int) -> None:
        asyncio.ensure_future(self._remove_chat(chat_db_id))

    async def _remove_chat(self, chat_db_id: int) -> None:
        rows = await self.message_manager.get_assigned_chats_for_message(self.msg_id)
        new_ids = [r["db_chat_id"] for r in rows if r.get("is_active") and r["db_chat_id"] != chat_db_id]
        await self.message_manager.update_message_assignments(self.msg_id, new_ids)
        await self._load_chats()

    # ── Schedule actions ───────────────────────────────────────────────────────

    def _on_add_schedule(self) -> None:
        QTimer.singleShot(0, self._show_schedule_wizard)

    def _show_schedule_wizard(self, prefill: Any = None) -> None:
        from teleflow.gui.windows.schedule_wizard import ScheduleWizard  # noqa: PLC0415
        wizard = ScheduleWizard(self, prefill=prefill)
        if not wizard.exec():
            return
        config = wizard.result_config
        if config is None:
            return
        asyncio.ensure_future(self._create_schedule(config))

    async def _create_schedule(self, config: Any) -> None:
        media_raw = _json.dumps(self._media_paths) if self._media_paths else None
        text = to_telegram_html(self._doc)

        schedule_id = self.scheduler.add_schedule(
            config, self.client, self.phone, self.msg_id, text, media_raw
        )
        if not schedule_id:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать расписание.\nПроверьте, запущен ли планировщик.")
            return

        import json  # noqa: PLC0415
        await db.save_schedule(
            schedule_id=schedule_id,
            msg_id=self.msg_id,
            account_phone=self.phone,
            mode=config.mode,
            config_json=json.dumps(config.__dict__, default=str),
            description=config.human_description(),
        )
        await self._load_schedules()

    def _on_delete_schedule(self, schedule_id: str) -> None:
        reply = QMessageBox.question(
            self, "Удалить расписание",
            "Удалить это расписание? Отправка по нему прекратится.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.scheduler.remove_schedule(schedule_id)
        asyncio.ensure_future(self._after_delete_schedule(schedule_id))

    async def _after_delete_schedule(self, schedule_id: str) -> None:
        await db.delete_schedule(schedule_id)
        await self._load_schedules()

    def _on_edit_schedule(self, schedule_id: str) -> None:
        asyncio.ensure_future(self._load_schedule_for_edit(schedule_id))

    async def _load_schedule_for_edit(self, schedule_id: str) -> None:
        from teleflow.core.scheduler import ScheduleConfig  # noqa: PLC0415
        import json  # noqa: PLC0415
        from datetime import datetime  # noqa: PLC0415

        cursor = await db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        row = await cursor.fetchone()
        if not row:
            return
        try:
            cfg_dict = json.loads(row["config_json"])
            if cfg_dict.get("run_datetime"):
                cfg_dict["run_datetime"] = datetime.fromisoformat(str(cfg_dict["run_datetime"]))
            config = ScheduleConfig(**cfg_dict)
        except Exception as e:
            logger.error(f"Failed to load config for edit: {e}")
            return

        def _do_edit() -> None:
            from teleflow.gui.windows.schedule_wizard import ScheduleWizard  # noqa: PLC0415
            wizard = ScheduleWizard(self, prefill=config)
            if not wizard.exec():
                return
            new_config = wizard.result_config
            if new_config is None:
                return
            self.scheduler.remove_schedule(schedule_id)
            asyncio.ensure_future(self._replace_schedule(schedule_id, new_config))

        QTimer.singleShot(0, _do_edit)

    async def _replace_schedule(self, old_id: str, new_config: Any) -> None:
        await db.delete_schedule(old_id)
        await self._create_schedule(new_config)

    def _on_pause_schedule(self, schedule_id: str) -> None:
        self.scheduler.pause_schedule(schedule_id)
        asyncio.ensure_future(self._load_schedules())

    def _on_resume_schedule(self, schedule_id: str) -> None:
        self.scheduler.resume_schedule(schedule_id)
        asyncio.ensure_future(self._load_schedules())

    # ── Send now ───────────────────────────────────────────────────────────────

    def _on_send_now(self) -> None:
        asyncio.ensure_future(self._do_send_now())

    async def _do_send_now(self) -> None:
        from teleflow.core.sender_engine import SenderEngine  # noqa: PLC0415

        assigned = await self.message_manager.get_assigned_chats_for_message(self.msg_id)
        if not [a for a in assigned if a.get("is_active")]:
            QTimer.singleShot(0, lambda: QMessageBox.warning(
                self, "Нет чатов",
                "Добавьте хотя бы один чат в левой панели."
            ))
            return

        self.btn_send_now.setEnabled(False)
        self.btn_send_now.setText("⏳ Отправка...")
        try:
            sender = SenderEngine(self.message_manager)
            media_raw = _json.dumps(self._media_paths) if self._media_paths else None
            text = to_telegram_html(self._doc)
            await sender.send_message_now(
                self.client, self.phone, self.msg_id, text, media_raw
            )
            QTimer.singleShot(0, lambda: QMessageBox.information(self, "✅ Готово", "Сообщение отправлено во все назначенные чаты!"))
        except Exception as e:
            err_msg = str(e)
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, "Ошибка отправки", err_msg))
        finally:
            self.btn_send_now.setEnabled(True)
            self.btn_send_now.setText("⚡  Отправить сейчас")
