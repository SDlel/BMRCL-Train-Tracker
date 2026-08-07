"""Tests for the dashboard window: tabs, docks, header layout and controls."""

from __future__ import annotations

import pytest

from bmrcl.core.timetable import parse_hhmm

from .conftest import pump

WINDOW_WIDTHS = (1100, 1280, 1400, 1600, 1920)
HEADER_CONTROLS = ("play_button", "time_edit", "day_combo", "jump_button", "live_button")


def _clipped(header) -> list[str]:
    """Names of any header control whose content does not fit."""
    bad = [b.text() for b in header._speed_buttons.values() if b.sizeHint().width() > b.width()]
    bad += [
        name
        for name in HEADER_CONTROLS
        if getattr(header, name).sizeHint().width() > getattr(header, name).width()
    ]
    return bad


class TestHeaderLayout:
    @pytest.mark.parametrize("width", WINDOW_WIDTHS)
    def test_nothing_is_clipped(self, qapp, window, width: int) -> None:
        window.resize(width, 950)
        pump(qapp)
        assert _clipped(window.header) == []

    def test_speed_buttons_share_one_width(self, window) -> None:
        widths = {b.width() for b in window.header._speed_buttons.values()}
        assert len(widths) == 1

    @pytest.mark.parametrize("speed", [0.5, 20.0])
    def test_awkward_speed_labels_fit(self, window, speed: float) -> None:
        button = window.header._speed_buttons[speed]
        assert button.sizeHint().width() <= button.width()

    def test_toggle_does_not_resize_the_play_button(self, window) -> None:
        button = window.header.play_button
        before = button.width()
        window.header.set_running(False)
        assert button.width() == before

    def test_bars_span_the_whole_window(self, qapp, window) -> None:
        window.resize(1920, 950)
        pump(qapp)
        assert window.header.width() == window.width()
        assert window.status.width() == window.width()

    def test_branding_collapses_before_controls(self, qapp, window) -> None:
        window.resize(1100, 950)
        pump(qapp)
        assert not window.header.brand_title.isVisible()
        assert _clipped(window.header) == []

    def test_branding_returns_when_there_is_room(self, qapp, window) -> None:
        window.resize(1920, 950)
        pump(qapp)
        assert window.header.brand_title.isVisible()


class TestTabs:
    def test_one_overview_plus_one_per_line(self, window) -> None:
        assert window.tabs.count() == 4

    def test_labels_are_full_line_names(self, window) -> None:
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert labels == ["Network", "Purple Line", "Green Line", "Yellow Line"]

    def test_no_abbreviations(self, window) -> None:
        labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
        assert not {"PPL", "GRN", "YLW"} & set(labels)

    def test_every_tab_has_a_tooltip(self, window) -> None:
        assert all(window.tabs.tabToolTip(i) for i in range(window.tabs.count()))

    def test_overview_is_unfiltered(self, qapp, window) -> None:
        window.tabs.setCurrentIndex(0)
        pump(qapp)
        assert window.active_line_ids is None
        assert len(window.panel.network) == 3

    @pytest.mark.parametrize(("index", "line_id"), [(1, "purple"), (2, "green"), (3, "yellow")])
    def test_line_tab_scopes_everything(self, qapp, window, index: int, line_id: str) -> None:
        window.tabs.setCurrentIndex(index)
        pump(qapp)
        window._refresh_slow()

        assert window.active_line_ids == [line_id]
        assert len(window.panel.network) == 1

        model = window.train_table.model_
        assert model.rowCount() == len(window.simulation.frame.trains[line_id])
        seen = {model.train_at(r).line_id for r in range(model.rowCount())}
        assert seen <= {line_id}

        visible = [lid for lid, c in window.line_panel.cards.items() if c.isVisible()]
        assert visible == [line_id]

    def test_returning_to_overview_restores_everything(self, qapp, window) -> None:
        window.tabs.setCurrentIndex(2)
        pump(qapp)
        window.tabs.setCurrentIndex(0)
        pump(qapp)
        window._refresh_slow()
        assert window.train_table.model_.rowCount() == window.simulation.frame.total_active

    def test_hidden_tabs_are_not_rendered(self, qapp, window) -> None:
        window._on_frame()
        pump(qapp)
        dirty = [p for p in window.panels if p is not window.panel and p.is_dirty]
        assert len(dirty) == 3

    def test_each_tab_keeps_its_own_zoom(self, qapp, window) -> None:
        window.tabs.setCurrentIndex(1)
        pump(qapp)
        window.view.set_zoom(1.5)
        first = window.panel.zoom
        window.tabs.setCurrentIndex(2)
        pump(qapp)
        assert window.panel.zoom != first


