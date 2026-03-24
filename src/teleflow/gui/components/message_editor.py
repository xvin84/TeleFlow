"""
MessageEditorWidget — редактор шаблонов сообщений.
Поддерживает до 10 медиафайлов разных типов.

Хранение текста:
- В БД хранится нативный Qt HTML (inp_text.toHtml()) — для корректной
  загрузки обратно в редактор (сохраняются переносы строк и форматирование).
- При отправке вызывается to_telegram_html() уже из текущего документа.
"""

import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTextEdit, QPushButton, QLabel, QFileDialog,
    QMessageBox, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont, QPixmap
from teleflow.i18n import t
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.utils.qt_helpers import telegram_html_to_display_html, set_code_format, is_code_format

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv"}
AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".m4a", ".flac"}
MAX_MEDIA  = 10


def _file_icon(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "🖼"
    if ext in VIDEO_EXTS:
        return "🎬"
    if ext in AUDIO_EXTS:
        return "🎵"
    return "📄"


def _parse_media_paths(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [p for p in parsed if p] if isinstance(parsed, list) else [raw]
    except (json.JSONDecodeError, ValueError):
        return [raw]


def _encode_media_paths(paths: list[str]) -> str | None:
    return json.dumps(paths) if paths else None


# ── Single media card ─────────────────────────────────────────────────────────

class _MediaCard(QFrame):
    removed = pyqtSignal(int)

    W, H = 76, 64

    def __init__(self, path: str, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        self.path   = path
        self.setFixedSize(self.W + 4, self.H + 28)
        self.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {TG_BASE_COLORS['border']};
                border-radius: 8px;
                background-color: {TG_BASE_COLORS['bg_sidebar']};
            }}
        """)

        ly = QVBoxLayout(self)
        ly.setContentsMargins(3, 3, 3, 3)
        ly.setSpacing(2)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setFixedSize(self.W, self.H)

        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTS:
            pix = QPixmap(path).scaled(
                self.W, self.H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pix) if not pix.isNull() else thumb.setText("🖼️")
        else:
            thumb.setText(_file_icon(ext))
            thumb.setStyleSheet("font-size: 28px; border: none;")
        ly.addWidget(thumb)

        fname = os.path.basename(path)
        name  = QLabel(fname[:10] + "…" if len(fname) > 10 else fname)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(
            f"font-size: 10px; color: {TG_BASE_COLORS['text_muted']}; border: none;"
        )
        ly.addWidget(name)

        self._btn_rm = QPushButton("×", self)
        self._btn_rm.setFixedSize(20, 20)
        self._btn_rm.setStyleSheet(f"""
            QPushButton {{
                background-color: {TG_BASE_COLORS['danger']};
                color: white;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                border: none;
                padding: 0;
            }}
            QPushButton:hover {{ background-color: {TG_BASE_COLORS['danger_hover']}; }}
        """)
        self._btn_rm.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_rm.move(self.W - 8, 2)
        self._btn_rm.raise_()
        self._btn_rm.clicked.connect(lambda: self.removed.emit(self._index))

    def update_index(self, i: int) -> None:
        self._index = i


# ── Media gallery ─────────────────────────────────────────────────────────────

class _MediaGallery(QWidget):
    files_changed = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        header = QHBoxLayout()
        lbl = QLabel(t("messages.media_title"))
        lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {TG_BASE_COLORS['text_main']};"
        )
        self.lbl_count = QLabel(f"0 / {MAX_MEDIA}")
        self.lbl_count.setStyleSheet(
            f"font-size: 12px; color: {TG_BASE_COLORS['text_muted']};"
        )
        header.addWidget(lbl)
        header.addStretch()
        header.addWidget(self.lbl_count)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setFixedHeight(108)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._row = QHBoxLayout(self._inner)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(6)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._inner)
        outer.addWidget(scroll)

        self.btn_add = QPushButton(t("messages.btn_add_file"))
        self.btn_add.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._apply_btn_add_style()
        self.btn_add.clicked.connect(self._on_add)
        outer.addWidget(self.btn_add)

        self._rebuild()

    def _apply_btn_add_style(self) -> None:
        c = TG_BASE_COLORS
        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent_light']};
                color: {c['accent']};
                border: 1.5px solid {c['accent']};
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c['bg_hover']};
                border-color: {c['accent_hover']};
            }}
            QPushButton:disabled {{
                background-color: {c['bg_sidebar']};
                color: {c['text_muted']};
                border-color: {c['border']};
            }}
        """)

    def refresh_theme(self) -> None:
        self._apply_btn_add_style()
        self._rebuild()

    def set_paths(self, paths: list[str]) -> None:
        self._paths = list(paths)
        self._rebuild()

    def get_paths(self) -> list[str]:
        return list(self._paths)

    def _rebuild(self) -> None:
        # FIX: properly check widget() before calling deleteLater()
        while self._row.count():
            item = self._row.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        for i, p in enumerate(self._paths):
            card = _MediaCard(p, i)
            card.removed.connect(self._on_remove)
            self._row.addWidget(card)

        n = len(self._paths)
        self.btn_add.setEnabled(n < MAX_MEDIA)
        self.lbl_count.setText(f"{n} / {MAX_MEDIA}")
        if n >= MAX_MEDIA:
            self.lbl_count.setStyleSheet(
                f"font-size: 12px; color: {TG_BASE_COLORS['danger']}; font-weight: 600;"
            )
        else:
            self.lbl_count.setStyleSheet(
                f"font-size: 12px; color: {TG_BASE_COLORS['text_muted']};"
            )

    def _on_remove(self, idx: int) -> None:
        if 0 <= idx < len(self._paths):
            del self._paths[idx]
            self._rebuild()
            self.files_changed.emit(list(self._paths))

    def _on_add(self) -> None:
        remaining = MAX_MEDIA - len(self._paths)
        if remaining <= 0:
            return
        filter_str = (
            "Все файлы (*.png *.jpg *.jpeg *.gif *.webp *.bmp "
            "*.mp4 *.mov *.avi *.mkv *.mp3 *.ogg *.wav *.m4a "
            "*.pdf *.doc *.docx *.xls *.xlsx *.zip *.txt);;"
            "Изображения (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;"
            "Видео (*.mp4 *.mov *.avi *.mkv);;"
            "Документы (*.pdf *.doc *.docx *.xls *.xlsx)"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, t("messages.select_media"), "", filter_str)
        added = 0
        for p in paths:
            if added >= remaining:
                break
            if p and p not in self._paths:
                self._paths.append(p)
                added += 1
        if added:
            self._rebuild()
            self.files_changed.emit(list(self._paths))


