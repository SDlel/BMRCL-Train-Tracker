"""Tests for the train detail panel."""

from __future__ import annotations

import pytest

from bmrcl.core.timetable import parse_hhmm
from bmrcl.core.trains import Phase

from .conftest import pump


def pick(window, phase: Phase, line_id: str = "purple"):
    """First train on ``line_id`` currently in ``phase``."""
    trains = window.simulation.frame.trains[line_id]
    return next((t for t in trains if t.phase is phase), None)


def test_starts_empty(window) -> None:
    assert window.train_panel._run_id is None
    assert window.train_panel.tile_next.value.text() == "--"


def test_dock_exists_and_is_visible(window) -> None:
    assert window.dock_train.isVisible()
    assert window.dock_train.windowTitle() == "TRAIN DETAIL"


def test_clicking_a_train_populates_the_panel(qapp, window) -> None:
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)

    panel = window.train_panel
    assert panel._run_id == train.run_id
    assert panel.title.text() == train.run_label
    assert panel.tile_next.value.text() != "--"
    assert panel.facts["from"].value.text()
    assert panel.facts["to"].value.text()


def test_run_label_is_readable(qapp, window) -> None:
    """The label spells out the line and numbers trips from one."""
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)

    label = window.train_panel.title.text()
    assert label.startswith("Purple-")
    assert "No. " in label
    assert "#" not in label
    assert "PPL" not in label


def test_trip_numbers_start_at_one(sim) -> None:
    plan = sim.timetable.plan("green", "tue_fri")
    first = plan.departures[0]
    assert first.trip_index == 0
    assert first.run_label.endswith("No. 1")


def test_run_id_stays_stable_for_matching(sim) -> None:
    """The internal id must not change, since selection matches on it."""
    plan = sim.timetable.plan("green", "tue_fri")
    departure = plan.departures[0]
    assert "#" in departure.run_id
    assert departure.run_id != departure.run_label


def test_panel_names_the_destination(qapp, window) -> None:
    train = pick(window, Phase.RUNNING)
    line = window.simulation.network.line(train.line_id)
    window._on_train_selected(train)
    pump(qapp)
    expected = line.at(train.destination_index).name
    assert window.train_panel.facts["to"].value.text() == expected


def test_direction_explains_itself(qapp, window) -> None:
    """Up and Down mean nothing alone, so the heading is spelled out."""
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)
    text = window.train_panel.facts["direction"].value.text()
    assert "towards" in text
    assert text.startswith("Up") or text.startswith("Down")


def test_progress_is_reported(qapp, window) -> None:
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)
    assert "%" in window.train_panel.progress_text.text()
    assert "remaining" in window.train_panel.progress_text.text()


def test_dwelling_train_shows_platform_status(qapp, window) -> None:
    train = pick(window, Phase.DWELL)
    if train is None:
        pytest.skip("no dwelling train at this instant")
    window._on_train_selected(train)
    pump(qapp)
    assert window.train_panel.tile_status.value.text() == "At platform"


def test_terminated_train_reports_arrival_in_the_past(qapp, window) -> None:
    """A train standing at its terminal reports when it got there.

    Scans forward rather than relying on the opening frame, because with
    physical linkage enabled most arrivals continue into another working and
    comparatively few runs reach TERMINATED.
    """
    sim = window.simulation
    train = None
    for offset in range(0, 3600, 30):
        sim.clock.seek(parse_hhmm("09:00") + offset)
        sim.rebuild()
        train = next(
            (t for ts in sim.frame.trains.values() for t in ts if t.phase is Phase.TERMINATED),
            None,
        )
        if train is not None:
            break
    assert train is not None, "no terminated train found in an hour of running"

    window._on_train_selected(train)
    pump(qapp)
    assert "arrived" in window.train_panel.facts["arrives"].value.text()


def test_short_turn_is_labelled(qapp, window) -> None:
    trains = window.simulation.frame.trains["purple"]
    train = next((t for t in trains if t.short_turn), None)
    if train is None:
        pytest.skip("no short-turn train at this instant")
    window._on_train_selected(train)
    pump(qapp)
    assert "Short turn" in window.train_panel.subtitle.text()
    assert window.train_panel.facts["type"].value.text() == "Short turn"


def test_panel_follows_the_train_as_time_advances(qapp, window) -> None:
    sim = window.simulation
    train = next(
        t for t in sim.frame.trains["purple"] if t.phase is Phase.RUNNING and t.progress < 0.4
    )
    window._on_train_selected(train)
    pump(qapp)
    before = window.train_panel.progress_text.text()

    sim.clock.seek(parse_hhmm("09:00") + 900)
    sim.rebuild()
    window._refresh_train_panel()
    assert window.train_panel.progress_text.text() != before


def test_panel_reports_when_the_run_finishes(qapp, window) -> None:
    sim = window.simulation
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)

    sim.clock.seek(parse_hhmm("09:00") + 9000)
    sim.rebuild()
    window._refresh_train_panel()
    assert "complete" in window.train_panel.progress_text.text().lower()


def test_selecting_a_station_does_not_disturb_the_train_panel(qapp, window) -> None:
    train = pick(window, Phase.RUNNING)
    window._on_train_selected(train)
    pump(qapp)
    run_id = window.train_panel._run_id

    green = window.simulation.network.line("green")
    window._select_station(green.station("jayanagar"))
    pump(qapp)

    assert window.train_panel._run_id == run_id
    assert window.station_panel._station_key == "green:jayanagar"


def test_both_detail_docks_share_the_right_column(window) -> None:
    assert window.dockWidgetArea(window.dock_station) == window.dockWidgetArea(window.dock_train)
