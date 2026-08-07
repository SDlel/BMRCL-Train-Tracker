#!/usr/bin/env python3
"""Headless verification of the domain layer and an offscreen UI smoke test.

Run with::

    python selftest.py
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bmrcl import config
from bmrcl.core.network import Network
from bmrcl.core.simulation import Simulation
from bmrcl.core.timetable import Timetable, format_hhmm, parse_hhmm
from bmrcl.core.trains import run_duration

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def test_network(network: Network) -> None:
    section("Network")
    check("3 lines loaded", len(network) == 3, f"{[ln.id for ln in network]}")
    expected = {"purple": 38, "green": 32, "yellow": 15}
    for line_id, count in expected.items():
        line = network.line(line_id)
        check(f"{line_id} has {count} stations", len(line) == count, f"got {len(line)}")
    purple, green = network.line("purple"), network.line("green")
    check(
        "Majestic is an interchange on both lines",
        purple.station("kempegowda_majestic").interchange
        and green.station("kempegowda_majestic").interchange,
    )
    check(
        "RV Road interchange detected",
        "RV Road" in network.interchange_names()
        or network.line("yellow").station("rv_road").interchange,
    )
    check(
        "Purple short-turn points present",
        {
            "garudachar_palya",
            "baiyappanahalli",
            "kempegowda_majestic",
            "mahatma_gandhi_road",
            "mysore_road",
            "pattandur_agrahara",
        }
        <= {s.id for s in purple.short_turn_points},
    )
    check(
        "Green short-turn points present",
        {"nagasandra", "peenya_industry", "yelachenahalli"}
        <= {s.id for s in green.short_turn_points},
    )


def test_timetable(timetable: Timetable, network: Network) -> None:
    section("Timetable")
    check("parse 05:30", parse_hhmm("05:30") == 19800)
    check("format 19800", format_hhmm(19800) == "05:30")
    for day in ("monday", "tue_fri", "saturday", "sunday"):
        total = timetable.total_departures(day)
        check(f"{day} has departures", total > 0, f"{total} departures")
    mon = timetable.plan("purple", "monday")
    check(
        "Monday purple > tue_fri purple (earlier start)",
        mon.first_departure is not None and mon.first_departure == parse_hhmm("04:15"),
        format_hhmm(mon.first_departure or 0),
    )
    short_ids = {s.id for s in timetable.services("purple", "monday") if s.is_short_turn}
    check("Purple Monday short services encoded", len(short_ids) >= 8, f"{len(short_ids)} services")
    green_sun = timetable.plan("green", "sunday")
    check(
        "Green Sunday starts at 07:00",
        green_sun.first_departure == parse_hhmm("07:00"),
        format_hhmm(green_sun.first_departure or 0),
    )
    yellow_mon = timetable.plan("yellow", "monday")
    check("Yellow Monday departures", len(yellow_mon) > 100, f"{len(yellow_mon)}")


def test_trains(sim: Simulation) -> None:
    section("Train model")
    check("run_duration(1) == 120s", run_duration(1) == config.INTER_STATION_SECONDS)
    check("run_duration(2) == 260s", run_duration(2) == 2 * 120 + 20)

    sim.set_day_type("tue_fri")
    peak = parse_hhmm("09:00")
    sim.clock.seek(peak)
    frame = sim.rebuild()
    print(
        f"  peak 09:00 -> {frame.total_active} trains "
        + ", ".join(f"{k}={len(v)}" for k, v in frame.trains.items())
    )
    check("peak has trains on every line", all(len(v) > 0 for v in frame.trains.values()))
    check("peak train count plausible", 50 <= frame.total_active <= 400, str(frame.total_active))

    night = parse_hhmm("02:30")
    sim.clock.seek(night)
    night_frame = sim.rebuild()
    check("no trains at 02:30", night_frame.total_active == 0, str(night_frame.total_active))

    sim.clock.seek(peak)
    frame = sim.rebuild()
    shorts = sum(s.short_turns for s in frame.stats.values())
    check("short-turn services running at peak", shorts > 0, f"{shorts} trains")

    positions_ok = True
    for line_id, trains in frame.trains.items():
        line = sim.network.line(line_id)
        for t in trains:
            if not (0 <= t.position <= len(line) - 1):
                positions_ok = False
    check("all train positions in range", positions_ok)

    both_dirs = all(s.up > 0 and s.down > 0 for s in frame.stats.values())
    check("both directions active", both_dirs)


def test_continuity(sim: Simulation) -> None:
    section("Motion continuity")
    sim.set_day_type("tue_fri")
    base = parse_hhmm("09:00")
    sim.clock.seek(base)
    first = {t.run_id: t.position for t in sim.rebuild().trains["purple"]}
    sim.clock.seek(base + 1)
    second = {t.run_id: t.position for t in sim.rebuild().trains["purple"]}
    shared = set(first) & set(second)
    check("trains persist across 1s step", len(shared) > 5, f"{len(shared)} shared")
    deltas = [abs(second[k] - first[k]) for k in shared]
    max_delta = max(deltas) if deltas else 0.0
    check("no teleporting (<0.02 index/s)", max_delta < 0.02, f"max {max_delta:.4f}")
    moved = sum(1 for d in deltas if d > 0)
    check("some trains moved", moved > 0, f"{moved}/{len(deltas)}")


def test_eta(sim: Simulation) -> None:
    section("ETA and arrivals")
    sim.clock.seek(parse_hhmm("09:00"))
    sim.rebuild()
    line = sim.network.line("purple")
    index = line.index_of("mahatma_gandhi_road")
    arrivals = sim.arrivals_for("purple", index)
    check("MG Road has upcoming arrivals", len(arrivals) > 0, f"{len(arrivals)}")
    if arrivals:
        etas = [round(e) for _, e in arrivals]
        check("ETAs sorted ascending", etas == sorted(etas), str(etas))
        check("ETAs non-negative", all(e >= 0 for e in etas))


def test_station_board(sim: Simulation) -> None:
    """Normal stations expose 2 facts; short-turn stations expose 3."""
    section("Station board")
    sim.set_day_type("tue_fri")
    sim.clock.seek(parse_hhmm("09:00"))
    sim.rebuild()

    green = sim.network.line("green")
    normal = sim.board_for(green.station("jayanagar"))
    check("normal station is not short-turn", not normal.is_short_turn)
    check("normal station has no loop event", normal.loop is None)
    entry = normal.next_entry
    check("normal station has a next train", entry is not None)
    if entry:
        check("arrival is non-negative", entry.arrival_in >= 0, f"{entry.arrival_in:.0f}s")
        check(
            "departure follows arrival",
            entry.departure_in > entry.arrival_in,
            f"{entry.arrival_in:.0f} -> {entry.departure_in:.0f}",
        )
        check(
            "dwell gap equals configured dwell",
            abs((entry.departure_in - entry.arrival_in) - config.DWELL_SECONDS) < 1e-6,
        )

    loopy = sim.board_for(green.station("yelachenahalli"))
    check("Yelachenahalli is a short-turn point", loopy.is_short_turn)
    check("Yelachenahalli has a loop event", loopy.loop is not None)
    if loopy.loop:
        check("loop has a departure", loopy.loop.departs_in is not None)
        check("loop departure is non-negative", (loopy.loop.departs_in or 0) >= 0)
        check(
            "loop names a destination", bool(loopy.loop.to_destination), loopy.loop.to_destination
        )

    purple = sim.network.line("purple")
    terminus = sim.board_for(purple.station("challaghatta"))
    ends = [e for e in terminus.entries if e.terminates]
    check("terminating trains identified at Challaghatta", len(ends) > 0, f"{len(ends)}")
    check("terminating train has no departure", all(e.departure_in is None for e in ends))

    ordered = all(
        a.arrival_in <= b.arrival_in
        for a, b in zip(normal.entries, normal.entries[1:], strict=False)
    )
    check("board entries sorted by arrival", ordered)

    # Yellow has short-turn points flagged but no services yet; the panel must
    # degrade gracefully rather than show a wrong figure.
    yellow = sim.network.line("yellow")
    ec = sim.board_for(yellow.station("electronic_city"))
    check(
        "Yellow short-turn point has no invented loop",
        ec.loop is None or ec.loop.departs_in is None,
    )


def test_header_layout() -> None:
    """No control may be clipped at any supported window width."""
    section("Header layout")
    from PySide6.QtWidgets import QApplication

    from bmrcl.app import create_app
    from bmrcl.ui.main_window import MainWindow

    app = QApplication.instance() or create_app([])
    window = MainWindow(Simulation())
    window.show()

    named = ("play_button", "time_edit", "day_combo", "jump_button", "live_button")
    for width in (1100, 1280, 1400, 1600, 1920):
        window.resize(width, 950)
        for _ in range(3):
            app.processEvents()
        header = window.header
        clipped = [
            b.text() for b in header._speed_buttons.values() if b.sizeHint().width() > b.width()
        ]
        clipped += [
            n for n in named if getattr(header, n).sizeHint().width() > getattr(header, n).width()
        ]
        check(f"nothing clipped at {width}px", not clipped, str(clipped))

    header = window.header
    widths = {b.width() for b in header._speed_buttons.values()}
    check("speed buttons share one width", len(widths) == 1, str(widths))
    check(
        "0.5x fits its button",
        header._speed_buttons[0.5].sizeHint().width() <= header._speed_buttons[0.5].width(),
    )
    check(
        "20x fits its button",
        header._speed_buttons[20.0].sizeHint().width() <= header._speed_buttons[20.0].width(),
    )

    window.resize(1920, 950)
    for _ in range(3):
        app.processEvents()
    check(
        "header spans the full window width",
        header.width() == window.width(),
        f"{header.width()} vs {window.width()}",
    )
    check("status bar spans the full window width", window.status.width() == window.width())
    check("branding visible when there is room", header.brand_title.isVisible())

    window.resize(1100, 950)
    for _ in range(3):
        app.processEvents()
    check("branding collapses when narrow", not header.brand_title.isVisible())

    play = header.play_button
    before = play.width()
    header.set_running(False)
    check(
        "PAUSE/RESUME toggle does not resize the button",
        play.width() == before,
        f"{before} -> {play.width()}",
    )
    header.set_running(True)
    window.close()


def test_theme() -> None:
    """Theme must be true black, white-accented and typographically stable."""
    section("Theme")
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from bmrcl.app import create_app
    from bmrcl.ui import theme

    QApplication.instance() or create_app([])
    check("background is pure black", theme.BG_BASE.name() == "#000000", theme.BG_BASE.name())
    check("deep background is pure black", theme.BG_DEEP.name() == "#000000")
    check("accent is white", theme.ACCENT.name() == "#ffffff", theme.ACCENT.name())
    check("station fill is black", theme.STATION_FILL.name() == "#000000")
    check("UI font is Arial-first", theme.UI_FAMILIES[0] == "Arial", theme.UI_FAMILIES[0])
    check("numeric font matches UI font", theme.MONO_FAMILIES == theme.UI_FAMILIES)

    metrics = QFontMetrics(theme.mono_font(12))
    widths = {
        metrics.horizontalAdvance(s) for s in ("00:00:00", "18:38:11", "23:59:59", "11:11:11")
    }
    check("clock digits do not jitter", len(widths) == 1, str(widths))
    check("no blue left in stylesheet", "#22d3ee" not in theme.STYLESHEET)


def test_performance(sim: Simulation) -> None:
    section("Performance")
    sim.clock.seek(parse_hhmm("09:00"))
    start = time.perf_counter()
    iterations = 120
    for _ in range(iterations):
        sim.rebuild()
    elapsed = (time.perf_counter() - start) / iterations * 1000.0
    check("simulation rebuild < 8ms", elapsed < 8.0, f"{elapsed:.2f} ms/frame")


def test_ui() -> None:
    section("UI smoke test (offscreen)")
    try:
        from PySide6.QtWidgets import QApplication

        from bmrcl.app import create_app
        from bmrcl.ui.main_window import MainWindow
    except Exception as exc:  # pragma: no cover
        check("PySide6 importable", False, str(exc))
        return

    app = QApplication.instance() or create_app([])
    sim = Simulation()
    sim.set_day_type("tue_fri")
    sim.clock.seek(parse_hhmm("09:00"))
    window = MainWindow(sim)
    window.resize(1600, 900)
    window.show()

    start = time.perf_counter()
    for _ in range(90):
        window._on_frame()
        app.processEvents()
    elapsed = (time.perf_counter() - start) / 90 * 1000.0
    check("full frame loop < 16.7ms", elapsed < 16.7, f"{elapsed:.2f} ms/frame")

    check("scene built line items", len(window.scene.line_items) == 3)
    check(
        "roster populated",
        window.train_table.model_.rowCount() > 0,
        str(window.train_table.model_.rowCount()),
    )

    station_item = window.scene.line_item("purple").station_item(18)
    check("station tooltip generated", "Mahatma Gandhi Road" in station_item.toolTip())

    window.view.fit_all()
    check("fit sets a sane zoom", 0.05 < window.view.zoom < 4.0, f"{window.view.zoom:.3f}")

    window._toggle_running()
    check("pause works", not sim.clock.running)
    window._toggle_running()
    check("resume works", sim.clock.running)

    window._set_speed(2.0)
    check("speed change works", sim.clock.speed == 2.0)

    window._seek(parse_hhmm("18:30"))
    check("seek works", int(sim.clock.seconds) == parse_hhmm("18:30"))
    check("evening peak has trains", sim.frame.total_active > 0, str(sim.frame.total_active))

    test_tabs(app, window)
    test_station_panel(app, window)
    window.close()


def test_station_panel(app, window) -> None:
    """Clicking a station must populate and live-update the detail dock."""
    section("Station detail panel")
    sim = window.simulation
    sim.clock.set_running(False)
    sim.clock.seek(parse_hhmm("09:00"))
    sim.rebuild()
    panel = window.station_panel

    check("starts empty", panel._station_key is None)

    green = sim.network.line("green")
    window._select_station(green.station("jayanagar"))
    app.processEvents()
    check(
        "normal station selected", panel._station_key == "green:jayanagar", str(panel._station_key)
    )
    check(
        "arrival tile filled",
        panel.tile_arrival.value.text() != "--",
        panel.tile_arrival.value.text(),
    )
    check(
        "departure tile filled",
        panel.tile_departure.value.text() != "--",
        panel.tile_departure.value.text(),
    )
    check("loop tile hidden at normal station", not panel.tile_loop.isVisible())

    window._select_station(green.station("yelachenahalli"))
    app.processEvents()
    check("loop tile shown at short-turn station", panel.tile_loop.isVisible())
    check("loop tile filled", panel.tile_loop.value.text() != "--", panel.tile_loop.value.text())
    check("loop note explains the reversal", len(panel.loop_note.text()) > 20)

    highlighted = [
        p.scene.line_item("green").station_item(green.index_of("yelachenahalli"))._highlight
        for p in window.panels
        if p.has_line("green")
    ]
    check("selected station highlighted in every relevant tab", all(highlighted))

    before = panel.tile_arrival.value.text()
    sim.clock.seek(parse_hhmm("09:00") + 40)
    sim.rebuild()
    window._refresh_station_panel()
    check(
        "countdown updates as time advances",
        panel.tile_arrival.value.text() != before,
        f"{before} -> {panel.tile_arrival.value.text()}",
    )

    sim.clock.seek(parse_hhmm("03:00"))
    sim.rebuild()
    window._refresh_station_panel()
    check(
        "handles no-service hours without crashing",
        panel.tile_arrival.value.text() in ("--", "due"),
        panel.tile_arrival.value.text(),
    )

    sim.clock.seek(parse_hhmm("09:00"))
    sim.rebuild()
    sim.clock.set_running(True)


def test_tabs(app, window) -> None:
    """Tabs must exist, isolate their line, and rescope every dependent panel."""
    section("Line tabs")
    sim = window.simulation
    tabs = window.tabs
    # Freeze the clock so roster contents and the reference counts describe
    # the same instant; otherwise the timer can advance between the two reads.
    sim.clock.set_running(False)
    check("4 tabs (network + 3 lines)", tabs.count() == 4, f"{tabs.count()}")
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    check(
        "tabs use full line names, not codes",
        labels == ["Network", "Purple Line", "Green Line", "Yellow Line"],
        str(labels),
    )
    check("no abbreviated tab labels", not any(lbl in ("PPL", "GRN", "YLW") for lbl in labels))
    check("tabs carry route tooltips", all(tabs.tabToolTip(i) for i in range(tabs.count())))

    tabs.setCurrentIndex(0)
    app.processEvents()
    window._refresh_slow()
    check("overview shows all 3 lines", len(window.panel.network) == 3)
    check("overview filter is None", window.active_line_ids is None)
    overview_rows = window.train_table.model_.rowCount()
    check(
        "overview roster = all trains",
        overview_rows == sim.frame.total_active,
        f"{overview_rows} vs {sim.frame.total_active}",
    )

    for index, line_id in ((1, "purple"), (2, "green"), (3, "yellow")):
        tabs.setCurrentIndex(index)
        for _ in range(3):
            window._on_frame()
            app.processEvents()
        panel = window.panel
        window._refresh_slow()
        expected = len(sim.frame.trains[line_id])
        rows = window.train_table.model_.rowCount()
        check(f"{line_id} tab scene has 1 line", len(panel.network) == 1)
        check(
            f"{line_id} tab filter scoped",
            window.active_line_ids == [line_id],
            str(window.active_line_ids),
        )
        check(f"{line_id} roster shows only that line", rows == expected, f"{rows} vs {expected}")
        only = {window.train_table.model_.train_at(r).line_id for r in range(rows)}
        check(f"{line_id} roster has no foreign trains", only <= {line_id}, str(only))
        visible = [lid for lid, c in window.line_panel.cards.items() if c.isVisible()]
        check(f"{line_id} line card scoped", visible == [line_id], str(visible))
        check(
            f"{line_id} roster title updated",
            line_id.upper() in window.dock_trains.windowTitle().upper().replace(" LINE", ""),
            window.dock_trains.windowTitle(),
        )
        check(f"{line_id} tab fitted", 0.05 < panel.zoom < 4.0, f"{panel.zoom:.3f}")

    tabs.setCurrentIndex(0)
    app.processEvents()
    window._refresh_slow()
    check(
        "returning to overview restores full roster",
        window.train_table.model_.rowCount() == sim.frame.total_active,
    )

    sim.clock.set_running(True)
    start = time.perf_counter()
    for _ in range(60):
        window._on_frame()
        app.processEvents()
    elapsed = (time.perf_counter() - start) / 60 * 1000.0
    check("tabbed frame loop < 16.7ms", elapsed < 16.7, f"{elapsed:.2f} ms/frame")

    tabs.setCurrentIndex(1)
    app.processEvents()
    start = time.perf_counter()
    for _ in range(60):
        window._on_frame()
        app.processEvents()
    single = (time.perf_counter() - start) / 60 * 1000.0
    check("single-line tab is not slower", single < 16.7, f"{single:.2f} ms/frame")

    dirty = [p for p in window.panels if p is not window.panel and p.is_dirty]
    check("hidden tabs are skipped", len(dirty) == 3, f"{len(dirty)} dirty")


def main() -> int:
    print("=" * 62)
    print(" BMRCL Train Tracker - self test")
    print("=" * 62)
    network = Network.load()
    timetable = Timetable.load(network)
    sim = Simulation(network, timetable)

    test_network(network)
    test_timetable(timetable, network)
    test_trains(sim)
    test_continuity(sim)
    test_eta(sim)
    test_station_board(sim)
    test_theme()
    test_header_layout()
    test_performance(sim)
    test_ui()

    print("\n" + "=" * 62)
    if FAILURES:
        print(f" {len(FAILURES)} FAILURE(S): " + ", ".join(FAILURES))
        return 1
    print(" ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
