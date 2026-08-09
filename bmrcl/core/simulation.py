"""The simulation facade tying clock, network, timetable and trains together.

The UI layer only ever talks to :class:`Simulation`; it never reaches into the
timetable or the train manager directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .. import config
from .arrivals import ArrivalBoard, StationBoard
from .clock import ClockState, SimulationClock
from .network import Network, Station
from .timetable import Timetable, format_hhmm
from .trains import Phase, TrainManager, TrainState


@dataclass(slots=True)
class LineStats:
    """Per-line telemetry displayed in the header and side panels."""

    line_id: str
    active: int = 0
    running: int = 0
    dwelling: int = 0
    turning: int = 0
    short_turns: int = 0
    up: int = 0
    down: int = 0


@dataclass(slots=True)
class RefreshResult:
    """Outcome of a timetable refresh, used to report back to the operator."""

    corrected_seconds: float | None
    day_type: str
    day_type_changed: bool
    active_trains: int
    at: float

    @property
    def corrected(self) -> bool:
        """True if the clock was actually moved by a perceptible amount."""
        return self.corrected_seconds is not None and abs(self.corrected_seconds) >= 0.05

    @property
    def offset_text(self) -> str:
        """Signed correction with a unit that suits its size.

        Sub-second corrections are the common case once the clock has settled,
        and reading them as ``0.1s`` loses the detail, so milliseconds are used
        below one second and minutes above ninety.
        """
        if self.corrected_seconds is None:
            return "n/a"
        value = self.corrected_seconds
        sign = "+" if value >= 0 else "-"
        magnitude = abs(value)
        if magnitude < 1.0:
            return f"{sign}{magnitude * 1000:.0f}ms"
        if magnitude < 90.0:
            return f"{sign}{magnitude:.1f}s"
        return f"{sign}{magnitude / 60:.1f}min"

    @property
    def summary(self) -> str:
        """One-line description suitable for a status readout."""
        if self.corrected_seconds is None:
            return f"Verified against timetable, {self.active_trains} trains"
        if not self.corrected:
            return f"Already accurate, {self.active_trains} trains"
        return f"Refreshed ({self.offset_text}), {self.active_trains} trains"


@dataclass(slots=True)
class Frame:
    """Everything the renderer needs for one frame."""

    clock: ClockState
    day_type: str
    trains: dict[str, list[TrainState]] = field(default_factory=dict)
    stats: dict[str, LineStats] = field(default_factory=dict)

    @property
    def total_active(self) -> int:
        return sum(len(v) for v in self.trains.values())


class Simulation:
    """Owns simulated time and derives the live network picture from it."""

    def __init__(self, network: Network | None = None, timetable: Timetable | None = None) -> None:
        self.network = network or Network.load()
        self.timetable = timetable or Timetable.load(self.network)
        self.clock = SimulationClock()
        self.trains = TrainManager(self.network, self.timetable)
        self._day_type_override: str | None = None
        self._frame: Frame | None = None
        self._boards: dict[str, ArrivalBoard] = {}

    @property
    def day_type(self) -> str:
        if self._day_type_override:
            return self._day_type_override
        return self.timetable.day_type_for(self.clock.day)

    @property
    def day_type_label(self) -> str:
        return self.timetable.day_type_label(self.day_type)

    @property
    def day_type_is_overridden(self) -> bool:
        return self._day_type_override is not None

    def set_day_type(self, day_type: str | None) -> None:
        """Force a day type, or pass ``None`` to follow the calendar."""
        self._day_type_override = day_type

    def step(self) -> Frame:
        """Advance the clock and recompute the network picture."""
        self.clock.tick()
        return self.rebuild()

    def rebuild(self) -> Frame:
        """Recompute the picture for the current time without advancing."""
        state = self.clock.state()
        day_type = self.day_type
        trains = self.trains.snapshot(state.seconds, day_type)
        stats: dict[str, LineStats] = {}
        for line_id, items in trains.items():
            stat = LineStats(line_id=line_id, active=len(items))
            for train in items:
                if train.phase is Phase.RUNNING:
                    stat.running += 1
                elif train.phase is Phase.DWELL:
                    stat.dwelling += 1
                elif train.at_terminal:
                    stat.turning += 1
                if train.short_turn:
                    stat.short_turns += 1
                if train.direction > 0:
                    stat.up += 1
                else:
                    stat.down += 1
            stats[line_id] = stat
        self._frame = Frame(clock=state, day_type=day_type, trains=trains, stats=stats)
        return self._frame

    @property
    def frame(self) -> Frame:
        return self._frame or self.rebuild()

    def arrivals_for(self, line_id: str, station_index: int, limit: int = config.TOOLTIP_ARRIVALS):
        return self.trains.line_manager(line_id).next_arrivals(
            station_index, self.clock.seconds, self.day_type, limit
        )

    def refresh(self) -> RefreshResult:
        """Re-check the clock against the system time and rebuild the picture.

        Train positions are derived from the clock rather than accumulated, so
        nothing can drift out of step with the timetable on its own. What does
        drift is the clock itself, and correcting it brings every train back
        into line as a consequence.
        """
        correction = self.clock.correct_drift()
        day_type_before = self.day_type
        frame = self.rebuild()
        return RefreshResult(
            corrected_seconds=correction,
            day_type=frame.day_type,
            day_type_changed=day_type_before != frame.day_type,
            active_trains=frame.total_active,
            at=self.clock.seconds,
        )

    def board_for(self, station: Station, limit: int = 6) -> StationBoard:
        """Full arrival board for a station, including any reversal event."""
        board = self._boards.get(station.line_id)
        if board is None:
            board = ArrivalBoard(self.network.line(station.line_id), self.timetable)
            self._boards[station.line_id] = board
        trains = self.frame.trains.get(station.line_id, [])
        return board.build(station, trains, self.clock.seconds, self.day_type, limit)

    def service_span_text(self, line_id: str) -> str:
        first, last = self.timetable.service_span(line_id, self.day_type)
        if first is None or last is None:
            return "no service"
        return f"{format_hhmm(first)} - {format_hhmm(last)}"

    def scheduled_departures(self, line_id: str) -> int:
        return len(self.timetable.plan(line_id, self.day_type))

    def all_trains_sorted(self, line_ids: Sequence[str] | None = None) -> list[TrainState]:
        """Live trains ordered by line then position.

        Args:
            line_ids: Restrict the result to these lines.  ``None`` returns the
                whole network, which is what the overview tab shows.
        """
        out: list[TrainState] = []
        order = {line.id: line.order for line in self.network}
        wanted = set(line_ids) if line_ids is not None else None
        for line_id, items in self.frame.trains.items():
            if wanted is None or line_id in wanted:
                out.extend(items)
        out.sort(key=lambda t: (order.get(t.line_id, 99), t.position))
        return out
