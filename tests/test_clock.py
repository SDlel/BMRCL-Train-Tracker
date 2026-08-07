"""Tests for the simulation clock: pause, speed, seeking and rollover."""

from __future__ import annotations

from datetime import date

import pytest

from bmrcl import config
from bmrcl.core.clock import SimulationClock
from bmrcl.core.timetable import parse_hhmm


@pytest.fixture
def clock() -> SimulationClock:
    return SimulationClock()


def test_starts_live_and_running(clock: SimulationClock) -> None:
    assert clock.running
    assert clock.live


def test_pausing_stops_time(clock: SimulationClock) -> None:
    clock.set_running(False)
    before = clock.seconds
    clock.tick()
    assert clock.seconds == before


def test_paused_tick_reports_no_delta(clock: SimulationClock) -> None:
    clock.set_running(False)
    assert clock.tick() == 0.0


def test_toggle_flips_the_state(clock: SimulationClock) -> None:
    assert clock.toggle() is False
    assert clock.toggle() is True


def test_seek_sets_an_absolute_time(clock: SimulationClock) -> None:
    clock.seek(parse_hhmm("18:30"))
    assert int(clock.seconds) == parse_hhmm("18:30")


def test_seek_leaves_live_mode(clock: SimulationClock) -> None:
    clock.seek(parse_hhmm("18:30"))
    assert not clock.live


def test_seek_wraps_within_the_day(clock: SimulationClock) -> None:
    clock.seek(config.SECONDS_PER_DAY + 60)
    assert clock.seconds == 60


def test_seek_accepts_a_date(clock: SimulationClock) -> None:
    target = date(2026, 1, 1)
    clock.seek(0, day=target)
    assert clock.day == target


def test_nudge_is_relative(clock: SimulationClock) -> None:
    clock.seek(parse_hhmm("12:00"))
    clock.nudge(-3600)
    assert int(clock.seconds) == parse_hhmm("11:00")


def test_nudge_wraps_backwards_past_midnight(clock: SimulationClock) -> None:
    clock.seek(parse_hhmm("00:30"))
    clock.nudge(-3600)
    assert int(clock.seconds) == parse_hhmm("23:30")


def test_speed_change_leaves_live_mode(clock: SimulationClock) -> None:
    clock.set_speed(2.0)
    assert clock.speed == 2.0
    assert not clock.live


def test_speed_of_one_alone_does_not_break_live(clock: SimulationClock) -> None:
    clock.set_speed(1.0)
    assert clock.live


def test_speed_is_clamped_above_zero(clock: SimulationClock) -> None:
    clock.set_speed(-5)
    assert clock.speed > 0


def test_resync_restores_live_defaults(clock: SimulationClock) -> None:
    clock.set_speed(20.0)
    clock.set_running(False)
    clock.seek(0)
    clock.resync()
    assert clock.live and clock.running and clock.speed == 1.0


def test_state_snapshot_reflects_the_clock(clock: SimulationClock) -> None:
    clock.seek(parse_hhmm("07:05"))
    state = clock.state()
    assert state.hhmm == "07:05"
    assert state.hhmmss.startswith("07:05:")


def test_day_advances_at_midnight(clock: SimulationClock) -> None:
    """Crossing 24:00 must roll the date forward and wrap the time."""
    import time
    from datetime import timedelta

    start_day = clock.day
    clock.seek(config.SECONDS_PER_DAY - 1)
    # The clock advances by *real* elapsed time scaled by speed, so the test
    # must let genuine time pass rather than spin the loop.
    clock.set_speed(500.0)

    deadline = time.monotonic() + 2.0
    while clock.day == start_day and time.monotonic() < deadline:
        clock.tick()
        time.sleep(0.005)

    assert clock.day == start_day + timedelta(days=1)
    assert 0 <= clock.seconds < config.SECONDS_PER_DAY
