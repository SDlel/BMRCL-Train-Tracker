"""Dockable per-line summary cards showing headline operational figures."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from ...core.network import Line, Network
from ...core.simulation import Frame, LineStats
from .. import theme


class LineCard(QFrame):
    """One card per line: colour chip, terminals and live counters."""

    def __init__(self, line: Line, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.line = line
        self._cache: dict[str, str] = {}
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"background: {theme.HEX['bg_panel']};"
            f"border-left: 3px solid {line.colour};"
            "border-radius: 3px;"
        )
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 9)
        root.setSpacing(3)

        title = QLabel(self.line.name.upper())
        title.setFont(theme.ui_font(10, bold=True))
        title.setStyleSheet(f"color: {self.line.colour}; border: none;")
        root.addWidget(title)

        route = QLabel(f"{self.line.first.name}  \u2194  {self.line.last.name}")
        route.setFont(theme.ui_font(7))
        route.setWordWrap(True)
        route.setStyleSheet(f"color: {theme.HEX['text_dim']}; border: none;")
        root.addWidget(route)

        grid = QGridLayout()
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(2)
        self.values: dict[str, QLabel] = {}
        fields = (
            ("LIVE", "active"),
            ("UP", "up"),
            ("DN", "down"),
            ("DWELL", "dwelling"),
            ("SHORT", "short_turns"),
        )
        for column, (caption, key) in enumerate(fields):
            cap = QLabel(caption)
            cap.setFont(theme.mono_font(6))
            cap.setStyleSheet(f"color: {theme.HEX['text_dim']}; border: none;")
            cap.setAlignment(Qt.AlignHCenter)
            val = QLabel("0")
            val.setFont(theme.mono_font(12, bold=True))
            val.setStyleSheet(f"color: {theme.HEX['text']}; border: none;")
            val.setAlignment(Qt.AlignHCenter)
            grid.addWidget(cap, 0, column)
            grid.addWidget(val, 1, column)
            self.values[key] = val
        root.addLayout(grid)

        self.span = QLabel("")
        self.span.setFont(theme.mono_font(7))
        self.span.setStyleSheet(f"color: {theme.HEX['text_dim']}; border: none;")
        root.addWidget(self.span)

    def update_stats(self, stats: LineStats | None, span_text: str, scheduled: int) -> None:
        """Refresh the counters, writing only values that actually changed."""
        if stats is not None:
            for key, label in self.values.items():
                text = str(getattr(stats, key, 0))
                if self._cache.get(key) != text:
                    self._cache[key] = text
                    label.setText(text)
            colour = theme.HEX["ok"] if stats.active else theme.HEX["text_dim"]
            if self._cache.get("#colour") != colour:
                self._cache["#colour"] = colour
                self.values["active"].setStyleSheet(f"color: {colour}; border: none;")
        span = f"service {span_text}  |  {scheduled} departures"
        if self._cache.get("#span") != span:
            self._cache["#span"] = span
            self.span.setText(span)


class LinePanel(QWidget):
    """Stack of :class:`LineCard` widgets for every line in the network."""

    def __init__(self, network: Network, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.network = network
        self.cards: dict[str, LineCard] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        for line in network:
            card = LineCard(line)
            self.cards[line.id] = card
            root.addWidget(card)
        root.addStretch(1)

    def update_frame(self, frame: Frame, simulation, line_ids: list[str] | None = None) -> None:
        """Refresh every card, hiding those outside the active tab."""
        wanted = set(line_ids) if line_ids is not None else None
        for line_id, card in self.cards.items():
            visible = wanted is None or line_id in wanted
            if card.isVisible() != visible:
                card.setVisible(visible)
            if not visible:
                continue
            card.update_stats(
                frame.stats.get(line_id),
                simulation.service_span_text(line_id),
                simulation.scheduled_departures(line_id),
            )
