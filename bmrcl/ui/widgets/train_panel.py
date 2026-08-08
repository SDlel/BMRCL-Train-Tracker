"""Dockable train detail panel.

Selecting a train shows where it is, where it is going and how far through its
run it has travelled. It sits directly beneath the station panel so that the
right-hand column always answers the question "what did I just click".

The panel is driven by live :class:`TrainState` snapshots rather than by the
click event, because a train keeps moving after it is selected. Each refresh
re-finds the run by its identifier, so the readout stays correct until the run
terminates.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.network import Line
from ...core.timetable import format_hhmm
from ...core.trains import Phase, TrainState, run_duration
from .. import theme
from .detail_common import EventTile, ProgressBar, caption_label, countdown, elapsed_text, rule

PHASE_TEXT = {
    Phase.RUNNING: "In motion",
    Phase.DWELL: "At platform",
    Phase.TERMINATED: "Terminated",
}

PHASE_COLOUR = {
    Phase.RUNNING: theme.HEX["text"],
    Phase.DWELL: theme.HEX["warn"],
    Phase.TERMINATED: theme.HEX["text_faint"],
}


class FactRow(QWidget):
    """A label and value pair on one line."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(8)

        self.caption = QLabel(caption)
        self.caption.setFont(theme.ui_font(8))
        self.caption.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        self.caption.setFixedWidth(84)

        self.value = QLabel("--")
        self.value.setFont(theme.ui_font(8))
        self.value.setWordWrap(True)
        self.value.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        row.addWidget(self.caption)
        row.addWidget(self.value, 1)

    def set_value(self, text: str, colour: str | None = None) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {colour or theme.HEX['text']};")


class TrainPanel(QWidget):
    """Detail view for the currently selected train."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._run_id: str | None = None
        self._build()
        self.show_placeholder()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(9)

        self.title = QLabel("No train selected")
        self.title.setFont(theme.ui_font(13, bold=True))
        self.title.setWordWrap(True)
        root.addWidget(self.title)

        self.subtitle = QLabel("Click a train on the diagram")
        self.subtitle.setFont(theme.ui_font(8))
        self.subtitle.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)

        root.addWidget(rule())

        tiles = QGridLayout()
        tiles.setContentsMargins(0, 0, 0, 0)
        tiles.setHorizontalSpacing(18)
        self.tile_next = EventTile("NEXT STOP", theme.TEXT)
        self.tile_status = EventTile("STATUS", theme.TEXT)
        tiles.addWidget(self.tile_next, 0, 0)
        tiles.addWidget(self.tile_status, 0, 1)
        root.addLayout(tiles)

        self.progress_caption = caption_label("JOURNEY PROGRESS")
        root.addWidget(self.progress_caption)

        self.progress = ProgressBar()
        root.addWidget(self.progress)

        self.progress_text = QLabel("")
        self.progress_text.setFont(theme.mono_font(8))
        self.progress_text.setStyleSheet(f"color: {theme.HEX['text_dim']};")
        root.addWidget(self.progress_text)

        root.addWidget(rule())

        self.facts: dict[str, FactRow] = {}
        for key, caption in (
            ("service", "Service"),
            ("from", "From"),
            ("to", "Towards"),
            ("departed", "Departed"),
            ("arrives", "Arrives"),
            ("direction", "Direction"),
            ("type", "Pattern"),
        ):
            row = FactRow(caption)
            self.facts[key] = row
            root.addWidget(row)

        root.addStretch(1)

    def show_placeholder(self) -> None:
        """Reset to the nothing-selected state."""
        self._run_id = None
        self.title.setText("No train selected")
        self.title.setStyleSheet(f"color: {theme.HEX['text']};")
        self.subtitle.setText("Click any train on the diagram to follow its run.")
        for tile in (self.tile_next, self.tile_status):
            tile.set_muted()
        self.progress.set_progress(0.0, theme.HEX["text_faint"])
        self.progress_text.setText("")
        for row in self.facts.values():
            row.set_value("--", theme.HEX["text_faint"])

    def show_finished(self) -> None:
        """The selected run has left the network."""
        self.subtitle.setText("This run has completed and is no longer in service.")
        for tile in (self.tile_next, self.tile_status):
            tile.set_muted()
        self.progress.set_progress(1.0, theme.HEX["text_faint"])
        self.progress_text.setText("Run complete")

    def update_train(self, train: TrainState, line: Line, now: float) -> None:
        """Render a live :class:`TrainState`."""
        if self._run_id != train.run_id:
            self._run_id = train.run_id
            self.title.setText(train.run_label)
            self.title.setStyleSheet(f"color: {line.colour};")

        origin = line.at(train.origin_index).name
        destination = line.at(train.destination_index).name
        next_stop = line.at(train.to_index).name

        badge = "Short turn" if train.short_turn else "Full route"
        self.subtitle.setText(f"{line.name}  |  {badge}")

        if train.phase is Phase.TERMINATED:
            self.tile_next.set_muted("arrived", destination)
        elif train.phase is Phase.DWELL:
            self.tile_next.set_value(
                countdown(train.dwell_remaining),
                f"departing {next_stop}",
                theme.HEX["warn"],
            )
        else:
            self.tile_next.set_value(
                countdown(train.seconds_to_next),
                f"{next_stop}  ({format_hhmm(now + train.seconds_to_next)})",
            )

        self.tile_status.set_value(
            PHASE_TEXT.get(train.phase, "Unknown"),
            f"stop {abs(train.from_index - train.origin_index)} of {train.hops_total}",
            PHASE_COLOUR.get(train.phase, theme.HEX["text"]),
        )
        self.tile_status.value.setFont(theme.ui_font(13, bold=True))

        self.progress.set_progress(train.progress, line.colour)
        remaining = abs(train.destination_index - train.from_index)
        self.progress_text.setText(
            f"{train.progress * 100:.0f}% complete  |  {remaining} "
            f"{'stop' if remaining == 1 else 'stops'} remaining"
        )

        self.facts["service"].set_value(train.service_label)
        self.facts["from"].set_value(origin)
        self.facts["to"].set_value(destination)
        self.facts["departed"].set_value(
            f"{format_hhmm(train.departure_time)}  ({elapsed_text(now - train.departure_time)} ago)"
        )

        if train.phase is Phase.TERMINATED:
            arrived_at = train.departure_time + run_duration(train.hops_total)
            self.facts["arrives"].set_value(
                f"arrived {format_hhmm(arrived_at)}", theme.HEX["text_dim"]
            )
        else:
            eta = train.eta_to(train.destination_index)
            self.facts["arrives"].set_value(format_hhmm(now + eta) if eta is not None else "--")

        # "Up" and "Down" are railway convention but mean nothing on their own,
        # so name the end of the line each direction heads towards.
        heading = line.last.name if train.direction > 0 else line.first.name
        self.facts["direction"].set_value(
            f"{'Up' if train.direction > 0 else 'Down'}  (towards {heading})"
        )
        self.facts["type"].set_value(
            badge, theme.HEX["warn"] if train.short_turn else theme.HEX["text"]
        )
