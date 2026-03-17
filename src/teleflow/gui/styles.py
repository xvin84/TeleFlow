"""
Centralized Qt StyleSheets + ThemeManager for TeleFlow — Telegram Desktop aesthetic.

Usage
-----
    from teleflow.gui.styles import theme_manager, TG_BASE_COLORS

    # On app startup (async):
    await theme_manager.load_from_db()
    theme_manager.apply_to_app(qt_app)

    # Toggle from any widget:
    theme_manager.toggle()

    # React to changes:
    theme_manager.theme_changed.connect(my_refresh_slot)

TG_BASE_COLORS is a *mutable* module-level dict. ThemeManager updates it in-place
on every theme switch, so any code that reads TG_BASE_COLORS at call-time (f-strings
evaluated in methods, not at module import) will automatically see the current palette.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

# ── Palettes ──────────────────────────────────────────────────────────────────

LIGHT_PALETTE: dict[str, str] = {
    "bg_main":      "#ffffff",
    "bg_sidebar":   "#f4f4f5",
    "bg_hover":     "#ebebec",
    "bg_selected":  "#3390ec",
    "border":       "#dfe1e5",
    "text_main":    "#000000",
    "text_muted":   "#707579",
    "text_light":   "#ffffff",
    "accent":       "#3390ec",
    "accent_hover": "#2b7bc6",
    "accent_light": "#e8f3fd",
    "green":        "#28a745",
    "green_hover":  "#218838",
    "green_light":  "#e9f7ec",
    "danger":       "#e53935",
    "danger_hover": "#c62828",
    "danger_light": "#fdecea",
}

DARK_PALETTE: dict[str, str] = {
    "bg_main":      "#17212b",
    "bg_sidebar":   "#0e1621",
    "bg_hover":     "#202b36",
    "bg_selected":  "#3390ec",
    "border":       "#1e2c3a",
    "text_main":    "#f5f5f5",
    "text_muted":   "#708999",
    "text_light":   "#ffffff",
    "accent":       "#3390ec",
    "accent_hover": "#2b7bc6",
    "accent_light": "#1c3145",
    "green":        "#4bb34b",
    "green_hover":  "#3da43d",
    "green_light":  "#1c3323",
    "danger":       "#e53935",
    "danger_hover": "#c62828",
    "danger_light": "#3d1e1e",
}

# ── Global mutable colour dict (backward-compatible, updated in-place) ─────────
# All code that reads TG_BASE_COLORS at call-time (f-strings inside methods)
# will see the current palette automatically after a theme switch.
TG_BASE_COLORS: dict[str, str] = dict(LIGHT_PALETTE)


# ── QSS builders ──────────────────────────────────────────────────────────────

def build_dashboard_qss(c: dict[str, str]) -> str:
    return f"""
    QMainWindow {{
        background-color: {c["bg_main"]};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 14px;
    }}
    QSplitter::handle {{
        background-color: {c["border"]};
        width: 1px;
    }}
    QWidget#Sidebar {{
        background-color: {c["bg_sidebar"]};
        border-right: 1px solid {c["border"]};
    }}
    QPushButton[class="SidebarMenuBtn"] {{
        background-color: transparent;
        text-align: left;
        padding: 11px 20px;
        font-size: 15px;
        font-weight: 500;
        border: none;
        border-radius: 8px;
        color: {c["text_main"]};
        margin: 2px 10px;
    }}
    QPushButton[class="SidebarMenuBtn"]:hover {{
        background-color: {c["bg_hover"]};
    }}
    QPushButton[class="SidebarMenuBtn"]:checked {{
        background-color: {c["accent"]};
        color: {c["text_light"]};
    }}
    QComboBox#AccountSelector {{
        padding: 10px 12px;
        border: 1px solid {c["border"]};
        border-radius: 8px;
        font-size: 14px;
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
    }}
    QComboBox#AccountSelector::drop-down {{
        border: none;
        width: 28px;
    }}
    QComboBox#AccountSelector QAbstractItemView {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        selection-background-color: {c["accent"]};
        selection-color: white;
        border: 1px solid {c["border"]};
    }}
    QComboBox#AccountSelector:hover {{
        border-color: {c["accent"]};
    }}
    QLabel[class="WorkspaceHeader"] {{
        font-size: 22px;
        font-weight: 600;
        padding: 4px 0px;
        color: {c["text_main"]};
    }}
    QPushButton[class="ActionBtn"] {{
        background-color: {c["accent"]};
        color: {c["text_light"]};
        border: none;
        border-radius: 8px;
        padding: 9px 18px;
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton[class="ActionBtn"]:hover {{
        background-color: {c["accent_hover"]};
    }}
    QPushButton[class="ActionBtn"]:disabled {{
        background-color: #a2c9f4;
        color: white;
    }}
"""


def build_chat_list_qss(c: dict[str, str]) -> str:
    return f"""
    QLineEdit#SearchInput {{
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 9px 14px;
        font-size: 14px;
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
    }}
    QLineEdit#SearchInput:focus {{
        border: 2px solid {c["accent"]};
        background-color: {c["bg_main"]};
        padding: 8px 13px;
    }}
    QPushButton[class="FilterChip"] {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_muted"]};
        border: 1px solid {c["border"]};
        padding: 6px 12px;
        font-size: 13px;
        font-weight: 500;
        border-radius: 16px;
    }}
    QPushButton[class="FilterChip"]:hover {{
        background-color: {c["bg_hover"]};
        color: {c["text_main"]};
    }}
    QPushButton[class="FilterChip"]:checked {{
        background-color: {c["accent_light"]};
        color: {c["accent"]};
        border-color: {c["accent"]};
        font-weight: 600;
    }}
    QListWidget {{
        border: none;
        background-color: {c["bg_main"]};
        color: {c["text_main"]};
        outline: none;
    }}
    QListWidget::item {{
        padding: 14px 16px;
        border-bottom: 1px solid {c["bg_sidebar"]};
        font-size: 14px;
        color: {c["text_main"]};
    }}
    QListWidget::item:hover {{
        background-color: {c["bg_sidebar"]};
    }}
    QListWidget::item:selected {{
        background-color: {c["accent"]};
        color: white;
    }}
