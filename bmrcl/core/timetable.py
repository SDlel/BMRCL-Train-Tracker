"""Timetable parsing and departure expansion.

The JSON timetable stores *headway windows* rather than explicit departure
times.  This module turns those windows into a concrete, sorted list of
:class:`Departure` records for a given day type.  Rendering code never sees a
frequency value - it only consumes expanded departures.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .. import config
from .network import Line, Network

DEFAULT_WEEKDAY_MAP = {
    0: "monday",
    1: "tue_fri",
    2: "tue_fri",
    3: "tue_fri",
    4: "tue_fri",
    5: "saturday",
    6: "sunday",
}


def parse_hhmm(value: str) -> int:
    """Convert ``"HH:MM"`` (or ``"HH:MM:SS"``) into seconds after midnight."""
    parts = value.strip().split(":")
    if len(parts) == 2:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), 0
    elif len(parts) == 3:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
    else:  # pragma: no cover - malformed data
        raise ValueError(f"Cannot parse time {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def format_hhmm(seconds: float) -> str:
    """Render seconds-after-midnight as ``HH:MM`` (wrapping past midnight)."""
    total = int(seconds) % config.SECONDS_PER_DAY
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


def format_hhmmss(seconds: float) -> str:
    total = int(seconds) % config.SECONDS_PER_DAY
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True, slots=True)
class Window:
    """A frequency window: a departure every ``headway`` minutes."""

    start: int
    end: int
    headway_minutes: float

    @property
    def headway_seconds(self) -> float:
        return self.headway_minutes * 60.0

    def departures(self, *, closing: bool = False) -> list[int]:
        """Expand the window into concrete departure times.

        ``start`` is always inclusive.  ``end`` is normally *exclusive*, because
        it is the moment the next frequency window takes over and therefore
        owns that departure.  For the final window of a service ``closing`` is
        set, and ``end`` is treated as the published last-train time so that the
        last service of the day is not silently dropped.
        """
        step = self.headway_seconds
        if step <= 0:  # pragma: no cover - malformed data
            return []
        out: list[int] = []
        t = float(self.start)
        while t < self.end - 1e-6:
            out.append(round(t))
            t += step
        if closing and (not out or out[-1] != self.end):
            out.append(int(self.end))
        return out


@dataclass(frozen=True, slots=True)
class Service:
    """A scheduled pattern from one origin to one destination."""

    id: str
    label: str
    kind: str  # "full" | "short"
    line_id: str
    origin: str
    destination: str
    windows: tuple[Window, ...] = ()
    explicit: tuple[int, ...] = ()

    @property
    def is_short_turn(self) -> bool:
        return self.kind == "short"

    @property
    def display_id(self) -> str:
        """Service code with the line spelled out.

        The stored ids are terse three-letter codes such as ``GRN-SLK-FULL``.
        ``GRN`` is not obvious to a reader, so the leading segment is replaced
        with the line name for anything shown in the interface.
        """
        _, _, remainder = self.id.partition("-")
        line_name = self.line_id.capitalize()
        return f"{line_name}-{remainder}" if remainder else line_name

    def departure_times(self) -> list[int]:
        """Every departure of this service, sorted and de-duplicated."""
        times: list[int] = list(self.explicit)
        last = len(self.windows) - 1
        for i, window in enumerate(self.windows):
            # Only the chronologically final window closes the service; the
            # timetable may list a morning and an evening block for the same
            # short-turn service, and the morning block is not a closure.
            closing = i == last and window.end == max(w.end for w in self.windows)
            times.extend(window.departures(closing=closing))
        return sorted(set(times))


@dataclass(frozen=True, slots=True)
class Departure:
    """One concrete train departure produced by expanding a service."""

    service: Service
    time: int  # seconds after midnight
    trip_index: int

    @property
    def run_id(self) -> str:
        """Stable internal identifier, used to match a run between frames."""
        return f"{self.service.id}#{self.trip_index:03d}"

    @property
    def run_label(self) -> str:
        """Human-readable name shown in the interface.

        Trips are numbered from one rather than zero, because this is read by
        people rather than indexed by code.
        """
        return f"{self.service.display_id}  No. {self.trip_index + 1}"


class DayPlan:
    """Every departure of every service on one line, for one day type."""

    __slots__ = ("_times", "day_type", "departures", "line_id", "services")

    def __init__(self, line_id: str, day_type: str, services: Sequence[Service]) -> None:
        self.line_id = line_id
        self.day_type = day_type
        self.services = list(services)
        departures: list[Departure] = []
        for service in self.services:
            for i, t in enumerate(service.departure_times()):
                departures.append(Departure(service=service, time=t, trip_index=i))
        departures.sort(key=lambda d: (d.time, d.service.id))
        self.departures = departures
        self._times = [d.time for d in departures]

    def __len__(self) -> int:
        return len(self.departures)

    def slice(self, start: int, end: int) -> list[Departure]:
        """Departures with ``start <= time < end`` (no midnight wrap)."""
        lo = bisect_left(self._times, start)
        out: list[Departure] = []
        for i in range(lo, len(self.departures)):
            if self._times[i] >= end:
                break
            out.append(self.departures[i])
        return out

    @property
    def first_departure(self) -> int | None:
        return self._times[0] if self._times else None

    @property
    def last_departure(self) -> int | None:
        return self._times[-1] if self._times else None


class Timetable:
    """Parsed timetable document with per-line, per-day-type plans."""

    def __init__(self, payload: dict, network: Network) -> None:
        self._payload = payload
        self._network = network
        self.meta: dict = payload.get("meta", {})
        self.day_types: dict[str, dict] = payload.get("day_types", {})
        self._weekday_map = self._build_weekday_map()
        self._services: dict[tuple[str, str], list[Service]] = {}
        self._plans: dict[tuple[str, str], DayPlan] = {}
        self._parse(payload.get("lines", {}))

    @classmethod
    def load(cls, network: Network, path: Path | None = None) -> Timetable:
        path = path or config.TIMETABLE_FILE
        with path.open("r", encoding="utf-8") as handle:
            return cls(json.load(handle), network)

    def _build_weekday_map(self) -> dict[int, str]:
        mapping: dict[int, str] = {}
        for key, spec in self.day_types.items():
            for weekday in spec.get("weekdays", []):
                mapping[int(weekday)] = key
        return mapping or dict(DEFAULT_WEEKDAY_MAP)

    def _parse(self, lines_payload: dict) -> None:
        for line_id, line_payload in lines_payload.items():
            line = self._network.get(line_id)
            if line is None:
                continue  # timetable references a line that is not installed
            for day_type, raw_services in line_payload.get("services", {}).items():
                services = [self._parse_service(line, day_type, raw) for raw in raw_services]
                self._services[(line_id, day_type)] = [s for s in services if s is not None]

    def _parse_service(self, line: Line, day_type: str, raw: dict) -> Service | None:
        origin, destination = raw["origin"], raw["destination"]
        if not line.has(origin) or not line.has(destination):
            return None  # ignore services referring to unknown stations
        windows = tuple(
            Window(parse_hhmm(w["start"]), parse_hhmm(w["end"]), float(w["headway"]))
            for w in raw.get("windows", [])
        )
        explicit = tuple(parse_hhmm(t) for t in raw.get("departures", []))
        return Service(
            id=raw.get("id", f"{line.short_name}-{origin}-{destination}"),
            label=raw.get(
                "label", f"{line.station(origin).name} to {line.station(destination).name}"
            ),
            kind=raw.get("type", "full"),
            line_id=line.id,
            origin=origin,
            destination=destination,
            windows=windows,
            explicit=explicit,
        )

    def day_type_for(self, when: date) -> str:
        return self._weekday_map.get(when.weekday(), "tue_fri")

    def day_type_label(self, day_type: str) -> str:
        return self.day_types.get(day_type, {}).get("label", day_type)

    @property
    def day_type_keys(self) -> list[str]:
        return list(self.day_types.keys()) or list(dict.fromkeys(DEFAULT_WEEKDAY_MAP.values()))

    def services(self, line_id: str, day_type: str) -> list[Service]:
        return list(self._services.get((line_id, day_type), ()))

    def plan(self, line_id: str, day_type: str) -> DayPlan:
        """Return (and memoise) the expanded plan for a line and day type."""
        key = (line_id, day_type)
        plan = self._plans.get(key)
        if plan is None:
            plan = DayPlan(line_id, day_type, self._services.get(key, ()))
            self._plans[key] = plan
        return plan

    def total_departures(self, day_type: str) -> int:
        return sum(len(self.plan(line.id, day_type)) for line in self._network)

    def service_span(self, line_id: str, day_type: str) -> tuple[int | None, int | None]:
        plan = self.plan(line_id, day_type)
        return plan.first_departure, plan.last_departure
