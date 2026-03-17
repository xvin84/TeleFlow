"""
ScheduleManagerWidget — секция «Активные расписания» в редакторе шаблонов.

Отображает список расписаний для выбранного шаблона, позволяет:
  • Удалять расписание (APScheduler + БД)
  • Редактировать расписание (открывает ScheduleWizard с предзаполнением)
  • Ставить на паузу / возобновлять
"""
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from teleflow.core.storage.db import db
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.utils.logger import logger

if TYPE_CHECKING:
    from teleflow.core.scheduler import SchedulerManager


# ── Single schedule row ────────────────────────────────────────────────────────


class _ScheduleRow(QFrame):
    """One row: description label + pause/edit/delete buttons."""

    delete_clicked = pyqtSignal(str)   # schedule_id
    edit_clicked   = pyqtSignal(str)   # schedule_id
    pause_clicked  = pyqtSignal(str)   # schedule_id
    resume_clicked = pyqtSignal(str)   # schedule_id

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
        theme_manager.theme_changed.connect(lambda _: self._apply_style())

    def _setup_ui(self, description: str) -> None:
        ly = QHBoxLayout(self)
        ly.setContentsMargins(10, 8, 10, 8)
        ly.setSpacing(8)

        # Icon by mode
        icons = {
            "one_time":      "📅",
            "daily_fixed":   "🕐",
            "weekday":       "📆",
            "interval":      "🔁",
            "random_window": "🎲",
        }
        icon = QLabel(icons.get(self._mode, "⏰"))
        icon.setStyleSheet("font-size: 16px; border: none; background: transparent;")
        icon.setFixedWidth(24)
        ly.addWidget(icon)

        self.lbl_desc = QLabel(description)
        self.lbl_desc.setStyleSheet(
            f"font-size: 13px; color: {TG_BASE_COLORS['text_main']};"
            "border: none; background: transparent;"
        )
        self.lbl_desc.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        ly.addWidget(self.lbl_desc)

        if self._is_paused:
            lbl_paused = QLabel("На паузе")
            lbl_paused.setStyleSheet(
                f"font-size: 11px; color: {TG_BASE_COLORS['text_muted']};"
                f" background: {TG_BASE_COLORS['bg_sidebar']};"
                " border-radius: 4px; padding: 2px 6px;"
            )
            ly.addWidget(lbl_paused)

        self.btn_pause = self._make_btn(
            "⏸" if not self._is_paused else "▶",
            "Пауза" if not self._is_paused else "Возобновить",
        )
        self.btn_pause.clicked.connect(
            lambda: (self.resume_clicked if self._is_paused else self.pause_clicked)
            .emit(self.schedule_id)
        )
        # Don't show pause for one-time schedules
        if self._mode == "one_time":
            self.btn_pause.hide()

        self.btn_edit   = self._make_btn("✏", "Редактировать")
        self.btn_delete = self._make_btn("🗑", "Удалить", danger=True)

        self.btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self.schedule_id))
        self.btn_delete.clicked.connect(lambda: self.delete_clicked.emit(self.schedule_id))

        for btn in (self.btn_pause, self.btn_edit, self.btn_delete):
            ly.addWidget(btn)

    def _make_btn(self, icon: str, tooltip: str, danger: bool = False) -> QPushButton:
        btn = QPushButton(icon)
        btn.setToolTip(tooltip)
        btn.setFixedSize(30, 28)
        c = TG_BASE_COLORS
        color = c["danger"] if danger else c["accent"]
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 6px;
                font-size: 14px;
                color: {color};
            }}
            QPushButton:hover {{
                background-color: {c['bg_hover']};
                border-color: {color};
            }}
        """)
        return btn

    def _apply_style(self) -> None:
        c = TG_BASE_COLORS
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {c['bg_sidebar']};
                border: 1px solid {c['border']};
                border-radius: 8px;
            }}
        """)


# ── ScheduleManagerWidget ──────────────────────────────────────────────────────


