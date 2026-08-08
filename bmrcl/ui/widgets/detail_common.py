"""Shared building blocks for the station and train detail panels.

Both panels answer the same shape of question, so they share the countdown
formatting and the headline tile widget. Keeping these in one place is what
stops the two docks drifting apart visually.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .. import theme


def countdown(seconds: float | None) -> str:
    """Render a countdown the way a platform indicator would."""
    if seconds is None:
        return "--"
    seconds = max(0.0, seconds)
    if seconds < 30:
        return "due"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60):02d}m"


def elapsed_text(seconds: float) -> str:
    """Render a duration that has already passed, such as time in service."""
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def rule() -> QFrame:
    """A thin horizontal divider matching the dock styling."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {theme.HEX['border']};")
    return line


def caption_label(text: str) -> QLabel:
    """A small uppercase section caption."""
    label = QLabel(text)
    label.setFont(theme.ui_font(7, bold=True))
    label.setStyleSheet(f"color: {theme.HEX['text_dim']}; letter-spacing: 1px;")
    return label


class EventTile(QWidget):
    """A single headline figure: caption, large value, supporting detail."""

    def __init__(self, caption: str, accent: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        self.caption = caption_label(caption)

        self.value = QLabel("--")
        self.value.setFont(theme.mono_font(19, bold=True))
        self.value.setStyleSheet(f"color: {self._accent.name()};")

        self.detail = QLabel("")
        self.detail.setFont(theme.mono_font(8))
        self.detail.setStyleSheet(f"color: {theme.HEX['text_dim']};")

        root.addWidget(self.caption)
        root.addWidget(self.value)
        root.addWidget(self.detail)

    def set_value(self, text: str, detail: str = "", colour: str | None = None) -> None:
        self.value.setText(text)
        self.detail.setText(detail)
        self.value.setStyleSheet(f"color: {colour or self._accent.name()};")

    def set_muted(self, text: str = "--", detail: str = "") -> None:
        self.value.setText(text)
        self.detail.setText(detail)
        self.value.setStyleSheet(f"color: {theme.HEX['text_faint']};")


class ProgressBar(QWidget):
    """Slim journey progress indicator drawn in the line colour."""

    HEIGHT = 6.0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fraction = 0.0
        self._colour = QColor(theme.TEXT)
        self.setFixedHeight(int(self.HEIGHT))

    def set_progress(self, fraction: float, colour: str) -> None:
        fraction = min(1.0, max(0.0, fraction))
        new_colour = QColor(colour)
        if abs(fraction - self._fraction) < 0.001 and new_colour == self._colour:
            return
        self._fraction = fraction
        self._colour = new_colour
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(theme.BORDER)
        painter.setBrush(theme.BG_RAISED)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 3, 3)

        filled = int((self.width() - 2) * self._fraction)
        if filled > 0:
            painter.setPen(self._colour)
            painter.setBrush(self._colour)
            painter.drawRoundedRect(1, 1, filled, self.height() - 3, 2, 2)
        painter.end()