"""


def build_login_qss(c: dict[str, str]) -> str:
    return f"""
    QDialog {{
        background-color: {c["bg_main"]};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    QLabel {{
        color: {c["text_main"]};
        font-size: 15px;
    }}
    QLabel#TitleLabel {{
        font-size: 24px;
        font-weight: 600;
        margin-bottom: 5px;
        margin-top: 10px;
    }}
    QLabel#DescLabel {{
        font-size: 14px;
        color: {c["text_muted"]};
        margin-bottom: 20px;
        line-height: 1.4;
    }}
    QLineEdit {{
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 14px 12px;
        font-size: 16px;
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
    }}
    QLineEdit:focus {{
        border: 2px solid {c["accent"]};
        background-color: {c["bg_main"]};
        padding: 13px 11px;
    }}
    QPushButton#NextBtn {{
        background-color: {c["accent"]};
        color: {c["text_light"]};
        border: none;
        border-radius: 10px;
        padding: 14px;
        font-size: 15px;
        font-weight: 600;
    }}
    QPushButton#NextBtn:hover {{
        background-color: {c["accent_hover"]};
    }}
    QPushButton#NextBtn:disabled {{
        background-color: #a2c9f4;
    }}
    QPushButton#LinkBtn {{
        background-color: transparent;
        color: {c["accent"]};
        font-size: 14px;
        font-weight: 500;
        border: none;
    }}
    QPushButton#LinkBtn:hover {{
        color: {c["accent_hover"]};
        text-decoration: underline;
    }}
    QPushButton#CancelBtn {{
        background-color: transparent;
        color: {c["danger"]};
        font-size: 14px;
        font-weight: 500;
        border: none;
    }}
    QPushButton#CancelBtn:hover {{
        text-decoration: underline;
    }}
