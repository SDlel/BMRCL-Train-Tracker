"""Shared pytest fixtures.

Qt is forced offscreen before any import so the suite runs headlessly in CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from bmrcl.core.network import Network
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import Timetable, parse_hhmm

PEAK = parse_hhmm("09:00")

NIGHT = parse_hhmm("02:30")


@pytest.fixture(scope="session")
def network() -> Network:
    """The full three-line network, loaded once per session."""
    return Network.load()


@pytest.fixture(scope="session")
def timetable(network: Network) -> Timetable:
    """The parsed timetable, loaded once per session."""
    return Timetable.load(network)


@pytest.fixture
def sim(network: Network, timetable: Timetable) -> Simulation:
    """A paused simulation parked at the weekday morning peak.

    Pausing makes assertions deterministic: the clock cannot advance between
    two reads inside a single test.
    """
    simulation = Simulation(network, timetable)
    simulation.set_day_type("tue_fri")
    simulation.clock.set_running(False)
    simulation.clock.seek(PEAK)
    simulation.rebuild()
    return simulation


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication with the dashboard theme applied."""
    from PySide6.QtWidgets import QApplication

    from bmrcl.app import create_app

    app = QApplication.instance() or create_app([])
    yield app


@pytest.fixture
def window(qapp, sim):
    """A shown MainWindow driven by the paused peak-hour simulation."""
    from bmrcl.ui.main_window import MainWindow

    win = MainWindow(sim)
    win.resize(1600, 900)
    win.show()
    for _ in range(3):
        qapp.processEvents()
    yield win
    win.close()


def pump(qapp, times: int = 3) -> None:
    """Let Qt settle pending layout and paint events."""
    for _ in range(times):
        qapp.processEvents()
