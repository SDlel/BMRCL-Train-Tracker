"""Top control bar: branding, clock, transport controls and day-type selector."""

from __future__ import annotations

from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ... import config
from ...core.simulation import Frame
from .. import theme
from ..metrics import (
    BUTTON_PADDING,
    COMBO_PADDING,
    FIELD_PADDING,
    SPACING_SECTION,
    SPACING_TIGHT,
    fit_width,
)


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setStyleSheet(f"color: {theme.HEX['border']};")
    line.setFixedWidth(1)
    return line


class HeaderBar(QFrame):
    """Primary operator controls plus the always-visible system clock."""

    play_toggled = Signal(bool)
    speed_changed = Signal(float)
    seek_requested = Signal(int)
    resync_requested = Signal()
    day_type_changed = Signal(object)
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    fit_requested = Signal()

    BRAND_MIN_WIDTH = 1340

    BRAND_SUB_MIN_WIDTH = 1420

    CONTROLS_MIN_WIDTH = 1060

    def __init__(self, day_types: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(64)
        self._speed_buttons: dict[float, QPushButton] = {}
        self._last_clock = ""
        self._last_date = ""
        self._last_clock_colour = ""
        self._build(day_types)

    def _build(self, day_types: list[tuple[str, str]]) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 8, 16, 8)
        root.setSpacing(SPACING_SECTION)

        root.addLayout(self._brand_block())
        root.addWidget(_separator())
        root.addLayout(self._clock_block())
        root.addWidget(_separator())
        root.addLayout(self._transport_block())
        root.addWidget(_separator())
        root.addLayout(self._time_block())
        root.addWidget(_separator())
        root.addLayout(self._day_block(day_types))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        root.addWidget(spacer)

        root.addLayout(self._view_block())
        self._collapsible = [self.brand_title, self.brand_sub]

    def _brand_block(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(0)
        self.brand_title = QLabel("BMRCL TRAIN TRACKER")
        self.brand_title.setObjectName("Brand")
        self.brand_title.setFont(theme.ui_font(13, bold=True))
        self.brand_sub = QLabel("BENGALURU METRO")
        self.brand_sub.setObjectName("BrandSub")
        self.brand_sub.setFont(theme.mono_font(7))
        box.addWidget(self.brand_title)
        box.addWidget(self.brand_sub)
        return box

    def _clock_block(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(0)
        self.clock_label = QLabel("--:--:--")
        self.clock_label.setObjectName("Clock")
        self.clock_label.setFont(theme.mono_font(21, bold=True))
        self.date_label = QLabel("")
        self.date_label.setObjectName("ClockDate")
        self.date_label.setFont(theme.mono_font(7))
        box.addWidget(self.clock_label)
        box.addWidget(self.date_label)
        return box

    def _transport_block(self) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(SPACING_TIGHT)

        self.play_button = QPushButton("PAUSE")
        self.play_button.setCheckable(True)
        self.play_button.setChecked(True)
        self.play_button.setFont(theme.mono_font(8, bold=True))
        self.play_button.clicked.connect(self._on_play_clicked)
        # Sized to the longest state ("RESUME") so toggling never shoves
        # the neighbouring controls sideways.
        fit_width(self.play_button, "PAUSE", "RESUME", padding=BUTTON_PADDING)
        box.addWidget(self.play_button)

        labels = [f"{speed:g}x" for speed in config.SPEED_CHOICES]
        for speed, label in zip(config.SPEED_CHOICES, labels, strict=True):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setFont(theme.mono_font(8))
            button.setChecked(abs(speed - config.DEFAULT_SPEED) < 1e-9)
            button.clicked.connect(lambda _=False, s=speed: self._on_speed_clicked(s))
            fit_width(button, *labels, padding=BUTTON_PADDING)
            self._speed_buttons[speed] = button
            box.addWidget(button)
        return box

    def _time_block(self) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(SPACING_TIGHT)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setFont(theme.mono_font(9))
        # Include the spin arrows the widget draws on the right.
        fit_width(self.time_edit, "00:00", padding=FIELD_PADDING + 18)
        box.addWidget(self.time_edit)

        self.jump_button = QPushButton("JUMP")
        self.jump_button.setFont(theme.mono_font(8))
        self.jump_button.clicked.connect(self._on_seek)
        fit_width(self.jump_button, "JUMP", padding=BUTTON_PADDING)
        box.addWidget(self.jump_button)

        self.live_button = QPushButton("LIVE")
        self.live_button.setFont(theme.mono_font(8, bold=True))
        self.live_button.clicked.connect(self.resync_requested.emit)
        fit_width(self.live_button, "LIVE", padding=BUTTON_PADDING)
        box.addWidget(self.live_button)
        return box

    def _day_block(self, day_types: list[tuple[str, str]]) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(SPACING_TIGHT + 2)
        caption = QLabel("DAY")
        caption.setFont(theme.mono_font(7))
        caption.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        box.addWidget(caption)

        self.day_combo = QComboBox()
        self.day_combo.setFont(theme.ui_font(9))
        self.day_combo.addItem("Auto (calendar)", None)
        for key, label in day_types:
            self.day_combo.addItem(label, key)
        self.day_combo.currentIndexChanged.connect(
            lambda _: self.day_type_changed.emit(self.day_combo.currentData())
        )
        entries = ["Auto (calendar)"] + [label for _, label in day_types]
        fit_width(self.day_combo, *entries, padding=COMBO_PADDING)
        box.addWidget(self.day_combo)
        return box

    def _view_block(self) -> QHBoxLayout:
        box = QHBoxLayout()
        box.setSpacing(SPACING_TIGHT)
        for label, signal, tip in (
            ("\u2212", self.zoom_out_requested, "Zoom out"),
            ("+", self.zoom_in_requested, "Zoom in"),
            ("FIT", self.fit_requested, "Fit the whole line on screen"),
        ):
            button = QPushButton(label)
            button.setFont(theme.mono_font(9, bold=True))
            button.setToolTip(tip)
            button.clicked.connect(signal.emit)
            fit_width(
                button, label, "+" if label != "FIT" else "FIT", padding=BUTTON_PADDING, minimum=34
            )
            box.addWidget(button)
        return box

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout()

    def _apply_responsive_layout(self) -> None:
        """Shed decoration before controls when space runs out.

        Branding carries no function, so it is dropped first: the subtitle,
        then the title. Operational controls are never clipped.
        """
        available = self.width()
        self._set_visible(self.brand_sub, available >= self.BRAND_SUB_MIN_WIDTH)
        self._set_visible(self.brand_title, available >= self.BRAND_MIN_WIDTH)

    @staticmethod
    def _set_visible(widget: QWidget, visible: bool) -> None:
        if widget.isVisible() != visible:
            widget.setVisible(visible)

    def minimumSizeHint(self):
        # Report only what the controls genuinely need, so the window can be
        # narrowed to the point where branding is hidden without Qt forcing a
        # wider minimum.
        hint = super().minimumSizeHint()
        hint.setWidth(min(hint.width(), self.CONTROLS_MIN_WIDTH))
        return hint

    def _on_play_clicked(self) -> None:
        running = self.play_button.isChecked()
        self.play_button.setText("PAUSE" if running else "RESUME")
        self.play_toggled.emit(running)

    def _on_speed_clicked(self, speed: float) -> None:
        for value, button in self._speed_buttons.items():
            button.setChecked(abs(value - speed) < 1e-9)
        self.speed_changed.emit(speed)

    def _on_seek(self) -> None:
        t: QTime = self.time_edit.time()
        self.seek_requested.emit(t.hour() * 3600 + t.minute() * 60)

    def set_running(self, running: bool) -> None:
        self.play_button.setChecked(running)
        self.play_button.setText("PAUSE" if running else "RESUME")

    def set_speed(self, speed: float) -> None:
        for value, button in self._speed_buttons.items():
            button.setChecked(abs(value - speed) < 1e-9)

    def update_frame(self, frame: Frame) -> None:
        """Refresh the clock readout, skipping unchanged text.

        ``setText`` on an unchanged string still schedules a repaint, so the
        previous values are cached and compared first.
        """
        hhmmss = frame.clock.hhmmss
        if hhmmss != self._last_clock:
            self._last_clock = hhmmss
            self.clock_label.setText(hhmmss)

        suffix = "LIVE" if frame.clock.live else "SIM"
        date_text = f"{frame.clock.day:%a %d %b %Y}  |  {suffix}"
        if date_text != self._last_date:
            self._last_date = date_text
            self.date_label.setText(date_text)

        colour = theme.HEX["accent"] if frame.clock.live else theme.HEX["warn"]
        if colour != self._last_clock_colour:
            self._last_clock_colour = colour
            self.clock_label.setStyleSheet(f"color: {colour}; letter-spacing: 2px;")
