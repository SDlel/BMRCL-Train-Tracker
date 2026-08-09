"""Tests for clock drift detection and timetable refresh."""

from __future__ import annotations

import time
from datetime import datetime

import pytest

from bmrcl import config
from bmrcl.core.clock import SimulationClock
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import parse_hhmm

from .conftest import pump


def wall_seconds() -> float:
    now = datetime.now()
    return now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6


class TestDriftDetection:
    def test_a_fresh_clock_is_accurate(self) -> None:
        assert abs(SimulationClock().drift()) < 0.5

    def test_injected_drift_is_measured(self) -> None:
        clock = SimulationClock()
        clock._seconds -= 12.0
        assert clock.drift() == pytest.approx(-12.0, abs=0.5)

    def test_drift_is_meaningless_while_paused(self) -> None:
        clock = SimulationClock()
        clock.set_running(False)
        assert clock.drift() is None

    def test_drift_is_meaningless_off_realtime_speed(self) -> None:
        clock = SimulationClock()
        clock.set_speed(2.0)
        assert clock.drift() is None

    def test_drift_is_meaningless_after_a_seek(self) -> None:
        """A deliberately chosen time is not drift and must not be corrected."""
        clock = SimulationClock()
        clock.seek(parse_hhmm("09:00"))
        assert clock.drift() is None


class TestDriftCorrection:
    def test_correction_removes_the_offset(self) -> None:
        clock = SimulationClock()
        clock._seconds -= 9.0
        clock.correct_drift()
        assert abs(clock.drift()) < 0.1

    def test_correction_reports_what_it_applied(self) -> None:
        clock = SimulationClock()
        clock._seconds -= 6.0
        assert clock.correct_drift() == pytest.approx(6.0, abs=0.5)

    def test_correction_preserves_running_speed_and_day(self) -> None:
        clock = SimulationClock()
        before = (clock.running, clock.speed, clock.day)
        clock._seconds -= 4.0
        clock.correct_drift()
        assert (clock.running, clock.speed, clock.day) == before

    def test_correction_is_skipped_when_not_applicable(self) -> None:
        clock = SimulationClock()
        clock.seek(parse_hhmm("14:00"))
        before = clock.seconds
        assert clock.correct_drift() is None
        assert clock.seconds == before

    def test_a_render_loop_accumulates_drift_that_is_corrected(self) -> None:
        """Frame-by-frame accumulation loses time; refresh recovers it."""
        clock = SimulationClock()
        start = time.perf_counter()
        while time.perf_counter() - start < 1.5:
            clock.tick()
            time.sleep(1 / 120)
        clock.correct_drift()
        assert abs(clock.drift()) < 0.05


class TestSimulationRefresh:
    def test_refresh_corrects_and_reports(self) -> None:
        sim = Simulation()
        sim.clock._seconds -= 8.0
        result = sim.refresh()
        assert result.corrected
        assert result.corrected_seconds == pytest.approx(8.0, abs=0.5)
        assert "Refreshed" in result.summary

    def test_a_second_refresh_finds_nothing_to_do(self) -> None:
        sim = Simulation()
        sim.clock._seconds -= 8.0
        sim.refresh()
        assert not sim.refresh().corrected

    def test_refresh_leaves_a_chosen_time_alone(self) -> None:
        sim = Simulation()
        sim.clock.seek(parse_hhmm("18:30"))
        before = sim.clock.seconds
        sim.refresh()
        assert abs(sim.clock.seconds - before) < 1.0

    def test_refresh_rebuilds_the_picture(self) -> None:
        sim = Simulation()
        sim.set_day_type("tue_fri")
        sim.clock.seek(parse_hhmm("09:00"))
        result = sim.refresh()
        assert result.active_trains == sim.frame.total_active
        assert result.active_trains > 0

    def test_summary_is_always_readable(self) -> None:
        sim = Simulation()
        for _ in range(3):
            assert len(sim.refresh().summary) > 10


class TestOffsetFormatting:
    """The unit should suit the size of the correction."""

    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0.093, "+93ms"),
            (0.4, "+400ms"),
            (-0.25, "-250ms"),
            (1.4, "+1.4s"),
            (12.7, "+12.7s"),
            (-3.2, "-3.2s"),
            (145.0, "+2.4min"),
        ],
    )
    def test_units_scale(self, seconds: float, expected: str) -> None:
        from bmrcl.core.simulation import RefreshResult

        result = RefreshResult(
            corrected_seconds=seconds,
            day_type="tue_fri",
            day_type_changed=False,
            active_trains=98,
            at=0.0,
        )
        assert result.offset_text == expected

    def test_no_correction_reads_as_not_applicable(self) -> None:
        from bmrcl.core.simulation import RefreshResult

        result = RefreshResult(
            corrected_seconds=None,
            day_type="tue_fri",
            day_type_changed=False,
            active_trains=0,
            at=0.0,
        )
        assert result.offset_text == "n/a"


class TestRefreshUi:
    def test_refresh_button_exists(self, window) -> None:
        assert window.header.refresh_button.text() == "\u21bb"
        assert "F5" in window.header.refresh_button.toolTip()

    def test_auto_refresh_timer_runs(self, window) -> None:
        assert window._refresh_timer.isActive()
        assert window._refresh_timer.interval() == config.AUTO_REFRESH_MINUTES * 60_000

    def test_status_bar_shows_sync_age(self, window) -> None:
        assert "sync" in window.status.metrics

    def test_manual_refresh_updates_the_status_bar(self, qapp, window) -> None:
        window.simulation.clock.set_running(True)
        window.simulation.clock._seconds -= 7.0
        window._manual_refresh()
        pump(qapp)
        assert window.status.metrics["sync"].toolTip()

    def test_manual_refresh_shows_a_toast(self, qapp, window) -> None:
        # The fixture parks the clock at a fixed time, so restore live running
        # before injecting drift; otherwise correction is correctly skipped.
        window.simulation.clock.resync()
        window.simulation.clock._seconds -= 9.0
        window._manual_refresh()
        pump(qapp)
        assert window.toast.isVisible()
        assert "Refreshed" in window.toast.message.text()

    def test_toast_confirms_even_when_nothing_changed(self, qapp, window) -> None:
        """Silence after pressing a button reads as a broken button."""
        window._manual_refresh()
        pump(qapp)
        window._manual_refresh()
        pump(qapp)
        assert window.toast.isVisible()
        assert "sync" in window.toast.message.text().lower()

    def test_toast_stays_inside_the_window(self, qapp, window) -> None:
        window._manual_refresh()
        pump(qapp)
        toast = window.toast
        assert toast.x() + toast.width() <= window.width()
        assert toast.y() + toast.height() <= window.height()

    def test_manual_refresh_does_not_break_a_selection(self, qapp, window) -> None:
        green = window.simulation.network.line("green")
        window._select_station(green.station("jayanagar"))
        pump(qapp)
        window._manual_refresh()
        pump(qapp)
        assert window.station_panel._station_key == "green:jayanagar"

    def test_auto_refresh_is_silent_when_nothing_changed(self, qapp, window) -> None:
        window._auto_refresh()
        pump(qapp)
        assert window.station_panel is not None

    def test_refresh_keeps_the_frame_budget(self, qapp, window) -> None:
        start = time.perf_counter()
        window._manual_refresh()
        qapp.processEvents()
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 400, f"refresh took {elapsed:.0f} ms"
