"""Physical-train linkage: which arriving train works which return service.

The timetable describes *passenger services*. It says a train leaves Whitefield
at 09:00 and another leaves Challaghatta at 09:14; it does not say whether
those are the same vehicle. This module supplies that missing half - the
physical layer - without inventing a single scheduled departure.

Why it is needed
----------------
Without linkage a run that reaches its terminus simply reports ``TERMINATED``,
which reads as though the train evaporated. Real metros turn a train and send
it back. The departures that represent those return workings already exist in
the timetable; the only thing missing is naming which one follows which
arrival.

What it deliberately does not do
--------------------------------
It never creates a departure. Every linked working is an existing timetable
entry, claimed at most once, so service counts are untouched.

It also does not pretend every arrival turns back. On the Purple Line about
twice as many runs terminate at Challaghatta as depart from it, because
short-turn services terminate there too. Under any layover limit the match
rate plateaus near 60%: the surplus arrivals have no departure to claim and are
reported honestly as having no onward working, which is what stabling or a
depot move looks like from the timetable's point of view.

Matching rule
-------------
A departure may be worked by an arriving train when all of the following hold:

* the train arrived at the station the departure leaves from;
* the departure heads the opposite way, since a turnaround reverses the train;
* the train's full turnaround is complete by the departure time;
* the wait is no longer than :data:`~bmrcl.config.MAX_LAYOVER_SECONDS`;
* the train has not already been assigned elsewhere.

Departures are processed in time order, and each takes the **most recently
arrived** eligible train rather than the longest-waiting one. That choice
matters, and the obvious alternative is wrong.

Matching each departure to the *earliest* waiting arrival - plain first-in
first-out - looks more like a real platform queue, but it collapses here.
Roughly twice as many runs terminate at a terminus as depart from it, because
short-turn services terminate there too. Under first-in first-out that surplus
becomes a queue that never drains: every arrival is pushed further back, and
the median layover balloons to twenty-odd minutes. Trains then appear to sit
motionless at the terminal long after their turnaround has finished, which is
both wrong and exactly what it looks like.

Taking the freshest eligible train instead keeps layovers close to the
turnaround, and the surplus older arrivals are simply never claimed. That is
the honest outcome: those vehicles have no onward working and are stabled,
which is what the timetable's arrival/departure imbalance actually implies.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config
from .network import Line
from .timetable import Departure, Timetable


def _run_duration(hops: int) -> float:
    """Origin-departure to destination-arrival time for ``hops`` legs.

    Duplicated from :mod:`~bmrcl.core.trains` rather than imported, because
    that module imports this one and a cycle would be worse than four lines.
    """
    if hops <= 0:
        return 0.0
    return hops * config.INTER_STATION_SECONDS + (hops - 1) * config.DWELL_SECONDS


@dataclass(frozen=True, slots=True)
class Working:
    """The service an arriving physical train goes on to operate."""

    run_id: str
    run_label: str
    departure_time: int
    origin_index: int
    destination_index: int
    destination_name: str
    short_turn: bool

    @property
    def direction(self) -> int:
        return 1 if self.destination_index > self.origin_index else -1


@dataclass(frozen=True, slots=True)
class Arrival:
    """One run reaching the end of its journey."""

    run_id: str
    time: float
    station_id: str
    station_index: int
    direction: int


class PhysicalLinkage:
    """Links arrivals to return workings for one line and day type.

    The whole assignment is computed once and cached, because it is a pure
    function of the timetable. Resolving a train then costs a dictionary
    lookup, which matters when this runs inside the render loop.
    """

    def __init__(self, line: Line, timetable: Timetable, day_type: str) -> None:
        self.line = line
        self.day_type = day_type
        #: arriving run id -> the working it goes on to operate
        self.next_working: dict[str, Working] = {}
        #: departing run id -> the run that brought the train in
        self.previous_run: dict[str, str] = {}
        #: any run id -> identifier of the physical vehicle operating it
        self.physical_ids: dict[str, str] = {}
        self._build(timetable)

    # -- construction -------------------------------------------------------

    def _build(self, timetable: Timetable) -> None:
        plan = timetable.plan(self.line.id, self.day_type)
        arrivals: list[Arrival] = []
        by_origin: dict[str, list[Departure]] = {}

        for departure in plan.departures:
            service = departure.service
            origin = self.line.index_of(service.origin)
            destination = self.line.index_of(service.destination)
            if origin == destination:
                continue
            direction = 1 if destination > origin else -1
            arrivals.append(
                Arrival(
                    run_id=departure.run_id,
                    time=departure.time + _run_duration(abs(destination - origin)),
                    station_id=service.destination,
                    station_index=destination,
                    direction=direction,
                )
            )
            by_origin.setdefault(service.origin, []).append(departure)

        for departures in by_origin.values():
            departures.sort(key=lambda d: d.time)

        arrivals.sort(key=lambda a: a.time)
        by_station: dict[str, list[Arrival]] = {}
        for arrival in arrivals:
            by_station.setdefault(arrival.station_id, []).append(arrival)

        assigned: set[str] = set()
        for station_id, departures in by_origin.items():
            waiting = by_station.get(station_id)
            if not waiting:
                continue
            for departure in departures:
                arrival = self._pick_arrival(departure, waiting, assigned)
                if arrival is None:
                    continue
                assigned.add(arrival.run_id)
                working = self._working_for(departure)
                self.next_working[arrival.run_id] = working
                self.previous_run[working.run_id] = arrival.run_id

        self._assign_physical_ids()

    def _pick_arrival(
        self,
        departure: Departure,
        waiting: list[Arrival],
        assigned: set[str],
    ) -> Arrival | None:
        """Freshest unassigned arrival that can work ``departure``.

        Scanning backwards finds the latest arrival first, which keeps the
        layover as short as the timetable allows.
        """
        service = departure.service
        origin = self.line.index_of(service.origin)
        destination = self.line.index_of(service.destination)
        direction = 1 if destination > origin else -1

        ready_by = departure.time - config.TURNAROUND_SECONDS
        not_before = departure.time - config.MAX_LAYOVER_SECONDS

        for arrival in reversed(waiting):
            if arrival.time > ready_by:
                continue  # turnaround would not be finished in time
            if arrival.time < not_before:
                break  # sorted, so everything earlier waits even longer
            if arrival.run_id in assigned:
                continue
            if arrival.direction == direction:
                # Same direction means this is not our train turning back.
                continue
            return arrival
        return None

    def _working_for(self, departure: Departure) -> Working:
        service = departure.service
        origin = self.line.index_of(service.origin)
        destination = self.line.index_of(service.destination)
        return Working(
            run_id=departure.run_id,
            run_label=departure.run_label,
            departure_time=departure.time,
            origin_index=origin,
            destination_index=destination,
            destination_name=self.line.at(destination).name,
            short_turn=service.is_short_turn,
        )

    def _assign_physical_ids(self) -> None:
        """Give every run in a chain the identifier of the vehicle working it.

        A chain is a sequence of runs joined by turnarounds. The first run in
        the chain names the vehicle, so a train keeps one identity from the
        moment it enters service until it stables.
        """
        counter = 0
        for run_id in self.next_working:
            if run_id in self.previous_run:
                continue  # not the head of a chain
            counter += 1
            physical_id = f"{self.line.short_name}-{counter:03d}"
            current: str | None = run_id
            seen: set[str] = set()
            while current is not None and current not in seen:
                seen.add(current)
                self.physical_ids[current] = physical_id
                working = self.next_working.get(current)
                current = working.run_id if working else None

    # -- queries ------------------------------------------------------------

    def working_after(self, run_id: str) -> Working | None:
        """The service this run's train goes on to operate, if any."""
        return self.next_working.get(run_id)

    def physical_id_for(self, run_id: str) -> str:
        """Vehicle identifier for ``run_id``.

        Unlinked runs fall back to their own run id, so every train always has
        a physical identity even when no chain was found.
        """
        return self.physical_ids.get(run_id, run_id)

    @property
    def linked_count(self) -> int:
        return len(self.next_working)


class LinkageRegistry:
    """Caches one :class:`PhysicalLinkage` per line and day type."""

    def __init__(self, timetable: Timetable) -> None:
        self._timetable = timetable
        self._cache: dict[tuple[str, str], PhysicalLinkage] = {}

    def get(self, line: Line, day_type: str) -> PhysicalLinkage:
        key = (line.id, day_type)
        linkage = self._cache.get(key)
        if linkage is None:
            linkage = PhysicalLinkage(line, self._timetable, day_type)
            self._cache[key] = linkage
        return linkage