"""


def build_full_app_qss(c: dict[str, str]) -> str:
    """
    Comprehensive stylesheet applied to QApplication.
    Covers all standard widget types so child widgets without inline styles
    automatically adopt the current theme.
    """
    return (
        build_dashboard_qss(c)
        + build_chat_list_qss(c)
        + build_login_qss(c)
        + f"""
    /* ── Generic base overrides ──────────────────────────────────── */
    QWidget {{
        background-color: {c["bg_main"]};
        color: {c["text_main"]};
    }}
    QFrame {{
        background-color: transparent;
        color: {c["text_main"]};
    }}
    QLabel {{
        background-color: transparent;
        color: {c["text_main"]};
    }}
    /* ── Input fields ─────────────────────────────────────────────── */
    QTextEdit {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        border: 1.5px solid {c["border"]};
        border-radius: 8px;
        padding: 10px 12px;
        selection-background-color: {c["accent"]};
        selection-color: white;
    }}
    QTextEdit:focus {{
        border: 2px solid {c["accent"]};
        background-color: {c["bg_main"]};
    }}
    QLineEdit {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        border: 1.5px solid {c["border"]};
        border-radius: 8px;
        padding: 8px 10px;
        selection-background-color: {c["accent"]};
        selection-color: white;
    }}
    QLineEdit:focus {{
        border: 2px solid {c["accent"]};
        background-color: {c["bg_main"]};
    }}
    /* ── Scrollbars ───────────────────────────────────────────────── */
    QScrollBar:vertical {{
        background: {c["bg_sidebar"]};
        width: 8px;
        border-radius: 4px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]};
        border-radius: 4px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["text_muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: {c["bg_sidebar"]};
        height: 8px;
        border-radius: 4px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border"]};
        border-radius: 4px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c["text_muted"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    /* ── Tables ───────────────────────────────────────────────────── */
    QTableWidget {{
        background-color: {c["bg_main"]};
        color: {c["text_main"]};
        border: none;
        gridline-color: {c["border"]};
        font-size: 13px;
    }}
    QTableWidget::item {{
        padding: 4px 8px;
    }}
    QTableWidget::item:selected {{
        background-color: {c["accent"]};
        color: white;
    }}
    QHeaderView::section {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        padding: 8px 6px;
        border: 1px solid {c["border"]};
        font-weight: bold;
        font-size: 13px;
    }}
    /* ── Dialogs ──────────────────────────────────────────────────── */
    QDialog {{
        background-color: {c["bg_main"]};
    }}
    QMessageBox {{
        background-color: {c["bg_main"]};
    }}
    QMessageBox QLabel {{
        color: {c["text_main"]};
    }}
    QMessageBox QPushButton {{
        background-color: {c["accent"]};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 16px;
        font-weight: 600;
        min-width: 64px;
    }}
    QMessageBox QPushButton:hover {{
        background-color: {c["accent_hover"]};
    }}
    /* ── Date/Time picker ─────────────────────────────────────────── */
    QDateTimeEdit {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        padding: 5px;
    }}
    QDateTimeEdit::drop-down {{ border: none; }}
    QCalendarWidget QWidget {{
        background-color: {c["bg_main"]};
        color: {c["text_main"]};
    }}
    QCalendarWidget QToolButton {{
        color: {c["text_main"]};
        background-color: {c["bg_sidebar"]};
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: {c["bg_main"]};
        color: {c["text_main"]};
        selection-background-color: {c["accent"]};
        selection-color: white;
    }}
    /* ── Tooltip ──────────────────────────────────────────────────── */
    QToolTip {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_main"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        padding: 4px 8px;
    }}
