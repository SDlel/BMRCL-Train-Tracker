"""Tests for the terminal turnaround state machine.

The terminal lifecycle is::

    RUNNING -> ARRIVED_TERMINAL -> TURNING -> TERMINATED

``ARRIVED_TERMINAL`` and ``TURNING`` together occupy exactly
``TURNAROUND_SECONDS``. Nothing here should create a scheduled service: the
timetable already supplies departures from both terminals independently.
"""

from __future__ import annotations

import pytest

from bmrcl import config
from bmrcl.core.network import Network
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import Departure, Timetable, parse_hhmm
from bmrcl.core.trains import Phase, RunResolver, run_duration

from .conftest import pump


@pytest.fixture
def resolver_case(network: Network, timetable: Timetable):
    """A full Purple Line run departing at t=0, with its resolver."""
    line = network.line("purple")
    service = next(s for s in timetable.services("purple", "tue_fri") if s.id == "PPL-WFD-FULL")
    departure = Departure(service=service, time=0, trip_index=0)
    hops = abs(line.index_of(service.destination) - line.index_of(service.origin))
    return RunResolver(line), departure, run_duration(hops)


def phase_at(resolver, departure, offset: float):
    state = resolver.resolve(departure, offset)
    return state.phase if state else None


class TestConfiguration:
    def test_default_turnaround_is_five_minutes(self) -> None:
        assert config.TURNAROUND_SECONDS == 300.0

    def test_arrival_window_is_inside_the_turnaround(self) -> None:
        """The arrival period is carved out, never added on top."""
        assert config.TERMINAL_ARRIVAL_SECONDS < config.TURNAROUND_SECONDS

    def test_intermediate_timings_are_untouched(self) -> None:
        assert config.INTER_STATION_SECONDS == 120.0
        assert config.DWELL_SECONDS == 20.0


