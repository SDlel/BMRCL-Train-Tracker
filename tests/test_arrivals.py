"""Tests for the station arrival board, including short-turn reversals."""

from __future__ import annotations

import pytest

from bmrcl import config
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import parse_hhmm


@pytest.fixture
def jayanagar(sim: Simulation):
    """An ordinary through station."""
    return sim.board_for(sim.network.line("green").station("jayanagar"))


@pytest.fixture
def yelachenahalli(sim: Simulation):
    """A short-turn point where services reverse."""
    return sim.board_for(sim.network.line("green").station("yelachenahalli"))


class TestOrdinaryStation:
    """A normal station answers two questions: arrives when, departs when."""

    def test_is_not_a_short_turn_point(self, jayanagar) -> None:
        assert not jayanagar.is_short_turn

    def test_has_no_loop_event(self, jayanagar) -> None:
        assert jayanagar.loop is None

    def test_has_a_next_train(self, jayanagar) -> None:
        assert jayanagar.next_entry is not None

    def test_arrival_is_not_in_the_past(self, jayanagar) -> None:
        assert jayanagar.next_entry.arrival_in >= 0

    def test_departure_is_arrival_plus_dwell(self, jayanagar) -> None:
        entry = jayanagar.next_entry
        assert entry.departure_in - entry.arrival_in == pytest.approx(config.DWELL_SECONDS)

    def test_entries_are_sorted_by_arrival(self, jayanagar) -> None:
        etas = [e.arrival_in for e in jayanagar.entries]
        assert etas == sorted(etas)

    def test_every_entry_names_a_destination(self, jayanagar) -> None:
        assert all(e.destination for e in jayanagar.entries)


class TestShortTurnStation:
    """A short-turn point adds a third question: when does one turn back."""

    def test_is_flagged_as_short_turn(self, yelachenahalli) -> None:
        assert yelachenahalli.is_short_turn

    def test_has_a_loop_event(self, yelachenahalli) -> None:
        assert yelachenahalli.loop is not None

    def test_loop_has_a_departure(self, yelachenahalli) -> None:
        assert yelachenahalli.loop.departs_in is not None
        assert yelachenahalli.loop.departs_in >= 0

    def test_loop_names_where_it_goes(self, yelachenahalli) -> None:
        assert yelachenahalli.loop.to_destination


@pytest.mark.parametrize("station_id", ["peenya_industry", "yelachenahalli"])
def test_green_short_turn_points_report_loops(sim: Simulation, station_id: str) -> None:
    board = sim.board_for(sim.network.line("green").station(station_id))
    assert board.is_short_turn
    assert board.loop is not None


def test_terminating_trains_have_no_departure(sim: Simulation) -> None:
    board = sim.board_for(sim.network.line("purple").station("challaghatta"))
    ending = [e for e in board.entries if e.terminates]
    assert ending
    assert all(e.departure_in is None for e in ending)


def test_yellow_short_turn_points_do_not_invent_a_loop(sim: Simulation) -> None:
    """Yellow has no published short workings; the board must stay honest."""
    board = sim.board_for(sim.network.line("yellow").station("electronic_city"))
    assert board.loop is None or board.loop.departs_in is None


def test_board_is_empty_outside_service_hours(sim: Simulation) -> None:
    sim.clock.seek(parse_hhmm("03:00"))
    sim.rebuild()
    board = sim.board_for(sim.network.line("green").station("jayanagar"))
    assert board.entries == ()
    assert board.next_entry is None


def test_limit_is_respected(sim: Simulation) -> None:
    board = sim.board_for(sim.network.line("purple").station("indiranagar"), limit=2)
    assert len(board.entries) <= 2


def test_dwelling_flag_matches_a_berthed_train(sim: Simulation) -> None:
    for line in sim.network:
        for station in line:
            board = sim.board_for(station, limit=1)
            entry = board.next_entry
            if entry is not None:
                assert entry.dwelling_now == (entry.arrival_in <= 0)
