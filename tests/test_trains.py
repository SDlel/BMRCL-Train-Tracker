"""Tests for train motion: position, phase, ETA and midnight behaviour."""

from __future__ import annotations

import pytest

from bmrcl import config
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import parse_hhmm
from bmrcl.core.trains import Phase, run_duration


class TestRunDuration:
    def test_single_hop_is_pure_run_time(self) -> None:
        assert run_duration(1) == config.INTER_STATION_SECONDS

    def test_intermediate_stops_add_dwell(self) -> None:
        assert run_duration(2) == 2 * 120 + 20
        assert run_duration(3) == 3 * 120 + 2 * 20

    def test_no_hops_takes_no_time(self) -> None:
        assert run_duration(0) == 0


def test_peak_has_trains_on_every_line(sim: Simulation) -> None:
    for line_id, trains in sim.frame.trains.items():
        assert trains, f"{line_id} had no trains at the morning peak"


def test_peak_train_count_is_plausible(sim: Simulation) -> None:
    assert 50 <= sim.frame.total_active <= 400


def test_no_service_in_the_small_hours(sim: Simulation) -> None:
    sim.clock.seek(parse_hhmm("02:30"))
    assert sim.rebuild().total_active == 0


def test_positions_stay_on_the_line(sim: Simulation) -> None:
    for line_id, trains in sim.frame.trains.items():
        limit = len(sim.network.line(line_id)) - 1
        assert all(0 <= t.position <= limit for t in trains)


def test_both_directions_are_running(sim: Simulation) -> None:
    for stat in sim.frame.stats.values():
        assert stat.up > 0 and stat.down > 0


def test_short_turn_services_run_at_peak(sim: Simulation) -> None:
    assert sum(s.short_turns for s in sim.frame.stats.values()) > 0


def test_direction_matches_the_run(sim: Simulation) -> None:
    for trains in sim.frame.trains.values():
        for train in trains:
            expected = 1 if train.destination_index > train.origin_index else -1
            assert train.direction == expected


def test_dwelling_trains_sit_on_a_station(sim: Simulation) -> None:
    for trains in sim.frame.trains.values():
        for train in (t for t in trains if t.phase is Phase.DWELL):
            assert train.position == pytest.approx(round(train.position))


class TestContinuity:
    """Motion must be smooth: no jumps, no vanishing trains."""

    def _positions(self, sim: Simulation, at: float) -> dict[str, float]:
        sim.clock.seek(at)
        return {t.run_id: t.position for t in sim.rebuild().trains["purple"]}

    def test_trains_persist_across_a_second(self, sim: Simulation) -> None:
        first = self._positions(sim, parse_hhmm("09:00"))
        second = self._positions(sim, parse_hhmm("09:00") + 1)
        assert len(set(first) & set(second)) > 5

    def test_nothing_teleports(self, sim: Simulation) -> None:
        first = self._positions(sim, parse_hhmm("09:00"))
        second = self._positions(sim, parse_hhmm("09:00") + 1)
        for run_id in set(first) & set(second):
            assert abs(second[run_id] - first[run_id]) < 0.02

    def test_trains_actually_move(self, sim: Simulation) -> None:
        first = self._positions(sim, parse_hhmm("09:00"))
        second = self._positions(sim, parse_hhmm("09:00") + 1)
        shared = set(first) & set(second)
        assert any(second[r] != first[r] for r in shared)

    def test_position_is_a_pure_function_of_time(self, sim: Simulation) -> None:
        """The same instant must always produce the same picture."""
        once = self._positions(sim, parse_hhmm("14:23"))
        sim.clock.seek(parse_hhmm("19:00"))
        sim.rebuild()
        twice = self._positions(sim, parse_hhmm("14:23"))
        assert once == twice


class TestEta:
    def test_arrivals_are_ordered_and_positive(self, sim: Simulation) -> None:
        line = sim.network.line("purple")
        arrivals = sim.arrivals_for("purple", line.index_of("mahatma_gandhi_road"))
        assert arrivals
        etas = [eta for _, eta in arrivals]
        assert etas == sorted(etas)
        assert all(eta >= 0 for eta in etas)

    def test_eta_is_none_for_stations_behind_the_train(self, sim: Simulation) -> None:
        train = next(
            t
            for t in sim.frame.trains["purple"]
            if t.direction > 0 and t.from_index > t.origin_index
        )
        assert train.eta_to(train.origin_index) is None

    def test_eta_grows_with_distance(self, sim: Simulation) -> None:
        train = next(
            t
            for t in sim.frame.trains["purple"]
            if t.direction > 0 and t.destination_index - t.to_index >= 3
        )
        near = train.eta_to(train.to_index)
        far = train.eta_to(train.to_index + 3)
        assert far > near

    def test_departure_trails_arrival_by_the_dwell(self, sim: Simulation) -> None:
        train = next(
            t
            for t in sim.frame.trains["green"]
            if t.direction > 0 and t.to_index < t.destination_index
        )
        arrival = train.eta_to(train.to_index)
        departure = train.departure_eta_to(train.to_index)
        assert departure - arrival == pytest.approx(config.DWELL_SECONDS)

    def test_terminating_train_never_departs(self, sim: Simulation) -> None:
        train = next(t for t in sim.frame.trains["purple"])
        assert train.departure_eta_to(train.destination_index) is None
        assert train.terminates_at(train.destination_index)


class TestMidnight:
    def test_late_train_survives_the_rollover(self, sim: Simulation) -> None:
        """A 23:55 departure is still in service after midnight."""
        sim.clock.seek(parse_hhmm("00:15"))
        trains = sim.rebuild().trains["yellow"]
        assert trains
        assert any(t.departure_time == parse_hhmm("23:55") for t in trains)

    def test_counts_stay_sane_across_the_boundary(self, sim: Simulation) -> None:
        for hhmm in ("23:30", "23:59", "00:01", "00:30"):
            sim.clock.seek(parse_hhmm(hhmm))
            assert 0 <= sim.rebuild().total_active < 200
