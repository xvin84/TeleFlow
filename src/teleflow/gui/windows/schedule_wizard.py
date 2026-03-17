"""
ScheduleWizard — полный мастер настройки расписания.

Поддерживает 5 режимов:
  • Один раз          — конкретная дата и время
  • Ежедневно         — каждый день в HH:MM
  • По дням недели    — выбранные дни в HH:MM
  • Интервал          — каждые N минут/часов
  • Случайное окно    — случайное время между HH:MM и HH:MM (ежедневно)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QDateTime, QTime
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDateTimeEdit,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from teleflow.core.scheduler import ScheduleConfig
from teleflow.gui.styles import TG_BASE_COLORS, theme_manager
from teleflow.i18n import t


# ── small style helpers ───────────────────────────────────────────────────────

def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color: {TG_BASE_COLORS['border']}; margin: 4px 0;")
    return f


def _time_edit(hhmm: str = "10:00") -> QTimeEdit:
    c = TG_BASE_COLORS
    h, m = map(int, hhmm.split(":"))
    w = QTimeEdit(QTime(h, m))
    w.setDisplayFormat("HH:mm")
    w.setFixedHeight(36)
    w.setStyleSheet(f"""
        QTimeEdit {{
            border: 1.5px solid {c['border']};
            border-radius: 6px;
            padding: 0 8px;
            background: {c['bg_sidebar']};
            color: {c['text_main']};
            font-size: 14px;
        }}
        QTimeEdit:focus {{ border-color: {c['accent']}; }}
        QTimeEdit::up-button, QTimeEdit::down-button {{
            width: 18px;
        }}
    """)
    return w


def _spin(min_v: int, max_v: int, val: int, suffix: str = "") -> QSpinBox:
    c = TG_BASE_COLORS
    s = QSpinBox()
    s.setRange(min_v, max_v)
    s.setValue(val)
    if suffix:
        s.setSuffix(f" {suffix}")
    s.setFixedHeight(36)
    s.setStyleSheet(f"""
        QSpinBox {{
            border: 1.5px solid {c['border']};
            border-radius: 6px;
            padding: 0 8px;
            background: {c['bg_sidebar']};
            color: {c['text_main']};
            font-size: 14px;
        }}
        QSpinBox:focus {{ border-color: {c['accent']}; }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 18px;
        }}
    """)
    return s


def _day_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setFixedSize(36, 36)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{
            border: 1.5px solid {c['border']};
            border-radius: 18px;
            background: {c['bg_sidebar']};
            color: {c['text_main']};
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:checked {{
            background: {c['accent']};
            border-color: {c['accent']};
            color: white;
        }}
        QPushButton:hover:!checked {{ background: {c['bg_hover']}; }}
    """)
    return btn


def _primary_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setFixedHeight(40)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {c['accent']};
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            padding: 0 20px;
        }}
        QPushButton:hover {{ background: {c['accent_hover']}; }}
        QPushButton:disabled {{ background: {c['border']}; color: {c['text_muted']}; }}
    """)
    return btn


def _cancel_btn(label: str) -> QPushButton:
    c = TG_BASE_COLORS
    btn = QPushButton(label)
    btn.setFixedHeight(40)
    btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent;
            color: {c['text_muted']};
            border: 1.5px solid {c['border']};
            border-radius: 8px;
            font-size: 13px;
            padding: 0 20px;
        }}
        QPushButton:hover {{ background: {c['bg_hover']}; }}
    """)
    return btn


def _mode_radio(label: str, desc: str) -> QRadioButton:
    c = TG_BASE_COLORS
    rb = QRadioButton(f"  {label}")
    rb.setStyleSheet(f"""
        QRadioButton {{
            font-size: 14px;
            font-weight: 600;
            color: {c['text_main']};
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 18px; height: 18px;
            border-radius: 9px;
            border: 2px solid {c['border']};
            background: {c['bg_sidebar']};
        }}
        QRadioButton::indicator:checked {{
            background: {c['accent']};
            border-color: {c['accent']};
        }}
    """)
    rb.setToolTip(desc)
    return rb


# ── ScheduleWizard ────────────────────────────────────────────────────────────

_WEEKDAYS = [
    ("mon", "Пн"), ("tue", "Вт"), ("wed", "Ср"), ("thu", "Чт"),
    ("fri", "Пт"), ("sat", "Сб"), ("sun", "Вс"),
]

