"""Tests for the static network model loaded from JSON."""

from __future__ import annotations

import pytest

from bmrcl.core.network import Network

EXPECTED_STATION_COUNTS = {"purple": 38, "green": 32, "yellow": 15}

PURPLE_SHORT_TURNS = {
    "garudachar_palya",
    "baiyappanahalli",
    "kempegowda_majestic",
    "mahatma_gandhi_road",
    "mysore_road",
    "pattandur_agrahara",
}

GREEN_SHORT_TURNS = {"nagasandra", "peenya_industry", "yelachenahalli"}


def test_three_lines_load(network: Network) -> None:
    assert [line.id for line in network] == ["purple", "green", "yellow"]


@pytest.mark.parametrize(("line_id", "count"), EXPECTED_STATION_COUNTS.items())
def test_station_counts(network: Network, line_id: str, count: int) -> None:
    assert len(network.line(line_id)) == count


def test_terminals_match_declared_endpoints(network: Network) -> None:
    for line in network:
        assert line.first.id == line.terminals["up"]
        assert line.last.id == line.terminals["down"]
        assert line.first.terminus and line.last.terminus


def test_majestic_is_interchange_on_both_lines(network: Network) -> None:
    for line_id in ("purple", "green"):
        assert network.line(line_id).station("kempegowda_majestic").interchange


def test_rv_road_links_green_and_yellow(network: Network) -> None:
    assert network.line("yellow").station("rv_road").interchange
    assert network.line("green").station("rashtreeya_vidyalaya_road").interchange


def test_purple_short_turn_points(network: Network) -> None:
    found = {s.id for s in network.line("purple").short_turn_points}
    assert found >= PURPLE_SHORT_TURNS


def test_green_short_turn_points(network: Network) -> None:
    found = {s.id for s in network.line("green").short_turn_points}
    assert found >= GREEN_SHORT_TURNS


def test_yellow_is_ready_for_future_short_turns(network: Network) -> None:
    """Yellow publishes no short workings yet, but the data supports them."""
    assert network.line("yellow").short_turn_points


def test_station_ids_unique_within_a_line(network: Network) -> None:
    for line in network:
        ids = [s.id for s in line]
        assert len(ids) == len(set(ids)), f"duplicate station id on {line.id}"


def test_indices_are_contiguous(network: Network) -> None:
    for line in network:
        assert [s.index for s in line] == list(range(len(line)))


def test_index_lookup_round_trips(network: Network) -> None:
    for line in network:
        for station in line:
            assert line.index_of(station.id) == station.index
            assert line.at(station.index) is station


def test_unknown_station_raises(network: Network) -> None:
    with pytest.raises(KeyError):
        network.line("purple").index_of("not_a_station")


def test_run_time_accounts_for_intermediate_dwells(network: Network) -> None:
    line = network.line("purple")
    assert line.run_time_seconds(0, 0) == 0
    assert line.run_time_seconds(0, 1) == 120
    assert line.run_time_seconds(0, 2) == 120 * 2 + 20


def test_subset_shares_line_objects(network: Network) -> None:
    subset = network.subset(["green"])
    assert len(subset) == 1
    assert subset.line("green") is network.line("green")


def test_subset_ignores_unknown_ids(network: Network) -> None:
    assert len(network.subset(["green", "teal"])) == 1