class TestStationPanel:
    def test_starts_empty(self, window) -> None:
        assert window.station_panel._station_key is None

    def test_ordinary_station_shows_two_facts(self, qapp, window) -> None:
        green = window.simulation.network.line("green")
        window._select_station(green.station("jayanagar"))
        pump(qapp)
        panel = window.station_panel
        assert panel.tile_arrival.value.text() != "--"
        assert panel.tile_departure.value.text() != "--"
        assert not panel.tile_loop.isVisible()

    def test_short_turn_station_shows_three(self, qapp, window) -> None:
        green = window.simulation.network.line("green")
        window._select_station(green.station("yelachenahalli"))
        pump(qapp)
        panel = window.station_panel
        assert panel.tile_arrival.value.text() != "--"
        assert panel.tile_departure.value.text() != "--"
        assert panel.tile_loop.isVisible()
        assert panel.tile_loop.value.text() != "--"
        assert len(panel.loop_note.text()) > 20

    def test_selection_is_highlighted_in_every_relevant_tab(self, qapp, window) -> None:
        green = window.simulation.network.line("green")
        station = green.station("yelachenahalli")
        window._select_station(station)
        pump(qapp)
        for panel in window.panels:
            if panel.has_line("green"):
                item = panel.scene.line_item("green").station_item(station.index)
                assert item._highlight

    def test_countdown_ticks_down(self, qapp, window) -> None:
        sim = window.simulation
        green = sim.network.line("green")
        window._select_station(green.station("jayanagar"))
        pump(qapp)
        before = window.station_panel.tile_arrival.value.text()
        sim.clock.seek(parse_hhmm("09:00") + 40)
        sim.rebuild()
        window._refresh_station_panel()
        assert window.station_panel.tile_arrival.value.text() != before

    def test_survives_a_closed_railway(self, qapp, window) -> None:
        sim = window.simulation
        window._select_station(sim.network.line("green").station("jayanagar"))
        sim.clock.seek(parse_hhmm("03:00"))
        sim.rebuild()
        window._refresh_station_panel()
        assert window.station_panel.tile_arrival.value.text() in ("--", "due")


class TestTransportControls:
    def test_pause_and_resume(self, window) -> None:
        # The fixture hands over a paused clock, so start from a known state.
        window.simulation.clock.set_running(True)
        window._toggle_running()
        assert not window.simulation.clock.running
        window._toggle_running()
        assert window.simulation.clock.running

    @pytest.mark.parametrize("speed", [0.5, 1.0, 2.0, 5.0, 20.0])
    def test_speed_selection(self, window, speed: float) -> None:
        window._set_speed(speed)
        assert window.simulation.clock.speed == speed

    def test_seeking(self, window) -> None:
        window._seek(parse_hhmm("18:30"))
        assert int(window.simulation.clock.seconds) == parse_hhmm("18:30")
        assert window.simulation.frame.total_active > 0

    def test_day_type_override(self, window) -> None:
        window._set_day_type("sunday")
        assert window.simulation.day_type == "sunday"
        window._set_day_type(None)
        assert not window.simulation.day_type_is_overridden

    def test_fit_produces_a_sane_zoom(self, qapp, window) -> None:
        window._fit()
        pump(qapp)
        assert 0.05 < window.view.zoom < 4.0


def test_scene_builds_all_lines(window) -> None:
    assert len(window.panels[0].scene.line_items) == 3


def test_roster_is_populated(window) -> None:
    assert window.train_table.model_.rowCount() > 0


def test_station_tooltip_is_generated(window) -> None:
    item = window.panels[0].scene.line_item("purple").station_item(18)
    item.refresh_tooltip()
    assert "Mahatma Gandhi Road" in item.toolTip()
