"""Station arrival board: what is coming, when it leaves, and what turns back.

This is the data behind the station detail panel.  A normal station shows two
facts about its next train - arrival and departure.  A short-turn station shows
a third: when a service next terminates and reverses there, which is the event
an operator actually cares about at places like Yelachenahalli.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from .network import Line, Station
from .timetable import DayPlan, Departure, Timetable
from .trains import RunResolver, TrainState


@dataclass(frozen=True, slots=True)
class BoardEntry:
    """One train's call at a station."""

    train: TrainState
    arrival_in: float  #: seconds until it berths
    departure_in: float | None  #: seconds until it leaves, ``None`` if it terminates
    terminates: bool  #: this station is the end of the run
    destination: str  #: passenger-facing destination name

    @property
    def dwelling_now(self) -> bool:
        """True while the train is standing at this station."""
        return self.arrival_in <= 0.0

    @property
    def short_turn(self) -> bool:
        return self.train.short_turn


@dataclass(frozen=True, slots=True)
class LoopEvent:
    """A service reversing at a short-turn station.

    ``arrival_in`` is when the inbound run terminates; ``departs_in`` is when
    the next outbound run leaves in the opposite direction.  They come from two
    different scheduled runs, which is why this is not simply a
    :class:`BoardEntry` with a longer dwell.
    """

    arrival_in: float | None
    departs_in: float | None
    from_direction: str
    to_destination: str

    @property
    def has_data(self) -> bool:
        return self.arrival_in is not None or self.departs_in is not None


@dataclass(frozen=True, slots=True)
class StationBoard:
    """Everything the detail panel needs for one station."""

    station: Station
    line: Line
    entries: tuple[BoardEntry, ...]
    loop: LoopEvent | None

    @property
    def is_short_turn(self) -> bool:
        return self.station.short_turn

    @property
    def next_entry(self) -> BoardEntry | None:
        return self.entries[0] if self.entries else None


class ArrivalBoard:
    """Builds :class:`StationBoard` snapshots for a line."""

    LOOK_AHEAD_SECONDS = 3600

    def __init__(self, line: Line, timetable: Timetable) -> None:
        self.line = line
        self.timetable = timetable
        self._resolver = RunResolver(line)

    def build(
        self,
        station: Station,
        trains: list[TrainState],
        now: float,
        day_type: str,
        limit: int = 6,
    ) -> StationBoard:
        """Assemble the board for ``station`` at ``now``."""
        entries: list[BoardEntry] = []
        for train in trains:
            arrival = train.eta_to(station.index)
            if arrival is None:
                continue
            terminates = train.terminates_at(station.index)
            entries.append(
                BoardEntry(
                    train=train,
                    arrival_in=arrival,
                    departure_in=train.departure_eta_to(station.index),
                    terminates=terminates,
                    destination=self.line.at(train.destination_index).name,
                )
            )
        entries.sort(key=lambda e: e.arrival_in)
        entries = entries[:limit]

        loop = self._loop_event(station, trains, now, day_type) if station.short_turn else None
        return StationBoard(
            station=station,
            line=self.line,
            entries=tuple(entries),
            loop=loop,
        )

    def _loop_event(
        self,
        station: Station,
        trains: list[TrainState],
        now: float,
        day_type: str,
    ) -> LoopEvent | None:
        """Find the next service that terminates here and the next that starts here."""
        arrival_in: float | None = None
        from_direction = ""
        for train in trains:
            if not train.terminates_at(station.index):
                continue
            eta = train.eta_to(station.index)
            if eta is None:
                continue
            if arrival_in is None or eta < arrival_in:
                arrival_in = eta
                origin = self.line.at(train.origin_index).name
                from_direction = origin

        departs_in, to_destination = self._next_origin_departure(station, now, day_type)

        event = LoopEvent(
            arrival_in=arrival_in,
            departs_in=departs_in,
            from_direction=from_direction,
            to_destination=to_destination,
        )
        return event if event.has_data else None

    def _next_origin_departure(
        self, station: Station, now: float, day_type: str
    ) -> tuple[float | None, str]:
        """Seconds until the next run *originates* from this station."""
        plan: DayPlan = self.timetable.plan(self.line.id, day_type)
        start = int(now)
        upcoming: list[Departure] = plan.slice(start, start + self.LOOK_AHEAD_SECONDS)
        for departure in upcoming:
            if departure.service.origin != station.id:
                continue
            destination = self.line.station(departure.service.destination).name
            return float(departure.time - now), destination

        if start + self.LOOK_AHEAD_SECONDS > config.SECONDS_PER_DAY:
            overflow = start + self.LOOK_AHEAD_SECONDS - config.SECONDS_PER_DAY
            for departure in plan.slice(0, int(overflow)):
                if departure.service.origin != station.id:
                    continue
                destination = self.line.station(departure.service.destination).name
                return float(departure.time + config.SECONDS_PER_DAY - now), destination
        return None, ""
