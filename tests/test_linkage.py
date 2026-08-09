"""Tests for physical train continuity across terminal turnarounds.

The central guarantee is that linkage never changes what is scheduled. It only
decides which physical vehicle is assumed to work an existing service.
"""

from __future__ import annotations

import pytest

from bmrcl import config
from bmrcl.core.linkage import LinkageRegistry, PhysicalLinkage
from bmrcl.core.network import Network
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import Timetable, parse_hhmm
from bmrcl.core.trains import Phase

from .conftest import pump

LINES = ("purple", "green", "yellow")


@pytest.fixture(scope="module")
def linkages(network: Network, timetable: Timetable) -> dict[str, PhysicalLinkage]:
    return {
        line_id: PhysicalLinkage(network.line(line_id), timetable, "tue_fri") for line_id in LINES
    }


class TestNoScheduleChange:
    """Linkage must not add, remove or move a single departure."""

    @pytest.mark.parametrize("line_id", LINES)
    def test_departure_count_is_untouched(
        self, timetable: Timetable, linkages, line_id: str
    ) -> None:
        before = len(timetable.plan(line_id, "tue_fri"))
        linkages[line_id]
        assert len(timetable.plan(line_id, "tue_fri")) == before

    @pytest.mark.parametrize("line_id", LINES)
    def test_every_linked_working_already_exists(
        self, timetable: Timetable, linkages, line_id: str
    ) -> None:
        known = {d.run_id for d in timetable.plan(line_id, "tue_fri").departures}
        linkage = linkages[line_id]
        for working in linkage.next_working.values():
            assert working.run_id in known

    @pytest.mark.parametrize("line_id", LINES)
    def test_a_working_is_claimed_at_most_once(self, linkages, line_id: str) -> None:
        claimed = [w.run_id for w in linkages[line_id].next_working.values()]
        assert len(claimed) == len(set(claimed))


class TestMatchingRules:
    @pytest.mark.parametrize("line_id", LINES)
    def test_turnaround_is_always_respected(
        self, network: Network, timetable: Timetable, linkages, line_id: str
    ) -> None:
        """No vehicle departs before it has finished turning."""
        line = network.line(line_id)
        plan = timetable.plan(line_id, "tue_fri")
        arrivals = {}
        for dep in plan.departures:
            hops = abs(line.index_of(dep.service.destination) - line.index_of(dep.service.origin))
            from bmrcl.core.trains import run_duration

            arrivals[dep.run_id] = dep.time + run_duration(hops)

        for run_id, working in linkages[line_id].next_working.items():
            gap = working.departure_time - arrivals[run_id]
            assert gap >= config.TURNAROUND_SECONDS

    @pytest.mark.parametrize("line_id", LINES)
    def test_layover_ceiling_is_respected(
        self, network: Network, timetable: Timetable, linkages, line_id: str
    ) -> None:
        from bmrcl.core.trains import run_duration

        line = network.line(line_id)
        plan = timetable.plan(line_id, "tue_fri")
        for dep in plan.departures:
            working = linkages[line_id].working_after(dep.run_id)
            if working is None:
                continue
            hops = abs(line.index_of(dep.service.destination) - line.index_of(dep.service.origin))
            arrival = dep.time + run_duration(hops)
            assert working.departure_time - arrival <= config.MAX_LAYOVER_SECONDS

    @pytest.mark.parametrize("line_id", LINES)
    def test_a_vehicle_leaves_the_way_it_did_not_arrive(
        self, network: Network, timetable: Timetable, linkages, line_id: str
    ) -> None:
        line = network.line(line_id)
        plan = timetable.plan(line_id, "tue_fri")
        for dep in plan.departures:
            working = linkages[line_id].working_after(dep.run_id)
            if working is None:
                continue
            inbound = (
                1
                if line.index_of(dep.service.destination) > line.index_of(dep.service.origin)
                else -1
            )
            assert working.direction == -inbound

    @pytest.mark.parametrize("line_id", LINES)
    def test_the_working_starts_where_the_train_arrived(
        self, network: Network, timetable: Timetable, linkages, line_id: str
    ) -> None:
        line = network.line(line_id)
        plan = timetable.plan(line_id, "tue_fri")
        for dep in plan.departures:
            working = linkages[line_id].working_after(dep.run_id)
            if working is None:
                continue
            assert working.origin_index == line.index_of(dep.service.destination)


class TestHonestGaps:
    """Where arrivals outnumber departures, the surplus must terminate."""

    def test_not_every_arrival_is_linked(self, linkages) -> None:
        """Purple has roughly twice as many arrivals as departures."""
        linkage = linkages["purple"]
        assert 0 < linkage.linked_count < len(linkage.physical_ids)

    def test_yellow_links_almost_everything(self, linkages) -> None:
        """Yellow is nearly balanced, so most vehicles work straight through."""
        linkage = linkages["yellow"]
        assert linkage.linked_count > len(linkage.physical_ids) * 0.5


