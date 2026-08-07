"""Train movement model and the train manager.

Train positions are computed as a **pure function of simulated time**.  Nothing
is integrated frame to frame, which means:

* seeking, pausing and speed changes are exact and cost nothing;
* the same time always yields the same picture (deterministic and testable);
* there is no drift over a long running session.

A run is described by ``(origin index, destination index, departure time)``.
Between two adjacent stations a train needs ``INTER_STATION_SECONDS``; at each
intermediate station it dwells for ``DWELL_SECONDS``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .. import config
from .network import Line, Network
from .timetable import Departure, Service, Timetable


class Phase(StrEnum):
    """What a train is doing right now."""

    RUNNING = "running"
    DWELL = "dwell"
    TERMINATED = "terminated"


@dataclass(slots=True)
class TrainState:
    """A live train, positioned in continuous station-index space."""

    run_id: str
    line_id: str
    service_id: str
    service_label: str
    short_turn: bool
    origin_index: int
    destination_index: int
    departure_time: int
    position: float  # continuous index along the line
    direction: int  # +1 towards higher indices, -1 towards lower
    phase: Phase
    from_index: int  # last station departed / currently stopped at
    to_index: int  # next station
    seconds_to_next: float  # arrival countdown at ``to_index``
    dwell_remaining: float
    progress: float  # 0..1 of the whole run
    delay: float = 0.0  # reserved for future perturbation modelling

    @property
    def is_moving(self) -> bool:
        return self.phase is Phase.RUNNING

    @property
    def hops_total(self) -> int:
        return abs(self.destination_index - self.origin_index)

    def terminates_at(self, station_index: int) -> bool:
        """True if this run ends at ``station_index`` rather than passing through."""
        return station_index == self.destination_index

    def departure_eta_to(self, station_index: int) -> float | None:
        """Seconds until this train *leaves* ``station_index``.

        Returns ``None`` for a train that terminates there, since it does not
        depart in service - it turns back as a different run.
        """
        arrival = self.eta_to(station_index)
        if arrival is None or self.terminates_at(station_index):
            return None
        return arrival + config.DWELL_SECONDS

    def eta_to(self, station_index: int) -> float | None:
        """Seconds until this train reaches ``station_index``.

        Returns ``None`` when the station is behind the train or beyond its
        terminating point.
        """
        if self.direction > 0 and not (self.to_index <= station_index <= self.destination_index):
            return None
        if self.direction < 0 and not (self.destination_index <= station_index <= self.to_index):
            return None
        hops_after_next = abs(station_index - self.to_index)
        eta = self.seconds_to_next + self.dwell_remaining
        eta += hops_after_next * (config.INTER_STATION_SECONDS + config.DWELL_SECONDS)
        if hops_after_next:
            eta -= config.DWELL_SECONDS
        return max(0.0, eta)


def run_duration(hops: int) -> float:
    """Total time from origin departure to destination arrival."""
    if hops <= 0:
        return 0.0
    return hops * config.INTER_STATION_SECONDS + (hops - 1) * config.DWELL_SECONDS


class RunResolver:
    """Turns a :class:`Departure` into a :class:`TrainState` for a given time."""

    CYCLE = config.INTER_STATION_SECONDS + config.DWELL_SECONDS

    def __init__(self, line: Line) -> None:
        self.line = line

    def resolve(self, departure: Departure, now: float) -> TrainState | None:
        """Return the train state at ``now`` or ``None`` if it is not running."""
        service: Service = departure.service
        origin = self.line.index_of(service.origin)
        destination = self.line.index_of(service.destination)
        hops = abs(destination - origin)
        if hops == 0:
            return None
        direction = 1 if destination > origin else -1

        elapsed = now - departure.time
        total = run_duration(hops)
        if elapsed < 0.0:
            return None
        if elapsed > total + config.TURNAROUND_SECONDS:
            return None

        if elapsed >= total:
            return TrainState(
                run_id=departure.run_id,
                line_id=self.line.id,
                service_id=service.id,
                service_label=service.label,
                short_turn=service.is_short_turn,
                origin_index=origin,
                destination_index=destination,
                departure_time=departure.time,
                position=float(destination),
                direction=direction,
                phase=Phase.TERMINATED,
                from_index=destination,
                to_index=destination,
                seconds_to_next=0.0,
                dwell_remaining=max(0.0, total + config.TURNAROUND_SECONDS - elapsed),
                progress=1.0,
            )

        hop = int(elapsed // self.CYCLE)
        rem = elapsed - hop * self.CYCLE
        from_index = origin + direction * hop
        to_index = from_index + direction

        if rem < config.INTER_STATION_SECONDS:
            fraction = rem / config.INTER_STATION_SECONDS
            position = from_index + direction * fraction
            phase = Phase.RUNNING
            seconds_to_next = config.INTER_STATION_SECONDS - rem
            dwell_remaining = 0.0
        else:
            position = float(to_index)
            phase = Phase.DWELL
            seconds_to_next = 0.0
            dwell_remaining = self.CYCLE - rem
            from_index = to_index
            to_index = min(max(from_index + direction, 0), len(self.line) - 1)

        return TrainState(
            run_id=departure.run_id,
            line_id=self.line.id,
            service_id=service.id,
            service_label=service.label,
            short_turn=service.is_short_turn,
            origin_index=origin,
            destination_index=destination,
            departure_time=departure.time,
            position=position,
            direction=direction,
            phase=phase,
            from_index=from_index,
            to_index=to_index,
            seconds_to_next=seconds_to_next,
            dwell_remaining=dwell_remaining,
            progress=min(1.0, elapsed / total) if total else 1.0,
        )


class LineTrainManager:
    """Produces the set of live trains on one line at any instant."""

    def __init__(self, line: Line, timetable: Timetable) -> None:
        self.line = line
        self.timetable = timetable
        self._resolver = RunResolver(line)
        self._max_span = run_duration(len(line) - 1) + config.TURNAROUND_SECONDS + 60.0

    def trains_at(self, now: float, day_type: str) -> list[TrainState]:
        """All trains physically present on the line at ``now``."""
        plan = self.timetable.plan(self.line.id, day_type)
        window_start = now - self._max_span
        candidates: list[Departure] = plan.slice(int(window_start), int(now) + 1)
        if window_start < 0:
            # Runs that departed just before midnight are still on the network.
            wrapped = plan.slice(int(config.SECONDS_PER_DAY + window_start), config.SECONDS_PER_DAY)
            for dep in wrapped:
                state = self._resolver.resolve(dep, now + config.SECONDS_PER_DAY)
                if state is not None:
                    candidates.append(dep)
        out: list[TrainState] = []
        for dep in candidates:
            reference = now if dep.time <= now else now + config.SECONDS_PER_DAY
            state = self._resolver.resolve(dep, reference)
            if state is not None:
                out.append(state)
        return out

    def next_arrivals(
        self,
        station_index: int,
        now: float,
        day_type: str,
        limit: int = config.TOOLTIP_ARRIVALS,
    ) -> list[tuple[TrainState, float]]:
        """Upcoming arrivals at ``station_index``, soonest first."""
        arrivals: list[tuple[TrainState, float]] = []
        for train in self.trains_at(now, day_type):
            eta = train.eta_to(station_index)
            if eta is not None:
                arrivals.append((train, eta))
        arrivals.sort(key=lambda pair: pair[1])
        return arrivals[:limit]


class TrainManager:
    """Network-wide facade over the per-line managers."""

    def __init__(self, network: Network, timetable: Timetable) -> None:
        self.network = network
        self.timetable = timetable
        self._managers = {line.id: LineTrainManager(line, timetable) for line in network}

    def line_manager(self, line_id: str) -> LineTrainManager:
        return self._managers[line_id]

    def snapshot(self, now: float, day_type: str) -> dict[str, list[TrainState]]:
        """Live trains for every line, keyed by line id."""
        return {line_id: mgr.trains_at(now, day_type) for line_id, mgr in self._managers.items()}

    def total_active(self, now: float, day_type: str) -> int:
        return sum(len(v) for v in self.snapshot(now, day_type).values())
