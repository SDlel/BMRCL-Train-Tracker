"""Static network model: stations, lines and the whole metro network.

The network is assembled entirely from JSON files in ``bmrcl/data/lines``.
Adding Blue, Orange or the Airport line therefore requires nothing more than
dropping a new JSON document into that directory.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .. import config


@dataclass(frozen=True, slots=True)
class Station:
    """A single station on one line."""

    id: str
    name: str
    code: str
    index: int
    line_id: str
    terminus: bool = False
    interchange: bool = False
    short_turn: bool = False
    depot: bool = False
    interchange_with: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Globally unique key (a station id may repeat across lines)."""
        return f"{self.line_id}:{self.id}"

    @property
    def radius(self) -> float:
        if self.interchange:
            return config.INTERCHANGE_RADIUS
        if self.terminus:
            return config.TERMINUS_RADIUS
        return config.STATION_RADIUS


@dataclass(slots=True)
class Line:
    """An ordered sequence of stations plus presentation metadata."""

    id: str
    name: str
    short_name: str
    colour: str
    colour_dim: str
    row: int
    order: int
    stations: list[Station] = field(default_factory=list)
    terminals: dict[str, str] = field(default_factory=dict)
    _index_by_id: dict[str, int] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, payload: dict) -> Line:
        line = cls(
            id=payload["id"],
            name=payload["name"],
            short_name=payload.get("short_name", payload["id"][:3].upper()),
            colour=payload.get("colour", "#888888"),
            colour_dim=payload.get("colour_dim", "#444444"),
            row=int(payload.get("row", 0)),
            order=int(payload.get("order", 0)),
            terminals=dict(payload.get("terminals", {})),
        )
        last = len(payload["stations"]) - 1
        for index, raw in enumerate(payload["stations"]):
            station = Station(
                id=raw["id"],
                name=raw["name"],
                code=raw.get("code", raw["id"][:3].upper()),
                index=index,
                line_id=line.id,
                terminus=bool(raw.get("terminus", index in (0, last))),
                interchange=bool(raw.get("interchange", False)),
                short_turn=bool(raw.get("short_turn", False)),
                depot=bool(raw.get("depot", False)),
                interchange_with=tuple(raw.get("interchange_with", ())),
            )
            line.stations.append(station)
            line._index_by_id[station.id] = index
        return line

    def __len__(self) -> int:
        return len(self.stations)

    def __iter__(self) -> Iterator[Station]:
        return iter(self.stations)

    def index_of(self, station_id: str) -> int:
        """Return the ordinal position of ``station_id``.

        Raises:
            KeyError: if the station does not belong to this line.
        """
        try:
            return self._index_by_id[station_id]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"{station_id!r} is not on line {self.id!r}") from exc

    def has(self, station_id: str) -> bool:
        return station_id in self._index_by_id

    def station(self, station_id: str) -> Station:
        return self.stations[self.index_of(station_id)]

    def at(self, index: int) -> Station:
        return self.stations[index]

    @property
    def first(self) -> Station:
        return self.stations[0]

    @property
    def last(self) -> Station:
        return self.stations[-1]

    @property
    def interchanges(self) -> list[Station]:
        return [s for s in self.stations if s.interchange]

    @property
    def short_turn_points(self) -> list[Station]:
        return [s for s in self.stations if s.short_turn]

    def run_time_seconds(self, a_index: int, b_index: int) -> float:
        """Total run time (excluding terminal dwell) between two indices."""
        hops = abs(b_index - a_index)
        if hops == 0:
            return 0.0
        return hops * config.INTER_STATION_SECONDS + (hops - 1) * config.DWELL_SECONDS


class Network:
    """Collection of every :class:`Line` known to the dashboard."""

    def __init__(self, lines: Sequence[Line]) -> None:
        self._lines: list[Line] = sorted(lines, key=lambda ln: (ln.order, ln.id))
        self._by_id = {line.id: line for line in self._lines}

    @classmethod
    def load(cls, directory: Path | None = None) -> Network:
        """Load every ``*.json`` line definition found in ``directory``."""
        directory = directory or config.LINES_DIR
        lines: list[Line] = []
        for path in sorted(directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                lines.append(Line.from_dict(json.load(handle)))
        if not lines:  # pragma: no cover - configuration error
            raise RuntimeError(f"No line definitions found in {directory}")
        return cls(lines)

    def __iter__(self) -> Iterator[Line]:
        return iter(self._lines)

    def __len__(self) -> int:
        return len(self._lines)

    @property
    def lines(self) -> list[Line]:
        return list(self._lines)

    def line(self, line_id: str) -> Line:
        return self._by_id[line_id]

    def get(self, line_id: str) -> Line | None:
        return self._by_id.get(line_id)

    def subset(self, line_ids: Sequence[str]) -> Network:
        """Return a view containing only ``line_ids``.

        Used to give each line tab its own scene.  The :class:`Line` objects
        themselves are shared, not copied, so this is cheap.
        """
        wanted = [self._by_id[lid] for lid in line_ids if lid in self._by_id]
        return Network(wanted)

    @property
    def station_count(self) -> int:
        return sum(len(line) for line in self._lines)

    @property
    def unique_station_count(self) -> int:
        return len({station.name for line in self._lines for station in line})

    def stations_named(self, name: str) -> list[Station]:
        """Every physical platform group sharing a passenger-facing name."""
        return [s for line in self._lines for s in line if s.name == name]

    def interchange_names(self) -> set[str]:
        counter: dict[str, int] = {}
        for line in self._lines:
            for station in line:
                counter[station.name] = counter.get(station.name, 0) + 1
        return {name for name, count in counter.items() if count > 1}

    def iter_stations(self) -> Iterable[Station]:
        for line in self._lines:
            yield from line