# ── MessageEditorWidget ───────────────────────────────────────────────────────

class MessageEditorWidget(QWidget):
    save_requested   = pyqtSignal(object, str, str, object)
    delete_requested = pyqtSignal(int)
    rules_requested    = pyqtSignal(int)   # open SendRulesDialog
    send_now_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_msg_id: int | None = None
        self._setup_ui()
        theme_manager.theme_changed.connect(self.refresh_theme)

    def _setup_ui(self) -> None:
        self._root_ly = QVBoxLayout(self)
        self._root_ly.setContentsMargins(24, 20, 24, 20)
        self._root_ly.setSpacing(14)

        self.lbl_hint = QLabel(t("messages.hint_text"))
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hint.setWordWrap(True)
        self._apply_hint_style()
        self._root_ly.addWidget(self.lbl_hint, stretch=1)

        self._editor = QWidget()
        ed_ly = QVBoxLayout(self._editor)
        ed_ly.setContentsMargins(0, 0, 0, 0)
        ed_ly.setSpacing(12)

        self.inp_title = QLineEdit()
        self.inp_title.setPlaceholderText(t("messages.title_placeholder"))
        self._apply_inp_title_style()
        ed_ly.addWidget(self.inp_title)

        ed_ly.addLayout(self._build_toolbar())

        self.inp_text = QTextEdit()
        self.inp_text.setPlaceholderText(t("messages.text_placeholder"))
        self.inp_text.setMinimumHeight(160)
        self._apply_inp_text_style()
        self.inp_text.textChanged.connect(self._update_char_count)
        ed_ly.addWidget(self.inp_text)

        self._editor_sep = QFrame()
        self._editor_sep.setFrameShape(QFrame.Shape.HLine)
        self._apply_sep_style()
        ed_ly.addWidget(self._editor_sep)

        self.media_gallery = _MediaGallery()
        ed_ly.addWidget(self.media_gallery)

        ed_ly.addLayout(self._build_actions())
        self._root_ly.addWidget(self._editor)
        self._editor.hide()

    # ── Style applicators ─────────────────────────────────────────────────────

    def _apply_hint_style(self) -> None:
        c = TG_BASE_COLORS
        self.lbl_hint.setStyleSheet(f"""
            background-color: {c['bg_sidebar']};
            color: {c['text_muted']};
            border: 2px dashed {c['border']};
            border-radius: 12px;
            padding: 40px 30px;
            font-size: 15px;
        """)

    def _apply_inp_title_style(self) -> None:
        c = TG_BASE_COLORS
        self.inp_title.setStyleSheet(f"""
            QLineEdit {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 11px 14px;
                font-size: 15px;
                font-weight: 600;
                background-color: {c['bg_sidebar']};
                color: {c['text_main']};
            }}
            QLineEdit:focus {{
                border: 2px solid {c['accent']};
                background-color: {c['bg_main']};
            }}
        """)

    def _apply_inp_text_style(self) -> None:
        c = TG_BASE_COLORS
        self.inp_text.setStyleSheet(f"""
            QTextEdit {{
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 14px;
                background-color: {c['bg_sidebar']};
                color: {c['text_main']};
            }}
            QTextEdit:focus {{
                border: 2px solid {c['accent']};
                background-color: {c['bg_main']};
            }}
        """)

    def _apply_sep_style(self) -> None:
        self._editor_sep.setStyleSheet(
            f"color: {TG_BASE_COLORS['border']}; margin: 2px 0;"
        )

    def _apply_toolbar_styles(self) -> None:
        c = TG_BASE_COLORS
        base = f"""
            QPushButton {{
                background-color: {c['bg_sidebar']};
                border: 1.5px solid {c['border']};
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 14px;
                font-weight: bold;
                min-width: 34px;
                color: {c['text_main']};
            }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; }}
            QPushButton:pressed {{
                background-color: {c['accent_light']};
                border-color: {c['accent']};
                color: {c['accent']};
            }}
        """
        self.btn_bold.setStyleSheet(base)
        self.btn_italic.setStyleSheet(base + "QPushButton { font-style: italic; }")
        self.btn_under.setStyleSheet(base + "QPushButton { text-decoration: underline; }")
        self.btn_strike.setStyleSheet(base + "QPushButton { text-decoration: line-through; }")
        self.btn_code.setStyleSheet(base + "QPushButton { font-family: monospace; letter-spacing: 1px; }")

    def _apply_action_styles(self) -> None:
        c = TG_BASE_COLORS
        self.btn_delete.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['danger_light']};
                color: {c['danger']};
                border: 1.5px solid {c['danger']};
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; border-color: {c['danger_hover']}; }}
        """)
        self.btn_rules.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent_light']};
                color: {c['accent']};
                border: 1.5px solid {c['accent']};
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; }}
        """)
        self.btn_send_now.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['green']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 9px 16px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['green_hover']}; }}
        """)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background-color: {c['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 9px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {c['accent_hover']}; }}
            QPushButton:disabled {{ background-color: #a2c9f4; }}
        """)

    def refresh_theme(self, _theme: str = "") -> None:
        self._apply_hint_style()
        self._apply_inp_title_style()
        self._apply_inp_text_style()
        self._apply_sep_style()
        self._apply_toolbar_styles()
        self._apply_action_styles()
        self.media_gallery.refresh_theme()

    # ── Toolbar builder ───────────────────────────────────────────────────────

    def _build_toolbar(self) -> QHBoxLayout:
        ly = QHBoxLayout()
        ly.setSpacing(4)

        self.btn_bold   = QPushButton("B")
        self.btn_italic = QPushButton("I")
        self.btn_under  = QPushButton("U")
        self.btn_strike = QPushButton("S")
        self.btn_code   = QPushButton("{ }")

        for btn in (self.btn_bold, self.btn_italic, self.btn_under, self.btn_strike, self.btn_code):
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            ly.addWidget(btn)

        self._apply_toolbar_styles()

        self.btn_bold.clicked.connect(self._toggle_bold)
        self.btn_italic.clicked.connect(self._toggle_italic)
        self.btn_under.clicked.connect(self._toggle_underline)
        self.btn_strike.clicked.connect(self._toggle_strike)
        self.btn_code.clicked.connect(self._toggle_code)

        ly.addStretch()
        self.lbl_char_count = QLabel("0 / 4096")
        self.lbl_char_count.setStyleSheet(
            f"font-size: 11px; color: {TG_BASE_COLORS['text_muted']}; min-width: 64px;"
        )
        ly.addWidget(self.lbl_char_count)
        return ly

    # ── Actions builder ───────────────────────────────────────────────────────

    def _build_actions(self) -> QHBoxLayout:
        ly = QHBoxLayout()
        ly.setSpacing(8)

        self.btn_delete = QPushButton(t("messages.btn_delete_short"))
        self.btn_delete.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_delete.hide()

        self.btn_rules = QPushButton(t("messages.btn_rules"))
        self.btn_rules.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_rules.clicked.connect(self._on_rules_clicked)
        self.btn_rules.hide()

        self.btn_send_now = QPushButton(t("messages.btn_send_now_short"))
        self.btn_send_now.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_send_now.clicked.connect(self._on_send_now_clicked)
        self.btn_send_now.hide()

        self.btn_save = QPushButton(t("messages.btn_save_short"))
        self.btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_save.clicked.connect(self._on_save_clicked)

        self._apply_action_styles()

        ly.addWidget(self.btn_delete)
        ly.addStretch()
        ly.addWidget(self.btn_rules)
        ly.addWidget(self.btn_send_now)
        ly.addWidget(self.btn_save)
        return ly

    # ── Public API ────────────────────────────────────────────────────────────

    def load_message(self, msg_id: int, title: str, text: str, media_path: str | None) -> None:
        """Load a saved message template into the editor."""
        self.current_msg_id = msg_id
        self.lbl_hint.hide()
        self._editor.show()
        self.inp_title.setText(title)
        if text:
            self.inp_text.setHtml(telegram_html_to_display_html(text) if text else "")
        else:
            self.inp_text.clear()
        self.media_gallery.set_paths(_parse_media_paths(media_path))
        self.btn_delete.show()
        self.btn_rules.show()
        self.btn_send_now.show()

    def activate_new(self) -> None:
        self.current_msg_id = None
        self.lbl_hint.hide()
        self._editor.show()
        self.inp_title.clear()
        self.inp_text.clear()
        self.media_gallery.set_paths([])
        self.btn_delete.hide()
        self.btn_rules.hide()
        self.btn_send_now.hide()
        self.inp_title.setFocus()

    def clear(self) -> None:
        self.current_msg_id = None
        self.inp_title.clear()
        self.inp_text.clear()
        self.media_gallery.set_paths([])
        self._editor.hide()
        self.lbl_hint.show()

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _update_char_count(self) -> None:
        n = len(self.inp_text.toPlainText())
        limit = 4096
        self.lbl_char_count.setText(f"{n} / {limit}")
        if n > limit:
            self.lbl_char_count.setStyleSheet(
                f"font-size: 11px; color: {TG_BASE_COLORS['danger']}; min-width: 64px; font-weight: 600;"
            )
        elif n > limit * 0.9:
            self.lbl_char_count.setStyleSheet(
                f"font-size: 11px; color: {TG_BASE_COLORS.get('warn', '#f0a500')}; min-width: 64px;"
            )
        else:
            self.lbl_char_count.setStyleSheet(
                f"font-size: 11px; color: {TG_BASE_COLORS['text_muted']}; min-width: 64px;"
            )

    def _on_save_clicked(self) -> None:
        title = self.inp_title.text().strip()
        if not title:
            QMessageBox.warning(self, t("app.warning"), t("messages.error_empty_title"))
            return

        text = self.inp_text.toHtml()

        self.save_requested.emit(
            self.current_msg_id, title, text,
            _encode_media_paths(self.media_gallery.get_paths())
        )

    def _on_rules_clicked(self) -> None:
        if self.current_msg_id:
            self.rules_requested.emit(self.current_msg_id)

    def _on_send_now_clicked(self) -> None:
        if self.current_msg_id:
            self.send_now_requested.emit(self.current_msg_id)

    def _on_delete_clicked(self) -> None:
        if self.current_msg_id:
            reply = QMessageBox.question(
                self,
                t("messages.delete_confirm_title"),
                t("messages.delete_confirm_text"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(self.current_msg_id)

    # ── Formatting ────────────────────────────────────────────────────────────

    def _toggle_bold(self) -> None:
        w = QFont.Weight.Bold if self.inp_text.fontWeight() != QFont.Weight.Bold.value else QFont.Weight.Normal
        self.inp_text.setFontWeight(w)
        self.inp_text.setFocus()

    def _toggle_italic(self) -> None:
        self.inp_text.setFontItalic(not self.inp_text.fontItalic())
        self.inp_text.setFocus()

    def _toggle_underline(self) -> None:
        self.inp_text.setFontUnderline(not self.inp_text.fontUnderline())
        self.inp_text.setFocus()

    def _toggle_strike(self) -> None:
        fmt = self.inp_text.currentCharFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        self.inp_text.mergeCurrentCharFormat(fmt)
        self.inp_text.setFocus()

    def _toggle_code(self) -> None:
        fmt = self.inp_text.currentCharFormat()
        currently_code = is_code_format(fmt)
        set_code_format(fmt, not currently_code)
        if not currently_code:
            fmt.setBackground(Qt.GlobalColor.lightGray)
        else:
            fmt.clearBackground()
        self.inp_text.mergeCurrentCharFormat(fmt)
        self.inp_text.setFocus()