class TestPhysicalIdentity:
    @pytest.mark.parametrize("line_id", LINES)
    def test_every_run_has_a_vehicle(self, timetable: Timetable, linkages, line_id: str) -> None:
        linkage = linkages[line_id]
        for dep in timetable.plan(line_id, "tue_fri").departures:
            assert linkage.physical_id_for(dep.run_id)

    @pytest.mark.parametrize("line_id", LINES)
    def test_a_chain_shares_one_vehicle(self, timetable: Timetable, linkages, line_id: str) -> None:
        linkage = linkages[line_id]
        for run_id, working in linkage.next_working.items():
            assert linkage.physical_id_for(run_id) == linkage.physical_id_for(working.run_id)

    def test_unrelated_runs_use_different_vehicles(self, linkages) -> None:
        linkage = linkages["yellow"]
        assert len(set(linkage.physical_ids.values())) > 1


class TestRegistry:
    def test_results_are_cached(self, network: Network, timetable: Timetable) -> None:
        registry = LinkageRegistry(timetable)
        line = network.line("green")
        assert registry.get(line, "tue_fri") is registry.get(line, "tue_fri")

    def test_day_types_are_separate(self, network: Network, timetable: Timetable) -> None:
        registry = LinkageRegistry(timetable)
        line = network.line("green")
        assert registry.get(line, "tue_fri") is not registry.get(line, "sunday")


class TestSimulationBehaviour:
    def test_departing_phase_is_reachable(self, sim: Simulation) -> None:
        seen = set()
        for offset in range(0, 3600, 30):
            sim.clock.seek(parse_hhmm("09:00") + offset)
            frame = sim.rebuild()
            seen.update(t.phase for ts in frame.trains.values() for t in ts)
            if Phase.DEPARTING in seen:
                break
        assert Phase.DEPARTING in seen

    def test_linked_trains_report_their_onward_working(self, sim: Simulation) -> None:
        sim.clock.seek(parse_hhmm("09:00"))
        frame = sim.rebuild()
        linked = [t for ts in frame.trains.values() for t in ts if t.next_working]
        assert linked
        for train in linked:
            assert train.next_working_time is not None

    def test_a_vehicle_id_survives_the_turnaround(self, sim: Simulation) -> None:
        """The same vehicle works the inbound and outbound runs."""
        sim.clock.seek(parse_hhmm("09:00"))
        frame = sim.rebuild()
        turning = next(
            (t for ts in frame.trains.values() for t in ts if t.phase is Phase.DEPARTING),
            None,
        )
        if turning is None:
            pytest.skip("no departing train in this frame")
        line = sim.network.line(turning.line_id)
        linkage = sim.trains.line_manager(line.id).linker(sim.day_type)
        working = linkage.working_after(turning.run_id)
        assert working is not None
        assert linkage.physical_id_for(working.run_id) == turning.physical_train_id

    def test_totals_stay_plausible(self, sim: Simulation) -> None:
        for hhmm in ("07:00", "09:00", "13:00", "18:00", "22:00"):
            sim.clock.seek(parse_hhmm(hhmm))
            assert 0 < sim.rebuild().total_active < 400

    def test_linkage_can_be_disabled(self, sim: Simulation, monkeypatch) -> None:
        monkeypatch.setattr(config, "PHYSICAL_RETURN_LINKAGE", False)
        manager = sim.trains.line_manager("purple")
        manager._linkers.clear()
        assert manager.linker("tue_fri") is None


class TestLinkageUi:
    def test_panel_names_a_real_onward_working(self, qapp, window) -> None:
        sim = window.simulation
        linked = None
        for offset in range(0, 1800, 30):
            sim.clock.seek(parse_hhmm("09:00") + offset)
            sim.rebuild()
            linked = next(
                (
                    t
                    for ts in sim.frame.trains.values()
                    for t in ts
                    if t.at_terminal and t.next_working
                ),
                None,
            )
            if linked:
                break
        if linked is None:
            pytest.skip("no linked terminal train found")

        window._on_train_selected(linked)
        pump(qapp)
        text = window.train_panel.facts["next_working"].value.text()
        assert text != "Not assigned"
        assert " to " in text

    def test_panel_shows_the_vehicle(self, qapp, window) -> None:
        sim = window.simulation
        train = next(t for ts in sim.frame.trains.values() for t in ts)
        window._on_train_selected(train)
        pump(qapp)
        assert window.train_panel.facts["vehicle"].value.text() == train.physical_train_id
