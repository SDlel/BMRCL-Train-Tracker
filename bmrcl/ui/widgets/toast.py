"""Transient notification overlay.

A brief message that appears over the diagram and fades out on its own. Used to
confirm actions that would otherwise leave the operator guessing whether
anything happened, such as pressing SYNC when the clock was already accurate.

The toast is a child of the window rather than a separate window, so it cannot
steal focus or appear in the taskbar.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from .. import theme


class Toast(QFrame):
    """A small message that fades in, waits, then fades out."""

    FADE_MS = 160
    MARGIN = 22

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"background: {theme.HEX['bg_raised']};"
            f"border: 1px solid {theme.HEX['border']};"
            "border-radius: 6px;"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 11, 18, 11)
        layout.setSpacing(11)

        self.icon = QLabel("\u21bb")
        self.icon.setFont(theme.ui_font(15, bold=True))
        self.icon.setStyleSheet(f"color: {theme.HEX['accent']}; border: none;")

        self.message = QLabel("")
        self.message.setFont(theme.ui_font(10))
        self.message.setStyleSheet(f"color: {theme.HEX['text']}; border: none;")

        layout.addWidget(self.icon)
        layout.addWidget(self.message)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(self.FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.InOutQuad)
        # Connected once and gated by a flag, because disconnecting a signal
        # that has no connection raises in PySide6.
        self._hide_when_faded = False
        self._fade.finished.connect(self._on_fade_finished)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)

        self.hide()

    def show_message(
        self, text: str, *, icon: str = "\u21bb", colour: str | None = None, duration_ms: int = 2400
    ) -> None:
        """Display ``text`` for ``duration_ms``, restarting any current toast."""
        self.message.setText(text)
        self.icon.setText(icon)
        self.icon.setStyleSheet(f"color: {colour or theme.HEX['accent']}; border: none;")
        self.adjustSize()
        self._reposition()

        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

        self._hide_timer.start(duration_ms)

    def _fade_out(self) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._hide_when_faded = True
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._hide_when_faded:
            self._hide_when_faded = False
            self.hide()

    def _reposition(self) -> None:
        """Sit in the lower right of the parent, clear of the docks."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            parent.width() - self.width() - self.MARGIN,
            parent.height() - self.height() - self.MARGIN,
        )