class TestStateTransitions:
    def test_running_right_up_to_arrival(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        assert phase_at(resolver, departure, total - 1) is Phase.RUNNING

    def test_arrival_enters_the_arrived_state(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        assert phase_at(resolver, departure, total) is Phase.ARRIVED_TERMINAL

    def test_arrived_holds_for_the_configured_window(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        edge = total + config.TERMINAL_ARRIVAL_SECONDS - 0.1
        assert phase_at(resolver, departure, edge) is Phase.ARRIVED_TERMINAL

    def test_turning_begins_when_the_arrival_window_ends(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        edge = total + config.TERMINAL_ARRIVAL_SECONDS
        assert phase_at(resolver, departure, edge) is Phase.TURNING

    def test_turning_holds_until_the_turnaround_ends(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        edge = total + config.TURNAROUND_SECONDS - 0.1
        assert phase_at(resolver, departure, edge) is Phase.TURNING

    def test_terminated_at_the_turnaround_boundary(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        edge = total + config.TURNAROUND_SECONDS
        assert phase_at(resolver, departure, edge) is Phase.TERMINATED

    def test_the_run_eventually_leaves_the_simulation(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        beyond = total + config.TURNAROUND_SECONDS + config.TERMINAL_CLEAR_SECONDS + 1
        assert resolver.resolve(departure, beyond) is None

    def test_departing_needs_a_linked_working(self, resolver_case) -> None:
        """Without a linker the run terminates; DEPARTING requires linkage."""
        resolver, departure, total = resolver_case
        resolver.linker = None
        seen = {
            phase_at(resolver, departure, total + t)
            for t in range(0, int(config.TURNAROUND_SECONDS) + 120)
        }
        assert Phase.DEPARTING not in seen
        assert Phase.TERMINATED in seen


class TestTurnaroundBudget:
    def test_the_two_terminal_states_sum_to_the_turnaround(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        span = int(config.TURNAROUND_SECONDS) + 120
        arrived = sum(
            1
            for t in range(span)
            if phase_at(resolver, departure, total + t) is Phase.ARRIVED_TERMINAL
        )
        turning = sum(
            1 for t in range(span) if phase_at(resolver, departure, total + t) is Phase.TURNING
        )
        assert arrived == pytest.approx(config.TERMINAL_ARRIVAL_SECONDS, abs=1)
        assert arrived + turning == pytest.approx(config.TURNAROUND_SECONDS, abs=1)

    def test_countdown_runs_from_full_to_zero(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        at_arrival = resolver.resolve(departure, total)
        midway = resolver.resolve(departure, total + config.TURNAROUND_SECONDS / 2)
        assert at_arrival.turnaround_remaining == pytest.approx(config.TURNAROUND_SECONDS)
        assert midway.turnaround_remaining == pytest.approx(config.TURNAROUND_SECONDS / 2)

    def test_turnaround_is_configurable(self, resolver_case, monkeypatch) -> None:
        resolver, departure, total = resolver_case
        monkeypatch.setattr(config, "TURNAROUND_SECONDS", 180.0)
        assert phase_at(resolver, departure, total + 179) is Phase.TURNING
        assert phase_at(resolver, departure, total + 180) is Phase.TERMINATED

    def test_a_moving_train_reports_no_turnaround(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        state = resolver.resolve(departure, total / 2)
        assert state.turnaround_remaining == 0.0
        assert not state.at_terminal


class TestNoDuplicateServices:
    """A physical turnaround must never invent a scheduled departure."""

    def test_departure_count_is_unchanged_by_turnaround(self, timetable: Timetable) -> None:
        total = sum(
            len(timetable.plan(line_id, "tue_fri")) for line_id in ("purple", "green", "yellow")
        )
        assert total == timetable.total_departures("tue_fri")

    def test_a_terminating_train_never_reverses_direction(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        running = resolver.resolve(departure, total - 1)
        turning = resolver.resolve(departure, total + 60)
        assert turning.direction == running.direction

    def test_a_terminating_train_stays_at_its_destination(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        for offset in (0, 30, 150, 299):
            state = resolver.resolve(departure, total + offset)
            assert state.position == float(state.destination_index)

    def test_no_departure_eta_from_the_terminating_station(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        state = resolver.resolve(departure, total + 60)
        assert state.departure_eta_to(state.destination_index) is None


class TestPhysicalIdentity:
    def test_every_train_carries_a_physical_id(self, sim: Simulation) -> None:
        for trains in sim.frame.trains.values():
            assert all(t.physical_train_id for t in trains)

    def test_identity_is_stable_through_the_turnaround(self, resolver_case) -> None:
        resolver, departure, total = resolver_case
        ids = {resolver.resolve(departure, total + t).physical_train_id for t in (0, 30, 150, 299)}
        assert len(ids) == 1


class TestTimeControls:
    """Terminal state must derive from simulated time, never frame count."""

    def test_seeking_into_the_turnaround(self, sim: Simulation) -> None:
        sim.clock.seek(parse_hhmm("09:00"))
        first = sim.rebuild()
        sim.clock.seek(parse_hhmm("14:00"))
        sim.rebuild()
        sim.clock.seek(parse_hhmm("09:00"))
        again = sim.rebuild()
        before = {t.run_id: t.phase for ts in first.trains.values() for t in ts}
        after = {t.run_id: t.phase for ts in again.trains.values() for t in ts}
        assert before == after

    def test_pausing_freezes_the_countdown(self, sim: Simulation) -> None:
        sim.clock.seek(parse_hhmm("09:00"))
        sim.clock.set_running(False)
        first = sim.rebuild()
        second = sim.rebuild()
        a = {t.run_id: t.turnaround_remaining for ts in first.trains.values() for t in ts}
        b = {t.run_id: t.turnaround_remaining for ts in second.trains.values() for t in ts}
        assert a == b

    def test_terminal_states_appear_across_the_day(self, sim: Simulation) -> None:
        seen: set[Phase] = set()
        for hhmm in ("06:30", "09:00", "12:00", "17:30", "21:00"):
            sim.clock.seek(parse_hhmm(hhmm))
            frame = sim.rebuild()
            for trains in frame.trains.values():
                seen.update(t.phase for t in trains)
        assert Phase.ARRIVED_TERMINAL in seen or Phase.TURNING in seen
        assert Phase.RUNNING in seen
        assert Phase.DWELL in seen

    def test_last_service_of_the_day_still_terminates(self, sim: Simulation) -> None:
        plan = sim.timetable.plan("yellow", "tue_fri")
        last = plan.departures[-1]
        line = sim.network.line("yellow")
        hops = abs(line.index_of(last.service.destination) - line.index_of(last.service.origin))
        arrival = last.time + run_duration(hops)
        state = RunResolver(line).resolve(last, arrival + 60)
        assert state is not None
        assert state.at_terminal


class TestIntermediateDwellUnchanged:
    def test_dwell_is_still_twenty_seconds(self, resolver_case) -> None:
        resolver, departure, _ = resolver_case
        dwelling = [t for t in range(0, 600) if phase_at(resolver, departure, t) is Phase.DWELL]
        first_run = []
        for t in dwelling:
            if not first_run or t == first_run[-1] + 1:
                first_run.append(t)
            else:
                break
        assert len(first_run) == pytest.approx(config.DWELL_SECONDS, abs=1)

    def test_intermediate_dwell_is_not_a_terminal_state(self, resolver_case) -> None:
        resolver, departure, _ = resolver_case
        state = resolver.resolve(departure, config.INTER_STATION_SECONDS + 5)
        assert state.phase is Phase.DWELL
        assert not state.at_terminal


class TestTerminalStatusBoard:
    def test_terminus_reports_a_status(self, sim: Simulation) -> None:
        sim.clock.seek(parse_hhmm("09:00"))
        sim.rebuild()
        board = sim.board_for(sim.network.line("purple").station("challaghatta"))
        assert board.terminal is not None
        assert board.terminal.label in ("CLEAR", "OCCUPIED", "TURNING")

    def test_through_station_reports_nothing(self, sim: Simulation) -> None:
        board = sim.board_for(sim.network.line("purple").station("indiranagar"))
        assert board.terminal is None

    def test_occupancy_matches_a_turning_train(self, sim: Simulation) -> None:
        line = sim.network.line("purple")
        station = line.station("challaghatta")
        for offset in range(0, 3600, 60):
            sim.clock.seek(parse_hhmm("09:00") + offset)
            sim.rebuild()
            board = sim.board_for(station)
            if board.terminal and board.terminal.occupied:
                assert board.terminal.train is not None
                assert board.terminal.train.destination_index == station.index
                return
        pytest.skip("no terminal occupancy found in the sampled window")


class TestTerminalUi:
    def test_train_panel_shows_turnaround(self, qapp, window) -> None:
        sim = window.simulation
        turning = None
        for offset in range(0, 3600, 30):
            sim.clock.seek(parse_hhmm("09:00") + offset)
            sim.rebuild()
            for trains in sim.frame.trains.values():
                for train in trains:
                    if train.phase is Phase.TURNING:
                        turning = train
                        break
                if turning:
                    break
            if turning:
                break
        if turning is None:
            pytest.skip("no turning train in the sampled window")

        window._on_train_selected(turning)
        pump(qapp)
        panel = window.train_panel
        assert panel.tile_status.value.text() == "Turning around"
        assert panel.facts["turnaround"].isVisible()
        assert "remaining" in panel.facts["turnaround"].value.text()
        # Either a real onward working from the timetable, or an honest
        # admission that this vehicle has none. Never an invented service.
        onward = panel.facts["next_working"].value.text()
        assert onward == "Not assigned" or " to " in onward

    def test_turnaround_rows_hidden_for_a_moving_train(self, qapp, window) -> None:
        sim = window.simulation
        running = next(
            t for ts in sim.frame.trains.values() for t in ts if t.phase is Phase.RUNNING
        )
        window._on_train_selected(running)
        pump(qapp)
        assert not window.train_panel.facts["turnaround"].isVisible()

    def test_station_panel_shows_terminal_status(self, qapp, window) -> None:
        line = window.simulation.network.line("purple")
        window._select_station(line.station("challaghatta"))
        pump(qapp)
        assert window.station_panel.terminal_value.isVisible()
        assert window.station_panel.terminal_value.text() in ("CLEAR", "OCCUPIED", "TURNING")

    def test_station_panel_hides_terminal_status_mid_line(self, qapp, window) -> None:
        line = window.simulation.network.line("purple")
        window._select_station(line.station("indiranagar"))
        pump(qapp)
        assert not window.station_panel.terminal_value.isVisible()
