"""
Application password dialogs.

Two dialogs are provided:

* ``SetupPasswordDialog``  — shown on first launch (or when no password is set).
  Lets the user choose a password or skip.
* ``AppLockDialog``        — shown on every subsequent launch when a password
  *is* set.  Blocks the UI until the correct password is entered.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.i18n import t
from teleflow.utils.password import verify_password


# ── helpers ───────────────────────────────────────────────────────────────────

def _action_btn(label: str, danger: bool = False) -> QPushButton:
    c = TG_BASE_COLORS
    bg      = c["danger"]        if danger else c["accent"]
    bg_hov  = c["danger_hover"]  if danger else c["accent_hover"]
    btn = QPushButton(label)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setFixedHeight(40)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg};
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 0 20px;
        }}
        QPushButton:hover {{ background: {bg_hov}; }}
        QPushButton:disabled {{ background: {c["border"]}; color: {c["text_muted"]}; }}
    """)
    return btn


def _link_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent;
            border: none;
            color: {c["text_muted"]};
            font-size: 12px;
        }}
        QPushButton:hover {{ color: {c["accent"]}; }}
    """)
    return btn


def _password_field(placeholder: str) -> QLineEdit:
    c = TG_BASE_COLORS
    inp = QLineEdit()
    inp.setEchoMode(QLineEdit.EchoMode.Password)
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(42)
    inp.setStyleSheet(f"""
        QLineEdit {{
            border: 1.5px solid {c["border"]};
            border-radius: 8px;
            padding: 0 14px;
            background: {c["bg_sidebar"]};
            color: {c["text_main"]};
            font-size: 14px;
        }}
        QLineEdit:focus {{ border-color: {c["accent"]}; }}
    """)
    return inp


# ── SetupPasswordDialog ───────────────────────────────────────────────────────

class SetupPasswordDialog(QDialog):
    """Shown on first launch.  The user may set a password or skip.

    After ``exec()`` check ``password_chosen``:
      - ``None``  → user skipped (no password protection)
      - ``str``   → the chosen plain-text password (must be hashed and stored
                    by the caller)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.password_chosen: str | None = None

        self.setWindowTitle(t("lock.setup_title"))
        self.setFixedSize(420, 480)
        self.setModal(True)
        self.setStyleSheet(theme_manager.login_qss())
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 32)
        root.setSpacing(0)

        c = TG_BASE_COLORS

        # Icon
        icon = QLabel("🔒")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        root.addWidget(icon)
        root.addSpacing(14)

        # Title
        title = QLabel(t("lock.setup_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {c['text_main']};")
        root.addWidget(title)
        root.addSpacing(6)

        # Description
        desc = QLabel(t("lock.setup_desc"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {c['text_muted']}; line-height: 1.4;")
        root.addWidget(desc)
        root.addSpacing(24)

        # Password inputs
        self.inp_pwd  = _password_field(t("lock.new_password_placeholder"))
        self.inp_pwd2 = _password_field(t("lock.confirm_password_placeholder"))
        root.addWidget(self.inp_pwd)
        root.addSpacing(10)
        root.addWidget(self.inp_pwd2)

        # Error label (hidden until needed)
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {c['danger']}; font-size: 12px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.hide()
        root.addSpacing(6)
        root.addWidget(self.lbl_error)

        root.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Confirm button
        self.btn_set = _action_btn(t("lock.btn_set_password"))
        self.btn_set.clicked.connect(self._on_set)
        root.addWidget(self.btn_set)
        root.addSpacing(10)

        # Skip link
        btn_skip = _link_btn(t("lock.btn_skip"))
        btn_skip.clicked.connect(self._on_skip)
        root.addWidget(btn_skip, alignment=Qt.AlignmentFlag.AlignCenter)

        # Enter submits
        self.inp_pwd2.returnPressed.connect(self._on_set)

    def _on_set(self) -> None:
        pwd  = self.inp_pwd.text()
        pwd2 = self.inp_pwd2.text()

        if len(pwd) < 4:
            self._show_error(t("lock.error_too_short"))
            return
        if pwd != pwd2:
            self._show_error(t("lock.error_mismatch"))
            return

        self.password_chosen = pwd
        self.accept()

    def _on_skip(self) -> None:
        self.password_chosen = None
        self.accept()

    def _show_error(self, msg: str) -> None:
        self.lbl_error.setText(msg)
        self.lbl_error.show()


# ── AppLockDialog ─────────────────────────────────────────────────────────────

class AppLockDialog(QDialog):
    """Shown on every startup when an app password is set.

    After a successful ``exec() == Accepted``, read ``entered_password`` for
    the plain-text password (needed to initialise ``SessionManager``).
    """

    def __init__(self, stored_hash: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stored_hash = stored_hash
        self.entered_password: str = ""

        self.setWindowTitle(t("lock.unlock_title"))
        self.setFixedSize(380, 380)
        self.setModal(True)
        self.setStyleSheet(theme_manager.login_qss())
        # Prevent closing without a password
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 32)
        root.setSpacing(0)

        c = TG_BASE_COLORS

        icon = QLabel("🔐")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")
        root.addWidget(icon)
        root.addSpacing(14)

        title = QLabel(t("lock.unlock_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {c['text_main']};")
        root.addWidget(title)
        root.addSpacing(6)

        desc = QLabel(t("lock.unlock_desc"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {c['text_muted']};")
        root.addWidget(desc)
        root.addSpacing(24)

        self.inp_pwd = _password_field(t("lock.password_placeholder"))
        root.addWidget(self.inp_pwd)

        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {c['danger']}; font-size: 12px;")
        self.lbl_error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_error.hide()
        root.addSpacing(6)
        root.addWidget(self.lbl_error)

        root.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        btn_unlock = _action_btn(t("lock.btn_unlock"))
        btn_unlock.clicked.connect(self._on_unlock)
        root.addWidget(btn_unlock)

        self.inp_pwd.returnPressed.connect(self._on_unlock)

        # Focus the field immediately
        self.inp_pwd.setFocus()

    def _on_unlock(self) -> None:
        pwd = self.inp_pwd.text()
        if not pwd:
            self._show_error(t("lock.error_empty"))
            return

        if verify_password(pwd, self._stored_hash):
            self.entered_password = pwd
            self.accept()
        else:
            self._show_error(t("lock.error_wrong"))
            self.inp_pwd.clear()
            self.inp_pwd.setFocus()

    def _show_error(self, msg: str) -> None:
        self.lbl_error.setText(msg)
        self.lbl_error.show()