_MODES = [
    ("one_time",      "Один раз",          "Отправить один раз в указанную дату и время"),
    ("daily_fixed",   "Ежедневно",          "Каждый день в указанное время"),
    ("weekday",       "По дням недели",     "В выбранные дни недели в указанное время"),
    ("interval",      "С интервалом",       "Повторять каждые N минут/часов"),
    ("random_window", "Случайное время",    "Каждый день в случайное время внутри окна"),
]


class ScheduleWizard(QDialog):
    """Full schedule configuration wizard.

    After ``exec() == Accepted``, read ``result_config: ScheduleConfig``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        prefill: Optional[ScheduleConfig] = None,
    ) -> None:
        super().__init__(parent)
        self.result_config: Optional[ScheduleConfig] = None
        self._prefill = prefill
        # For backward-compat with dashboard (uses selected_datetime)
        self.selected_datetime: Optional[datetime] = None

        self.setWindowTitle(t("schedule.title"))
        self.resize(480, 560)
        self.setModal(True)
        self.setStyleSheet(theme_manager.login_qss())

        self._build_ui()
        if prefill is not None:
            self._apply_prefill(prefill)

    def _apply_prefill(self, cfg: ScheduleConfig) -> None:
        """Pre-fill the wizard fields from an existing ScheduleConfig.

        Uses the CORRECT attribute names that match what _build_* methods create.
        """
        mode_map = {
            "one_time": 0, "daily_fixed": 1, "weekday": 2,
            "interval": 3, "random_window": 4,
        }
        idx = mode_map.get(cfg.mode, 0)

        # Select the correct radio button
        btns = self._radio_group.buttons()
        if idx < len(btns):
            btns[idx].setChecked(True)
            self._stack.setCurrentIndex(idx)

        # Fill fields per mode
        if cfg.mode == "one_time" and cfg.run_datetime:
            dt = QDateTime.fromSecsSinceEpoch(int(cfg.run_datetime.timestamp()))
            self.dt_one_time.setDateTime(dt)

        elif cfg.mode == "daily_fixed":
            h, m = map(int, cfg.time_hhmm.split(":"))
            self.time_daily.setTime(QTime(h, m))

        elif cfg.mode == "weekday":
            h, m = map(int, cfg.time_hhmm.split(":"))
            self.time_weekday.setTime(QTime(h, m))
            # Uncheck all days first, then check the saved ones
            for btn in self._day_btns.values():
                btn.setChecked(False)
            for day in cfg.weekdays:
                if day in self._day_btns:
                    self._day_btns[day].setChecked(True)

        elif cfg.mode == "interval":
            h, m = divmod(cfg.interval_minutes, 60)
            self.spin_hours.setValue(h)
            self.spin_minutes.setValue(m)

        elif cfg.mode == "random_window":
            wsh, wsm = map(int, cfg.window_start.split(":"))
            weh, wem = map(int, cfg.window_end.split(":"))
            self.time_win_start.setTime(QTime(wsh, wsm))
            self.time_win_end.setTime(QTime(weh, wem))

    # ── Build ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c = TG_BASE_COLORS
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # ── Header
        title = QLabel(t("schedule.title"))
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {c['text_main']};")
        root.addWidget(title)
        root.addWidget(_sep())

        # ── Mode selector
        mode_group = QGroupBox(t("schedule.mode_label"))
        mode_group.setStyleSheet(f"""
            QGroupBox {{
                font-size: 12px; font-weight: 700; color: {c['text_muted']};
                border: 1.5px solid {c['border']}; border-radius: 8px;
                margin-top: 8px; padding: 12px 12px 8px 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 12px; padding: 0 4px;
            }}
        """)
        mode_ly = QVBoxLayout(mode_group)
        mode_ly.setSpacing(6)

        self._radio_group = QButtonGroup(self)
        self._radios: list[QRadioButton] = []

        for idx, (mode_id, label, desc) in enumerate(_MODES):
            rb = _mode_radio(label, desc)
            self._radio_group.addButton(rb, idx)
            mode_ly.addWidget(rb)
            self._radios.append(rb)

        self._radios[0].setChecked(True)
        root.addWidget(mode_group)

        # ── Stacked settings panels
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_one_time_panel())
        self._stack.addWidget(self._build_daily_fixed_panel())
        self._stack.addWidget(self._build_weekday_panel())
        self._stack.addWidget(self._build_interval_panel())
        self._stack.addWidget(self._build_random_window_panel())
        root.addWidget(self._stack)

        self._radio_group.idToggled.connect(self._on_mode_changed)

        # ── Error label
        self.lbl_error = QLabel("")
        self.lbl_error.setStyleSheet(f"color: {c['danger']}; font-size: 12px;")
        self.lbl_error.hide()
        root.addWidget(self.lbl_error)

        root.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # ── Footer buttons
        foot = QHBoxLayout()
        foot.setSpacing(10)
        btn_cancel = _cancel_btn(t("schedule.btn_cancel"))
        btn_cancel.clicked.connect(self.reject)
        self.btn_confirm = _primary_btn(t("schedule.btn_confirm"))
        self.btn_confirm.clicked.connect(self._on_confirm)
        foot.addStretch()
        foot.addWidget(btn_cancel)
        foot.addWidget(self.btn_confirm)
        root.addLayout(foot)

    # ── Panel builders ────────────────────────────────────────────────────────

    def _panel_wrapper(self) -> tuple[QWidget, QVBoxLayout]:
        c = TG_BASE_COLORS
        w = QWidget()
        w.setStyleSheet(f"""
            QWidget {{
                background: {c['bg_sidebar']};
                border: 1.5px solid {c['border']};
                border-radius: 8px;
            }}
        """)
        ly = QVBoxLayout(w)
        ly.setContentsMargins(16, 12, 16, 12)
        ly.setSpacing(8)
        return w, ly

    def _field_row(self, layout: QVBoxLayout, label: str, widget: QWidget) -> None:
        c = TG_BASE_COLORS
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"font-size: 12px; color: {c['text_muted']}; font-weight: 600;"
            " background: transparent; border: none;"
        )
        layout.addWidget(lbl)
        layout.addWidget(widget)

    def _build_one_time_panel(self) -> QWidget:
        w, ly = self._panel_wrapper()
        c = TG_BASE_COLORS
        lbl = QLabel(t("schedule.one_time_desc"))
        lbl.setStyleSheet(
            f"font-size: 13px; color: {c['text_main']}; background: transparent; border: none;"
        )
        lbl.setWordWrap(True)
        ly.addWidget(lbl)

        self.dt_one_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.dt_one_time.setCalendarPopup(True)
        self.dt_one_time.setDisplayFormat("dd.MM.yyyy  HH:mm")
        self.dt_one_time.setFixedHeight(40)
        self.dt_one_time.setStyleSheet(f"""
            QDateTimeEdit {{
                border: 1.5px solid {c['border']};
                border-radius: 6px;
                padding: 0 10px;
                background: {c['bg_main']};
                color: {c['text_main']};
                font-size: 16px;
                font-weight: 600;
            }}
            QDateTimeEdit:focus {{ border-color: {c['accent']}; }}
        """)
        ly.addWidget(self.dt_one_time)
        return w

    def _build_daily_fixed_panel(self) -> QWidget:
        w, ly = self._panel_wrapper()
        c = TG_BASE_COLORS
        lbl = QLabel(t("schedule.daily_fixed_desc"))
        lbl.setStyleSheet(
            f"font-size: 13px; color: {c['text_main']}; background: transparent; border: none;"
        )
        ly.addWidget(lbl)
        self.time_daily = _time_edit("10:00")
        self._field_row(ly, t("schedule.time_label"), self.time_daily)
        return w

    def _build_weekday_panel(self) -> QWidget:
        w, ly = self._panel_wrapper()
        c = TG_BASE_COLORS
        lbl = QLabel(t("schedule.weekday_desc"))
        lbl.setStyleSheet(
            f"font-size: 13px; color: {c['text_main']}; background: transparent; border: none;"
        )
        ly.addWidget(lbl)

        # Day buttons row
        day_row = QHBoxLayout()
        day_row.setSpacing(6)
        self._day_btns: dict[str, QPushButton] = {}
        for day_id, day_label in _WEEKDAYS:
            btn = _day_btn(day_label)
            self._day_btns[day_id] = btn
            day_row.addWidget(btn)
        day_row.addStretch()
        day_widget = QWidget()
        day_widget.setStyleSheet("background: transparent; border: none;")
        day_widget.setLayout(day_row)
        ly.addWidget(day_widget)

        self.time_weekday = _time_edit("10:00")
        self._field_row(ly, t("schedule.time_label"), self.time_weekday)
        return w

    def _build_interval_panel(self) -> QWidget:
        w, ly = self._panel_wrapper()
        c = TG_BASE_COLORS
        lbl = QLabel(t("schedule.interval_desc"))
        lbl.setStyleSheet(
            f"font-size: 13px; color: {c['text_main']}; background: transparent; border: none;"
        )
        ly.addWidget(lbl)

        row = QHBoxLayout()
        self.spin_hours   = _spin(0, 23,  0, t("schedule.hours"))
        self.spin_minutes = _spin(0, 59, 30, t("schedule.minutes"))

        row.addWidget(self.spin_hours)
        lbl_sep = QLabel(":")
        lbl_sep.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {c['text_main']};"
            " background: transparent; border: none;"
        )
        row.addWidget(lbl_sep)
        row.addWidget(self.spin_minutes)
        row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        container.setLayout(row)
        self._field_row(ly, t("schedule.interval_label"), container)
        return w

    def _build_random_window_panel(self) -> QWidget:
        w, ly = self._panel_wrapper()
        c = TG_BASE_COLORS
        lbl = QLabel(t("schedule.random_window_desc"))
        lbl.setStyleSheet(
            f"font-size: 13px; color: {c['text_main']}; background: transparent; border: none;"
        )
        lbl.setWordWrap(True)
        ly.addWidget(lbl)

        row = QHBoxLayout()
        self.time_win_start = _time_edit("10:00")
        self.time_win_end   = _time_edit("11:00")

        lbl_from = QLabel(t("schedule.from"))
        lbl_from.setStyleSheet(
            f"font-size: 13px; color: {c['text_muted']}; background: transparent; border: none;"
        )
        lbl_to = QLabel(t("schedule.to"))
        lbl_to.setStyleSheet(
            f"font-size: 13px; color: {c['text_muted']}; background: transparent; border: none;"
        )

        row.addWidget(lbl_from)
        row.addWidget(self.time_win_start)
        row.addSpacing(10)
        row.addWidget(lbl_to)
        row.addWidget(self.time_win_end)
        row.addStretch()

        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        container.setLayout(row)
        self._field_row(ly, t("schedule.window_label"), container)
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_mode_changed(self, btn_id: int, checked: bool) -> None:
        if checked:
            self._stack.setCurrentIndex(btn_id)
            self.lbl_error.hide()

    def _on_confirm(self) -> None:
        mode_idx = self._radio_group.checkedId()
        mode_id  = _MODES[mode_idx][0]

        try:
            config = self._build_config(mode_id)
        except ValueError as e:
            self.lbl_error.setText(str(e))
            self.lbl_error.show()
            return

        self.result_config = config
        # Backward-compat
        if mode_id == "one_time":
            self.selected_datetime = config.run_datetime
        else:
            self.selected_datetime = None

        self.accept()

    def _build_config(self, mode_id: str) -> ScheduleConfig:
        if mode_id == "one_time":
            dt = self.dt_one_time.dateTime().toPyDateTime()
            if dt <= datetime.now():
                raise ValueError(t("schedule.error_past_date"))
            return ScheduleConfig(mode="one_time", run_datetime=dt)

        if mode_id == "daily_fixed":
            t_val = self.time_daily.time()
            return ScheduleConfig(
                mode="daily_fixed",
                time_hhmm=f"{t_val.hour():02d}:{t_val.minute():02d}",
            )

        if mode_id == "weekday":
            days = [d for d, btn in self._day_btns.items() if btn.isChecked()]
            if not days:
                raise ValueError(t("schedule.error_no_days"))
            t_val = self.time_weekday.time()
            return ScheduleConfig(
                mode="weekday",
                weekdays=days,
                time_hhmm=f"{t_val.hour():02d}:{t_val.minute():02d}",
            )

        if mode_id == "interval":
            total_minutes = self.spin_hours.value() * 60 + self.spin_minutes.value()
            if total_minutes < 1:
                raise ValueError(t("schedule.error_zero_interval"))
            return ScheduleConfig(mode="interval", interval_minutes=total_minutes)

        if mode_id == "random_window":
            ts = self.time_win_start.time()
            te = self.time_win_end.time()
            start = f"{ts.hour():02d}:{ts.minute():02d}"
            end   = f"{te.hour():02d}:{te.minute():02d}"
            if ts >= te:
                raise ValueError(t("schedule.error_window_order"))
            return ScheduleConfig(mode="random_window", window_start=start, window_end=end)

        raise ValueError(f"Unknown mode: {mode_id}")