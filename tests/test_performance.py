"""Performance guards.

These assert the frame budget rather than a precise timing, so they stay
meaningful on slower CI hardware while still catching a real regression.
"""

from __future__ import annotations

import time

import pytest

from bmrcl import config
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import parse_hhmm

from .conftest import pump

FRAME_BUDGET_MS = 1000.0 / config.TARGET_FPS

#: CI runners are slower and share cores, so allow generous headroom.
CI_TOLERANCE = 3.0


def _average_ms(action, iterations: int) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        action()
    return (time.perf_counter() - start) / iterations * 1000.0


def test_simulation_rebuild_is_cheap(sim: Simulation) -> None:
    elapsed = _average_ms(sim.rebuild, 120)
    assert elapsed < 8.0, f"{elapsed:.2f} ms per rebuild"


def test_snapshot_scales_to_the_whole_network(sim: Simulation) -> None:
    elapsed = _average_ms(lambda: sim.trains.snapshot(sim.clock.seconds, "tue_fri"), 120)
    assert elapsed < 8.0, f"{elapsed:.2f} ms per snapshot"


@pytest.mark.parametrize("tab", [0, 1, 2, 3])
def test_frame_loop_meets_the_budget(qapp, window, tab: int) -> None:
    window.tabs.setCurrentIndex(tab)
    pump(qapp)
    for _ in range(20):
        window._on_frame()
        qapp.processEvents()

    def frame() -> None:
        window._on_frame()
        qapp.processEvents()

    elapsed = _average_ms(frame, 60)
    budget = FRAME_BUDGET_MS * CI_TOLERANCE
    assert elapsed < budget, f"tab {tab}: {elapsed:.2f} ms exceeds {budget:.1f} ms"


def test_a_line_tab_is_no_slower_than_the_overview(qapp, window) -> None:
    def measure(index: int) -> float:
        window.tabs.setCurrentIndex(index)
        pump(qapp)
        for _ in range(15):
            window._on_frame()
            qapp.processEvents()

        def frame() -> None:
            window._on_frame()
            qapp.processEvents()

        return _average_ms(frame, 45)

    overview = measure(0)
    single = measure(3)
    assert single <= overview * 1.35, f"line tab {single:.2f} ms vs overview {overview:.2f} ms"


def test_peak_hour_is_the_worst_case(sim: Simulation) -> None:
    """Sanity-check that the fixture really is testing the busy period."""
    sim.clock.seek(parse_hhmm("09:00"))
    peak = sim.rebuild().total_active
    sim.clock.seek(parse_hhmm("14:00"))
    midday = sim.rebuild().total_active
    assert peak > midday