"""
    )


# ── Status colours for log table cells ────────────────────────────────────────

def build_status_colors(c: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Return (background, foreground) pairs for send_log statuses."""
    is_dark = c["bg_main"] != "#ffffff"
    return {
        "success":      (c["green_light"], "#155724" if not is_dark else "#a3cfbb"),
        "rate_limited": ("#3d3420" if is_dark else "#fff3cd",
                         "#ffd54f" if is_dark else "#856404"),
        "failed":       (c["danger_light"], "#721c24" if not is_dark else "#f8d7da"),
    }


# ── ThemeManager ──────────────────────────────────────────────────────────────

class ThemeManager(QObject):
    """
    Singleton managing light / dark theme switching.

    On theme change:
      1. Updates TG_BASE_COLORS dict in-place.
      2. Re-applies full stylesheet to the stored QApplication (if any).
      3. Emits theme_changed(name) so widgets can refresh their inline styles.
    """

    theme_changed = pyqtSignal(str)   # emits "light" or "dark"

    def __init__(self) -> None:
        super().__init__()
        self._current: str = "light"
        self._app: object = None

    # ── Read-only properties ──────────────────────────────────────────────────

    @property
    def current(self) -> str:
        return self._current

    @property
    def is_dark(self) -> bool:
        return self._current == "dark"

    @property
    def palette(self) -> dict[str, str]:
        return DARK_PALETTE if self._current == "dark" else LIGHT_PALETTE

    # ── Live QSS getters ──────────────────────────────────────────────────────

    def dashboard_qss(self) -> str:
        return build_dashboard_qss(self.palette)

    def chat_list_qss(self) -> str:
        return build_chat_list_qss(self.palette)

    def login_qss(self) -> str:
        return build_login_qss(self.palette)

    def full_app_qss(self) -> str:
        return build_full_app_qss(self.palette)

    def status_colors(self) -> dict[str, tuple[str, str]]:
        return build_status_colors(self.palette)

    # ── Switching ─────────────────────────────────────────────────────────────

    def apply_to_app(self, app: object) -> None:
        """Store the QApplication reference and apply the current theme."""
        self._app = app
        from PyQt6.QtWidgets import QApplication
        if isinstance(app, QApplication):
            app.setStyleSheet(self.full_app_qss())

    def set_theme(self, name: str) -> None:
        """Switch to 'light' or 'dark'. No-op if already that theme."""
        if name not in ("light", "dark") or name == self._current:
            return
        self._current = name
        TG_BASE_COLORS.update(self.palette)
        # Re-apply global stylesheet
        from PyQt6.QtWidgets import QApplication
        if isinstance(self._app, QApplication):
            self._app.setStyleSheet(self.full_app_qss())
        self.theme_changed.emit(name)

    def toggle(self) -> None:
        """Flip between light and dark."""
        self.set_theme("dark" if self._current == "light" else "light")

    # ── Persistence ───────────────────────────────────────────────────────────

    async def load_from_db(self) -> None:
        """
        Load the saved theme preference from the database and apply it
        (mutates TG_BASE_COLORS but does NOT emit theme_changed — widgets
        haven't been created yet at startup).
        """
        from teleflow.core.storage.db import db
        theme = await db.get_setting("theme", "light")
        self._current = theme if theme in ("light", "dark") else "light"
        TG_BASE_COLORS.update(self.palette)

    async def save_to_db(self) -> None:
        """Persist the current theme choice to the database."""
        from teleflow.core.storage.db import db
        await db.set_setting("theme", self._current)


# ── Module-level singleton ────────────────────────────────────────────────────
theme_manager = ThemeManager()


# ── Backward-compatible module-level QSS strings ──────────────────────────────
# These are evaluated at import time (always light), kept for any code that
# imported them before the ThemeManager refactor.
# Prefer theme_manager.dashboard_qss() / .chat_list_qss() / .login_qss() for
# live values that respect the current theme.
TG_DASHBOARD_STYLE = build_dashboard_qss(TG_BASE_COLORS)
TG_CHAT_LIST_STYLE = build_chat_list_qss(TG_BASE_COLORS)
TG_LOGIN_STYLE     = build_login_qss(TG_BASE_COLORS)