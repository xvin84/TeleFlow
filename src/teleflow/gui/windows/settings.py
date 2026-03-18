"""Settings window — unified save button, all sections."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from teleflow.core.account_manager import AccountManager
from teleflow.core.storage.db import db
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.i18n import t
from teleflow.utils.logger import logger
from teleflow.utils.password import hash_password, verify_password


# ── Style helpers ─────────────────────────────────────────────────────────────

def _label(text: str) -> QLabel:
    c = TG_BASE_COLORS
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-size: 11px; font-weight: 700; color: {c['text_muted']};"
        " letter-spacing: 0.5px;"
    )
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {TG_BASE_COLORS['border']};")
    return f


def _pwd(ph: str) -> QLineEdit:
    c = TG_BASE_COLORS
    w = QLineEdit()
    w.setEchoMode(QLineEdit.EchoMode.Password)
    w.setPlaceholderText(ph)
    w.setFixedHeight(40)
    w.setStyleSheet(f"""
        QLineEdit {{border:1.5px solid {c['border']};border-radius:8px;padding:0 12px;
            background:{c['bg_sidebar']};color:{c['text_main']};font-size:13px;}}
        QLineEdit:focus{{border-color:{c['accent']};}}
    """)
    return w


def _combo(items: list[str]) -> QComboBox:
    c = TG_BASE_COLORS
    w = QComboBox()
    w.setFixedHeight(36)
    w.addItems(items)
    w.setStyleSheet(f"""
        QComboBox{{border:1.5px solid {c['border']};border-radius:8px;padding:0 12px;
            background:{c['bg_sidebar']};color:{c['text_main']};font-size:13px;}}
        QComboBox::drop-down{{border:none;width:20px;}}
        QComboBox QAbstractItemView{{background:{c['bg_main']};color:{c['text_main']};
            border:1px solid {c['border']};selection-background-color:{c['accent_light']};}}
    """)
    return w


def _check(label: str) -> QCheckBox:
    c = TG_BASE_COLORS
    cb = QCheckBox(label)
    cb.setStyleSheet(f"""
        QCheckBox{{font-size:13px;color:{c['text_main']};spacing:8px;}}
        QCheckBox::indicator{{width:18px;height:18px;border:1.5px solid {c['border']};
            border-radius:4px;background:{c['bg_sidebar']};}}
        QCheckBox::indicator:checked{{background:{c['accent']};border-color:{c['accent']};}}
        QCheckBox::indicator:disabled{{background:{c['bg_main']};border-color:{c['border']};opacity:0.5;}}
        QCheckBox:disabled{{color:{c['text_muted']};}}
        QCheckBox::indicator:hover{{border-color:{c['accent']};}}
    """)
    return cb


def _primary_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setFixedHeight(38)
    btn.setStyleSheet(f"""
        QPushButton{{background:{c['accent']};color:white;border:none;border-radius:8px;
            font-size:13px;font-weight:600;padding:0 18px;}}
        QPushButton:hover{{background:{c['accent_hover']};}}
        QPushButton:disabled{{background:{c['border']};color:{c['text_muted']};}}
    """)
    return btn


def _danger_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setFixedHeight(38)
    btn.setStyleSheet(f"""
        QPushButton{{background:transparent;color:{c['danger']};border:1.5px solid {c['danger']};
            border-radius:8px;font-size:13px;font-weight:600;padding:0 18px;}}
        QPushButton:hover{{background:{c['danger_light']};}}
    """)
    return btn


# ── Autostart helpers ─────────────────────────────────────────────────────────

def _autostart_get() -> bool:
    if sys.platform.startswith("linux"):
        return (Path.home() / ".config" / "autostart" / "teleflow.desktop").exists()
    if sys.platform == "win32":
        try:
            import winreg  # type: ignore[import-untyped]
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                0,
                winreg.KEY_READ,
            )
            winreg.QueryValueEx(k, "TeleFlow")
            winreg.CloseKey(k)
            return True
        except Exception:
            return False
    return False


def _autostart_set(enabled: bool) -> None:
    if sys.platform.startswith("linux"):
        d = Path.home() / ".config" / "autostart"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "teleflow.desktop"
        if enabled:
            f.write_text(
                "[Desktop Entry]\nType=Application\nName=TeleFlow\n"
                f"Exec={sys.executable} -m teleflow\n"
                "Hidden=false\nNoDisplay=false\nX-GNOME-Autostart-enabled=true\n"
            )
        else:
            f.unlink(missing_ok=True)
    elif sys.platform == "win32":
        try:
            import winreg  # type: ignore[import-untyped]
            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if enabled:
                winreg.SetValueEx(
                    k, "TeleFlow", 0, winreg.REG_SZ,
                    f'"{sys.executable}" -m teleflow',
                )
            else:
                try:
                    winreg.DeleteValue(k, "TeleFlow")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(k)
        except Exception as e:
            raise RuntimeError(f"Registry error: {e}") from e


# ── PasswordSection ────────────────────────────────────────────────────────────

class _PasswordSection(QWidget):
    def __init__(self, acct_mgr: AccountManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = acct_mgr
        self._setup()

    def _setup(self) -> None:
        c = TG_BASE_COLORS
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(_label(t("settings.section_password")))
        ly.addWidget(_sep())

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet(f"font-size:13px;color:{c['text_main']};")
        ly.addWidget(self.lbl_status)

        self.inp_current = _pwd(t("settings.current_password"))
        self.inp_new = _pwd(t("settings.new_password"))
        self.inp_confirm = _pwd(t("settings.confirm_password"))
        for w in (self.inp_current, self.inp_new, self.inp_confirm):
            ly.addWidget(w)

        self.lbl_err = QLabel("")
        self.lbl_err.setStyleSheet(f"color:{c['danger']};font-size:12px;")
        self.lbl_err.hide()
        ly.addWidget(self.lbl_err)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_save = _primary_btn(t("settings.btn_change_password"))
        self.btn_remove = _danger_btn(t("settings.btn_remove_password"))
        self.btn_save.clicked.connect(lambda: asyncio.ensure_future(self._save()))
        self.btn_remove.clicked.connect(lambda: asyncio.ensure_future(self._remove()))
        row.addWidget(self.btn_save)
        row.addWidget(self.btn_remove)
        row.addStretch()
        ly.addLayout(row)
        asyncio.ensure_future(self._refresh())

    async def _refresh(self) -> None:
        has = bool(await db.get_setting("app_password_hash"))
        c = TG_BASE_COLORS
        self.lbl_status.setText(
            ("🔒  " + t("settings.password_is_set")) if has
            else ("🔓  " + t("settings.password_not_set"))
        )
        self.lbl_status.setStyleSheet(
            f"font-size:13px;color:{c['text_main'] if has else c['text_muted']};"
        )
        self.inp_current.setVisible(has)
        self.btn_remove.setVisible(has)

    async def _save(self) -> None:
        has = bool(await db.get_setting("app_password_hash"))
        if has:
            stored = await db.get_setting("app_password_hash")
            if not verify_password(self.inp_current.text(), stored):
                self._err(t("settings.error_wrong_current"))
                return
        pw = self.inp_new.text()
        if len(pw) < 4:
            self._err(t("lock.error_too_short"))
            return
        if pw != self.inp_confirm.text():
            self._err(t("lock.error_mismatch"))
            return
        try:
            await self._mgr.change_password(pw)
            await db.set_setting("app_password_hash", hash_password(pw))
            for w in (self.inp_current, self.inp_new, self.inp_confirm):
                w.clear()
            self.lbl_err.hide()
            await self._refresh()
            QMessageBox.information(self.window(), t("app.title"), t("settings.password_changed_ok"))
        except Exception as e:
            self._err(t("settings.error_reencrypt"))
            logger.error(e)

    async def _remove(self) -> None:
        stored = await db.get_setting("app_password_hash")
        if not stored:
            return
        if not verify_password(self.inp_current.text(), stored):
            self._err(t("settings.error_wrong_current"))
            return
        if QMessageBox.question(
            self.window(),
            t("settings.remove_password_title"),
            t("settings.remove_password_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            await self._mgr.change_password(None)
            await db.execute("DELETE FROM settings WHERE key='app_password_hash'")
            await db.commit()
            for w in (self.inp_current, self.inp_new, self.inp_confirm):
                w.clear()
            self.lbl_err.hide()
            await self._refresh()
            QMessageBox.information(self.window(), t("app.title"), t("settings.password_removed_ok"))
        except Exception as e:
            self._err(t("settings.error_reencrypt"))
            logger.error(e)

    def _err(self, m: str) -> None:
        self.lbl_err.setText(m)
        self.lbl_err.show()

    def get_values(self) -> dict:  # type: ignore[type-arg]
        return {}


# ── InterfaceSection ──────────────────────────────────────────────────────────

class _InterfaceSection(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup()

    def _setup(self) -> None:
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(10)
        ly.addWidget(_label(t("settings.section_interface")))
        ly.addWidget(_sep())

        row_t = QHBoxLayout()
        row_t.addWidget(QLabel(t("settings.theme_label")))
        self.cb_theme = _combo([t("settings.theme_dark_option"), t("settings.theme_light_option")])
        row_t.addWidget(self.cb_theme)
        row_t.addStretch()
        ly.addLayout(row_t)

        row_l = QHBoxLayout()
        row_l.addWidget(QLabel(t("settings.language_label")))
        self.cb_lang = _combo([t("settings.lang_ru"), t("settings.lang_en")])
        row_l.addWidget(self.cb_lang)
        row_l.addStretch()
        ly.addLayout(row_l)

        note = QLabel(t("settings.lang_restart_note"))
        note.setStyleSheet(f"font-size:11px;color:{TG_BASE_COLORS['text_muted']};")
        ly.addWidget(note)
        asyncio.ensure_future(self._load())

    async def _load(self) -> None:
        theme = await db.get_setting("theme", "dark")
        self.cb_theme.setCurrentIndex(0 if theme == "dark" else 1)
        lang = await db.get_setting("locale", "ru")
        self.cb_lang.setCurrentIndex(0 if lang == "ru" else 1)

    def get_values(self) -> dict:  # type: ignore[type-arg]
        return {
            "theme":  "dark" if self.cb_theme.currentIndex() == 0 else "light",
            "locale": "ru"   if self.cb_lang.currentIndex()  == 0 else "en",
        }


# ── NotificationsSection ──────────────────────────────────────────────────────

class _NotificationsSection(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup()

    def _setup(self) -> None:
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(_label(t("settings.section_notifications")))
        ly.addWidget(_sep())

        self.cb_enabled    = _check(t("settings.notify_enable"))
        self.cb_on_success = _check(t("settings.notify_on_success"))
        self.cb_on_error   = _check(t("settings.notify_on_error"))
        self.cb_on_flood   = _check(t("settings.notify_on_flood"))
        for cb in (self.cb_enabled, self.cb_on_success, self.cb_on_error, self.cb_on_flood):
            ly.addWidget(cb)

        self.cb_enabled.toggled.connect(self._toggle_subs)
        asyncio.ensure_future(self._load())

    async def _load(self) -> None:
        enabled = (await db.get_setting("notify_enabled", "1")) == "1"
        self.cb_enabled.setChecked(enabled)
        self.cb_on_success.setChecked((await db.get_setting("notify_success", "1")) == "1")
        self.cb_on_error.setChecked((await db.get_setting("notify_error",   "1")) == "1")
        self.cb_on_flood.setChecked((await db.get_setting("notify_flood",   "1")) == "1")
        self._toggle_subs(enabled)

    def _toggle_subs(self, enabled: bool) -> None:
        for cb in (self.cb_on_success, self.cb_on_error, self.cb_on_flood):
            cb.setEnabled(enabled)

    def get_values(self) -> dict:  # type: ignore[type-arg]
        return {
            "notify_enabled": "1" if self.cb_enabled.isChecked()    else "0",
            "notify_success": "1" if self.cb_on_success.isChecked() else "0",
            "notify_error":   "1" if self.cb_on_error.isChecked()   else "0",
            "notify_flood":   "1" if self.cb_on_flood.isChecked()   else "0",
        }


# ── AutostartSection ──────────────────────────────────────────────────────────

class _AutostartSection(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup()

    def _setup(self) -> None:
        c = TG_BASE_COLORS
        ly = QVBoxLayout(self)
        ly.setContentsMargins(0, 0, 0, 0)
        ly.setSpacing(8)
        ly.addWidget(_label(t("settings.section_autostart")))
        ly.addWidget(_sep())

        if sys.platform not in ("linux", "win32") and not sys.platform.startswith("linux"):
            ly.addWidget(QLabel(t("settings.autostart_not_supported")))
            return

        self.cb_auto = _check(t("settings.autostart_enable"))
        self.cb_auto.setChecked(_autostart_get())
        ly.addWidget(self.cb_auto)

        note_text = (
            "Linux: ~/.config/autostart/teleflow.desktop"
            if sys.platform.startswith("linux")
            else "Windows: HKCU\\...\\Run"
        )
        note = QLabel(note_text)
        note.setStyleSheet(f"font-size:11px;color:{c['text_muted']};")
        ly.addWidget(note)

    def get_values(self) -> dict:  # type: ignore[type-arg]
        if not hasattr(self, "cb_auto"):
            return {}
        return {"_autostart": self.cb_auto.isChecked()}


# ── SettingsWindow ────────────────────────────────────────────────────────────

class SettingsWindow(QDialog):
    def __init__(self, acct_mgr: AccountManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mgr = acct_mgr
        self.setWindowTitle(t("dashboard.settings"))
        self.resize(520, 600)
        self.setModal(True)
        self.setStyleSheet(theme_manager.login_qss())
        self._build()

    def _build(self) -> None:
        c = TG_BASE_COLORS
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title = QLabel(t("dashboard.settings"))
        title.setStyleSheet(
            f"font-size:18px;font-weight:700;color:{c['text_main']};padding:24px 30px 12px;"
        )
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")

        box = QWidget()
        box.setStyleSheet("background:transparent;")
        ly = QVBoxLayout(box)
        ly.setContentsMargins(30, 0, 30, 20)
        ly.setSpacing(24)

        self._pwd  = _PasswordSection(self._mgr)
        self._iface = _InterfaceSection()
        self._notif = _NotificationsSection()
        self._auto  = _AutostartSection()
        for w in (self._pwd, self._iface, self._notif, self._auto):
            ly.addWidget(w)
        ly.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        scroll.setWidget(box)
        root.addWidget(scroll, stretch=1)

        bot = QHBoxLayout()
        bot.setContentsMargins(30, 12, 30, 20)
        bot.setSpacing(10)
        btn_save  = _primary_btn(t("settings.btn_save_all"))
        btn_close = QPushButton(t("settings.btn_close"))
        btn_close.setFixedHeight(38)
        btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_close.setStyleSheet(f"""
            QPushButton{{background:transparent;color:{c['text_muted']};
                border:1.5px solid {c['border']};border-radius:8px;font-size:13px;padding:0 16px;}}
            QPushButton:hover{{background:{c['bg_hover']};color:{c['text_main']};}}
        """)
        btn_save.clicked.connect(lambda: asyncio.ensure_future(self._save_all()))
        btn_close.clicked.connect(self.accept)
        bot.addStretch()
        bot.addWidget(btn_save)
        bot.addWidget(btn_close)
        root.addLayout(bot)

    async def _save_all(self) -> None:
        for k, v in self._iface.get_values().items():
            await db.set_setting(k, v)
        theme = self._iface.get_values().get("theme", "dark")
        theme_manager.set_theme(theme)

        for k, v in self._notif.get_values().items():
            await db.set_setting(k, v)

        auto_vals = self._auto.get_values()
        if "_autostart" in auto_vals:
            try:
                _autostart_set(auto_vals["_autostart"])
            except Exception as e:
                QMessageBox.warning(self, t("settings.section_autostart"), t("settings.autostart_error", error=str(e)))
                return

        QMessageBox.information(self, t("app.title"), t("settings.saved_ok"))