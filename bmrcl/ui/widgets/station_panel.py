"""Dockable station detail panel.

Selecting a station shows, in plain terms:

* when the next train **arrives**
* when it **departs**
* and at a short-turn station, when a service next **turns back** there

Everything is expressed as a countdown plus the clock time it corresponds to,
which is how a real arrivals board reads.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.arrivals import BoardEntry, StationBoard
from ...core.timetable import format_hhmm
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


class EventTile(QWidget):
    """A single headline figure: caption, big countdown, clock time."""

    def __init__(self, caption: str, accent: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = QColor(accent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(1)

        self.caption = QLabel(caption)
        self.caption.setFont(theme.ui_font(7, bold=True))
        self.caption.setStyleSheet(f"color: {theme.HEX['text_dim']}; letter-spacing: 1px;")

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


class FollowingRow(QFrame):
    """One compact line in the 'later trains' list."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(8)

        self.eta = QLabel("")
        self.eta.setFont(theme.mono_font(9, bold=True))
        self.eta.setFixedWidth(62)

        self.dest = QLabel("")
        self.dest.setFont(theme.ui_font(8))
        self.dest.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.badge = QLabel("")
        self.badge.setFont(theme.mono_font(7, bold=True))
        self.badge.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.badge.setFixedWidth(56)

        root.addWidget(self.eta)
        root.addWidget(self.dest, 1)
        root.addWidget(self.badge)

    def set_entry(self, entry: BoardEntry, now: float) -> None:
        self.eta.setText(countdown(entry.arrival_in))
        self.eta.setStyleSheet(f"color: {theme.HEX['text']};")
        self.dest.setText(entry.destination)
        self.dest.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        if entry.terminates:
            self.badge.setText("TERMINATES")
            self.badge.setStyleSheet(f"color: {theme.HEX['warn']};")
        elif entry.short_turn:
            self.badge.setText("SHORT")
            self.badge.setStyleSheet(f"color: {theme.HEX['warn']};")
        else:
            self.badge.setText(format_hhmm(now + entry.arrival_in))
            self.badge.setStyleSheet(f"color: {theme.HEX['text_faint']};")


class StationPanel(QWidget):
    """Detail view for the currently selected station."""

    FOLLOWING_ROWS = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._station_key: str | None = None
        self._build()
        self.show_placeholder()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.title = QLabel("No station selected")
        self.title.setFont(theme.ui_font(13, bold=True))
        self.title.setWordWrap(True)
        root.addWidget(self.title)

        self.subtitle = QLabel("Click a station on the diagram")
        self.subtitle.setFont(theme.ui_font(8))
        self.subtitle.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)

        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.HLine)
        self.rule.setStyleSheet(f"color: {theme.HEX['border']};")
        root.addWidget(self.rule)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(10)
        self.tile_arrival = EventTile("NEXT ARRIVAL", theme.TEXT)
        self.tile_departure = EventTile("DEPARTS", theme.TEXT)
        self.tile_loop = EventTile("NEXT LOOP", theme.SHORT_TURN)
        grid.addWidget(self.tile_arrival, 0, 0)
        grid.addWidget(self.tile_departure, 0, 1)
        grid.addWidget(self.tile_loop, 1, 0, 1, 2)
        root.addLayout(grid)

        self.loop_note = QLabel("")
        self.loop_note.setFont(theme.ui_font(7))
        self.loop_note.setWordWrap(True)
        self.loop_note.setStyleSheet(f"color: {theme.HEX['text_faint']};")
        root.addWidget(self.loop_note)

        self.following_caption = QLabel("FOLLOWING")
        self.following_caption.setFont(theme.ui_font(7, bold=True))
        self.following_caption.setStyleSheet(
            f"color: {theme.HEX['text_dim']}; letter-spacing: 1px;"
        )
        root.addWidget(self.following_caption)

        self.rows: list[FollowingRow] = []
        for _ in range(self.FOLLOWING_ROWS):
            row = FollowingRow()
            self.rows.append(row)
            root.addWidget(row)

        root.addStretch(1)

    def show_placeholder(self) -> None:
        """Reset to the 'nothing selected' state."""
        self._station_key = None
        self.title.setText("No station selected")
        self.subtitle.setText("Click any station on the diagram to see its next trains.")
        for tile in (self.tile_arrival, self.tile_departure, self.tile_loop):
            tile.set_muted()
        self.tile_loop.setVisible(False)
        self.loop_note.setVisible(False)
        self.following_caption.setVisible(False)
        for row in self.rows:
            row.setVisible(False)

    def update_board(self, board: StationBoard, now: float) -> None:
        """Render a freshly computed :class:`StationBoard`."""
        station, line = board.station, board.line
        if self._station_key != station.key:
            self._station_key = station.key
            self.title.setText(station.name)
            self.title.setStyleSheet(f"color: {line.colour};")
            self.subtitle.setText(self._describe(board))

        entry = board.next_entry
        if entry is None:
            self.tile_arrival.set_muted("--", "no approaching trains")
            self.tile_departure.set_muted()
        else:
            self.tile_arrival.set_value(
                countdown(entry.arrival_in),
                f"{format_hhmm(now + entry.arrival_in)}  to {entry.destination}",
                theme.HEX["warn"] if entry.dwelling_now else theme.HEX["text"],
            )
            if entry.terminates:
                self.tile_departure.set_muted("terminates", "service ends here")
            elif entry.departure_in is not None:
                self.tile_departure.set_value(
                    countdown(entry.departure_in),
                    format_hhmm(now + entry.departure_in),
                )
            else:
                self.tile_departure.set_muted()

        self._update_loop(board, now)
        self._update_following(board, now)

    def _update_loop(self, board: StationBoard, now: float) -> None:
        """Third tile, shown only at short-turn stations."""
        visible = board.is_short_turn
        self.tile_loop.setVisible(visible)
        self.loop_note.setVisible(visible)
        if not visible:
            return

        loop = board.loop
        if loop is None or loop.departs_in is None:
            self.tile_loop.set_muted("--", "no reversal scheduled")
            self.loop_note.setText(
                "This is a short-turn point, but no service is scheduled to "
                "start back from here within the next hour."
            )
            return

        self.tile_loop.set_value(
            countdown(loop.departs_in),
            f"{format_hhmm(now + loop.departs_in)}  to {loop.to_destination}",
        )
        if loop.arrival_in is not None:
            self.loop_note.setText(
                f"A service terminates here in {countdown(loop.arrival_in)} "
                f"and the next working departs towards {loop.to_destination}."
            )
        else:
            self.loop_note.setText(
                f"Next short-turn service starts here towards {loop.to_destination}."
            )

    def _update_following(self, board: StationBoard, now: float) -> None:
        later = board.entries[1:] if board.entries else ()
        self.following_caption.setVisible(bool(later))
        for index, row in enumerate(self.rows):
            if index < len(later):
                row.set_entry(later[index], now)
                row.setVisible(True)
            else:
                row.setVisible(False)

    def _describe(self, board: StationBoard) -> str:
        station, line = board.station, board.line
        bits = [line.name]
        roles = []
        if station.terminus:
            roles.append("terminus")
        if station.interchange:
            roles.append("interchange")
        if station.short_turn:
            roles.append("short-turn point")
        if station.depot:
            roles.append("depot access")
        bits.append(", ".join(roles) if roles else "through station")
        if station.interchange_with:
            bits.append("connects " + ", ".join(station.interchange_with))
        return "  |  ".join(bits)
