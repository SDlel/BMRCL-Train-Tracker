"""Bottom status strip: FPS, telemetry counters and the symbol legend."""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from ...core.network import Network
from ...core.simulation import Frame
from .. import theme


class FpsCounter:
    """Rolling average frame rate over a short window."""

    def __init__(self, window: int = 60) -> None:
        self._samples: deque[float] = deque(maxlen=window)
        self._last = time.perf_counter()

    def tick(self) -> float:
        now = time.perf_counter()
        delta = now - self._last
        self._last = now
        if delta > 0:
            self._samples.append(delta)
        if not self._samples:
            return 0.0
        return len(self._samples) / sum(self._samples)


class LegendSwatch(QWidget):
    """Small painted key: line colours plus station and train symbols."""

    def __init__(self, network: Network, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.network = network
        self._filter: set[str] | None = None
        self.setFixedHeight(26)
        self.setMinimumWidth(640)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_line_filter(self, line_ids: list[str] | None) -> None:
        """Show colour chips only for the lines currently on screen."""
        new = set(line_ids) if line_ids is not None else None
        if new != self._filter:
            self._filter = new
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setFont(theme.mono_font(7))
        x = 0.0
        cy = self.height() / 2

        for line in self.network:
            if self._filter is not None and line.id not in self._filter:
                continue
            colour = QColor(line.colour)
            painter.setPen(Qt.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(int(x), int(cy - 3), 18, 6, 3, 3)
            x += 24
            painter.setPen(QPen(theme.TEXT_DIM))
            text = line.short_name
            painter.drawText(int(x), int(cy + 3), text)
            x += painter.fontMetrics().horizontalAdvance(text) + 16

        entries = (
            ("station", theme.TEXT_DIM, "circle"),
            ("interchange", theme.TEXT, "ring"),
            ("short-turn", theme.SHORT_TURN, "tick"),
            ("dwelling", theme.WARN, "dot"),
            ("train", theme.ACCENT, "box"),
        )
        for label, colour, kind in entries:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(colour), 1.6))
            if kind == "circle":
                painter.drawEllipse(int(x), int(cy - 4), 8, 8)
            elif kind == "ring":
                painter.drawEllipse(int(x) - 1, int(cy - 5), 10, 10)
                painter.drawEllipse(int(x) + 2, int(cy - 2), 4, 4)
            elif kind == "tick":
                painter.drawLine(int(x), int(cy - 4), int(x) + 8, int(cy - 4))
                painter.drawLine(int(x) + 4, int(cy - 4), int(x) + 4, int(cy + 3))
            elif kind == "dot":
                painter.setBrush(QColor(colour))
                painter.drawEllipse(int(x) + 2, int(cy - 2), 5, 5)
            else:
                painter.setBrush(QColor(colour))
                painter.drawRoundedRect(int(x), int(cy - 4), 14, 8, 2, 2)
            x += 22 if kind != "box" else 20
            painter.setPen(QPen(theme.TEXT_DIM))
            painter.drawText(int(x), int(cy + 3), label)
            x += painter.fontMetrics().horizontalAdvance(label) + 16
        painter.end()


class StatusBar(QFrame):
    """Telemetry footer refreshed on every frame."""

    def __init__(self, network: Network, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(34)
        self.network = network
        self.fps = FpsCounter()
        self._cache: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(14, 4, 14, 4)
        root.setSpacing(16)

        self.legend = LegendSwatch(self.network)
        root.addWidget(self.legend)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        root.addWidget(spacer)

        self.metrics: dict[str, QLabel] = {}
        for key, caption in (
            ("trains", "TRAINS"),
            ("dwell", "DWELL"),
            ("short", "SHORT"),
            ("day", "PLAN"),
            ("speed", "SPEED"),
            ("zoom", "ZOOM"),
            ("fps", "FPS"),
        ):
            label = QLabel(f"{caption} --")
            label.setProperty("class", "Metric")
            label.setFont(theme.mono_font(8))
            label.setStyleSheet(f"color: {theme.HEX['text_dim']};")
            self.metrics[key] = label
            root.addWidget(label)

    def update_frame(
        self, frame: Frame, day_label: str, zoom: float, line_ids: list[str] | None = None
    ) -> None:
        """Refresh the counters.

        Args:
            line_ids: When given, counts cover only these lines so that a line
                tab reports that line's figures rather than the whole network.
        """
        fps = self.fps.tick()
        wanted = set(line_ids) if line_ids is not None else None
        stats = [s for lid, s in frame.stats.items() if wanted is None or lid in wanted]
        dwell = sum(s.dwelling for s in stats)
        short = sum(s.short_turns for s in stats)
        active = sum(s.active for s in stats)

        self.legend.set_line_filter(line_ids)
        self._set("trains", f"TRAINS {active:>3}")
        self._set("dwell", f"DWELL {dwell:>3}")
        self._set("short", f"SHORT {short:>3}")
        self._set("day", f"PLAN {day_label}")
        self._set("speed", f"SPEED {frame.clock.speed:g}x")
        self._set("zoom", f"ZOOM {zoom * 100:.0f}%")
        self._set("fps", f"FPS {fps:5.1f}")

        colour = (
            theme.HEX["ok"]
            if fps >= 50
            else (theme.HEX["warn"] if fps >= 28 else theme.HEX["alert"])
        )
        self._set_colour("fps", colour)
        self._set_colour("speed", theme.HEX["ok"] if frame.clock.running else theme.HEX["warn"])

    def _set(self, key: str, text: str) -> None:
        """Assign label text only when it actually changed."""
        if self._cache.get(key) != text:
            self._cache[key] = text
            self.metrics[key].setText(text)

    def _set_colour(self, key: str, colour: str) -> None:
        cache_key = f"{key}#colour"
        if self._cache.get(cache_key) != colour:
            self._cache[cache_key] = colour
            self.metrics[key].setStyleSheet(f"color: {colour};")