class ScheduleManagerWidget(QWidget):
    """
    Section widget displayed inside MessageEditorWidget.
    Shows active schedules for the current template and lets the user
    manage them without leaving the editor.
    """

    # Emitted when the user wants to create a new schedule (same as «Отправить…» button)
    add_schedule_requested = pyqtSignal(int)  # msg_id
    # Emitted when a schedule has been removed / paused — callers may want to log
    schedule_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._msg_id: int | None = None
        self._scheduler: "SchedulerManager | None" = None
        self._rows: list[_ScheduleRow] = []
        self._setup_ui()
        theme_manager.theme_changed.connect(lambda _: self._apply_header_style())

    def set_scheduler(self, scheduler: "SchedulerManager") -> None:
        self._scheduler = scheduler

    # ── UI setup ───────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Header row
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        self.lbl_header = QLabel("📅  Активные расписания")
        self._apply_header_style()
        hdr.addWidget(self.lbl_header)
        hdr.addStretch()

        self.btn_add = QPushButton("＋  Добавить")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_btn_add_style()
        self.btn_add.clicked.connect(self._on_add_clicked)
        hdr.addWidget(self.btn_add)
        root.addLayout(hdr)

        # Scroll area for rows
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setMaximumHeight(200)
        self._scroll.setMinimumHeight(0)
        self._scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        self._scroll.hide()

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_ly = QVBoxLayout(self._list_widget)
        self._list_ly.setContentsMargins(0, 0, 0, 0)
        self._list_ly.setSpacing(4)
        self._scroll.setWidget(self._list_widget)
        root.addWidget(self._scroll)

        # Empty state label
        self.lbl_empty = QLabel("Нет активных расписаний")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet(
            f"font-size: 12px; color: {TG_BASE_COLORS['text_muted']}; padding: 8px;"
        )
        root.addWidget(self.lbl_empty)

    def _apply_header_style(self) -> None:
        c = TG_BASE_COLORS
        self.lbl_header.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {c['text_main']};"
        )

    def _apply_btn_add_style(self) -> None:
        c = TG_BASE_COLORS
        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent_light']};
                color: {c['accent']};
                border: 1.5px solid {c['accent']};
                border-radius: 8px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; }}
            QPushButton:disabled {{
                background-color: {c['bg_sidebar']};
                color: {c['text_muted']};
                border-color: {c['border']};
            }}
        """)

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_for_message(self, msg_id: int) -> None:
        """Load schedules for the given message. Must be called from async context."""
        self._msg_id = msg_id
        self.btn_add.setEnabled(True)
        asyncio.ensure_future(self._refresh())

    def clear(self) -> None:
        self._msg_id = None
        self.btn_add.setEnabled(False)
        self._clear_rows()
        self.lbl_empty.show()
        self._scroll.hide()

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _refresh(self) -> None:
        if self._msg_id is None:
            return

        db_rows = await db.list_schedules_for_message(self._msg_id)

        # Check pause status from APScheduler
        paused_ids: set[str] = set()
        if self._scheduler:
            live = await self._scheduler.list_schedules()
            paused_ids = {s["id"] for s in live if s.get("paused")}

        self._clear_rows()

        if not db_rows:
            self.lbl_empty.show()
            self._scroll.hide()
            return

        self.lbl_empty.hide()
        self._scroll.show()

        for row_data in db_rows:
            sid = row_data["id"]
            row = _ScheduleRow(
                schedule_id=sid,
                description=row_data["description"],
                mode=row_data["mode"],
                is_paused=sid in paused_ids,
            )
            row.delete_clicked.connect(self._on_delete)
            row.edit_clicked.connect(self._on_edit)
            row.pause_clicked.connect(self._on_pause)
            row.resume_clicked.connect(self._on_resume)
            self._list_ly.addWidget(row)
            self._rows.append(row)

    def _clear_rows(self) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()

    def _on_add_clicked(self) -> None:
        if self._msg_id is not None:
            self.add_schedule_requested.emit(self._msg_id)

    def _on_delete(self, schedule_id: str) -> None:
        reply = QMessageBox.question(
            self,
            "Удалить расписание",
            "Удалить это расписание? Отправка по нему прекратится.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self._scheduler:
            self._scheduler.remove_schedule(schedule_id)
        else:
            asyncio.ensure_future(db.delete_schedule(schedule_id))
        asyncio.ensure_future(self._refresh())
        self.schedule_changed.emit()

    def _on_edit(self, schedule_id: str) -> None:
        """Open ScheduleWizard pre-filled with existing config."""
        asyncio.ensure_future(self._do_edit(schedule_id))

    async def _do_edit(self, schedule_id: str) -> None:
        from teleflow.gui.windows.schedule_wizard import ScheduleWizard  # noqa: PLC0415
        from teleflow.core.scheduler import ScheduleConfig               # noqa: PLC0415
        from datetime import datetime                                      # noqa: PLC0415
        from PyQt6.QtCore import QTimer                                    # noqa: PLC0415

        # Load config from DB
        cursor = await db.execute(
            "SELECT * FROM schedules WHERE id = ?", (schedule_id,)
        )
        row = await cursor.fetchone()
        if not row:
            logger.warning(f"Schedule {schedule_id} not found in DB for editing")
            return

        try:
            cfg_dict = json.loads(row["config_json"])
            if "run_datetime" in cfg_dict and cfg_dict["run_datetime"]:
                cfg_dict["run_datetime"] = datetime.fromisoformat(cfg_dict["run_datetime"])
            config = ScheduleConfig(**cfg_dict)
        except Exception as e:
            logger.error(f"Failed to deserialize ScheduleConfig for {schedule_id}: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить конфиг расписания:\n{e}")
            return

        def _show_wizard() -> None:
            wizard = ScheduleWizard(self, prefill=config)
            if not wizard.exec():
                return
            new_config = wizard.result_config
            if new_config is None:
                return
            # Remove old schedule and add new one
            if self._scheduler:
                self._scheduler.remove_schedule(schedule_id)
                # Re-add with same msg_id
                msg_id = row["msg_id"]
                # We don't have text/media here — reload from DB in dashboard
                # So we emit a signal for the dashboard to handle
                self.add_schedule_requested.emit(msg_id)
            asyncio.ensure_future(self._refresh())

        QTimer.singleShot(0, _show_wizard)

    def _on_pause(self, schedule_id: str) -> None:
        if self._scheduler:
            self._scheduler.pause_schedule(schedule_id)
        asyncio.ensure_future(self._refresh())
        self.schedule_changed.emit()

    def _on_resume(self, schedule_id: str) -> None:
        if self._scheduler:
            self._scheduler.resume_schedule(schedule_id)
        asyncio.ensure_future(self._refresh())
        self.schedule_changed.emit()
