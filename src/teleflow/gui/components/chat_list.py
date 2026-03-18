from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QButtonGroup, QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from teleflow.i18n import t
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from typing import Any


class ChatListWidget(QWidget):
    """
    Chat list with working search + type filters, and a clearly visible Sync button.
    """

    selection_changed = pyqtSignal(list)
    sync_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._all_chats: list[dict[str, Any]] = []
        self._setup_ui()
        # Apply current theme (respects dark mode loaded from DB at startup)
        self.setStyleSheet(theme_manager.chat_list_qss())

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        # --- Search + Sync row ---
        search_layout = QHBoxLayout()
        self.inp_search = QLineEdit()
        self.inp_search.setObjectName("SearchInput")
        self.inp_search.setPlaceholderText(t("dashboard.search_chats"))
        self.inp_search.textChanged.connect(self._apply_filter)

        self.btn_sync = QPushButton("🔄 " + t("dashboard.sync"))
        self.btn_sync.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._apply_sync_btn_style()
        self.btn_sync.clicked.connect(self.sync_requested.emit)

        search_layout.addWidget(self.inp_search)
        search_layout.addWidget(self.btn_sync)
        layout.addLayout(search_layout)

        # --- Filter chips ---
        filters_layout = QHBoxLayout()
        filters_layout.setSpacing(4)

        self.btn_filter_all      = QPushButton(t("dashboard.filter_all"))
        self.btn_filter_users    = QPushButton(t("dashboard.filter_personal"))
        self.btn_filter_groups   = QPushButton(t("dashboard.filter_groups"))
        self.btn_filter_channels = QPushButton(t("dashboard.filter_channels"))

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        for btn in (self.btn_filter_all, self.btn_filter_users,
                    self.btn_filter_groups, self.btn_filter_channels):
            btn.setProperty("class", "FilterChip")
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.filter_group.addButton(btn)
            filters_layout.addWidget(btn)

        self.btn_filter_all.setChecked(True)
        filters_layout.addStretch()

        self.btn_filter_all.toggled.connect(lambda _: self._apply_filter())
        self.btn_filter_users.toggled.connect(lambda _: self._apply_filter())
        self.btn_filter_groups.toggled.connect(lambda _: self._apply_filter())
        self.btn_filter_channels.toggled.connect(lambda _: self._apply_filter())

        layout.addLayout(filters_layout)

        # --- Chat count label ---
        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet(
            f"color: {TG_BASE_COLORS['text_muted']}; font-size: 12px; margin-left: 2px;"
        )
        layout.addWidget(self.lbl_count)

        # --- List ---
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

    def _apply_sync_btn_style(self) -> None:
        c = TG_BASE_COLORS
        self.btn_sync.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 600;
                min-width: 110px;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:disabled {{ background-color: #a2c9f4; color: white; }}
        """)

    def refresh_theme(self, _theme: str = "") -> None:
        """Re-apply stylesheet and inline styles after a theme switch."""
        self.setStyleSheet(theme_manager.chat_list_qss())
        self._apply_sync_btn_style()
        self.lbl_count.setStyleSheet(
            f"color: {TG_BASE_COLORS['text_muted']}; font-size: 12px; margin-left: 2px;"
        )

    # ------------------------------------------------------------------
    def populate(self, chats: list[dict[str, Any]]) -> None:
        """Populate the list; keeps a full copy for re-filtering."""
        self._all_chats = chats
        self.list_widget.clear()

        icon_map = {"User": "👤", "Group": "👥", "Channel": "📢"}
        for chat in chats:
            item = QListWidgetItem()
            c_type = chat.get("type", "User")
            icon = icon_map.get(c_type, "💬")
            item.setText(f"{icon}  {chat['title']}")
            item.setData(Qt.ItemDataRole.UserRole, chat)
            self.list_widget.addItem(item)

        self._apply_filter()

    # ------------------------------------------------------------------
    def _apply_filter(self) -> None:
        """Filter list rows by the active type chip AND the search text."""
        text = self.inp_search.text().lower()
        checked = self.filter_group.checkedButton()

        # FIX: checked is QAbstractButton | None; dict key is QPushButton.
        # Use isinstance guard so mypy is satisfied.
        type_map: dict[QPushButton, str] = {
            self.btn_filter_users:    "User",
            self.btn_filter_groups:   "Group",
            self.btn_filter_channels: "Channel",
        }
        active_type = type_map.get(checked) if isinstance(checked, QPushButton) else None

        visible = 0
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if not item:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            text_match = not text or text in item.text().lower()
            type_match = (active_type is None) or (data.get("type") == active_type)
            hidden = not (text_match and type_match)
            item.setHidden(hidden)
            if not hidden:
                visible += 1

        total = self.list_widget.count()
        self.lbl_count.setText(t("dashboard.showing_count", visible=visible, total=total))

    # ------------------------------------------------------------------
    def _on_selection_changed(self) -> None:
        selected_data = [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.list_widget.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        ]
        self.selection_changed.emit(selected_data)