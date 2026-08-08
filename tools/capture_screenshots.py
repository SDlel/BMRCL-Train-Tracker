#!/usr/bin/env python3
"""Capture the README screenshots.

Runs the dashboard at a fixed simulated time so the images are reproducible,
and asserts the expected content is present in each shot before saving.

Usage::

    python tools/capture_screenshots.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402

from bmrcl.app import create_app  # noqa: E402
from bmrcl.core.simulation import Simulation  # noqa: E402
from bmrcl.core.timetable import parse_hhmm  # noqa: E402
from bmrcl.ui.main_window import MainWindow  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "images"

CAPTURE_TIME = "09:12"
CAPTURE_DAY = "tue_fri"

WIDTH, HEIGHT = 1760, 1000


def settle(app, ms: int = 260) -> None:
    """Let Qt finish layout, then run a few frames so trains are placed."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    for _ in range(6):
        app.processEvents()


def save(window, name: str) -> Path:
    path = OUTPUT_DIR / name
    pixmap = window.grab()
    pixmap.save(str(path), "PNG")
    return path


def describe(path: Path) -> str:
    from PySide6.QtGui import QImage

    image = QImage(str(path))
    size = path.stat().st_size / 1024
    return f"{image.width()}x{image.height()}  {size:6.0f} KB  {path.name}"


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "ok " if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail else ""))
    return condition


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app = create_app([])

    simulation = Simulation()
    simulation.set_day_type(CAPTURE_DAY)
    simulation.clock.seek(parse_hhmm(CAPTURE_TIME))
    simulation.clock.set_speed(1.0)

    window = MainWindow(simulation)
    window.resize(WIDTH, HEIGHT)
    window.show()
    settle(app, 500)

    ok = True
    shots: list[Path] = []

    window.tabs.setCurrentIndex(0)
    settle(app)
    window._fit()
    settle(app)
    frame = simulation.frame
    ok &= check(
        "overview has trains on every line",
        all(frame.trains[line.id] for line in simulation.network),
        f"{frame.total_active} live",
    )
    shots.append(save(window, "01-network-overview.png"))

    window.tabs.setCurrentIndex(1)
    settle(app)
    window._fit()
    settle(app)
    ok &= check("purple tab is scoped", window.active_line_ids == ["purple"])
    ok &= check(
        "roster shows only purple",
        window.train_table.model_.rowCount() == len(frame.trains["purple"]),
    )
    shots.append(save(window, "02-purple-line.png"))

    window.tabs.setCurrentIndex(2)
    settle(app)
    green = simulation.network.line("green")
    station = green.station("yelachenahalli")
    window._select_station(station)
    settle(app)
    line_item = window.panel.scene.line_item("green")
    window.view.set_zoom(0.92)
    window.view.centerOn(line_item.mapToScene(line_item.x_for_index(station.index), 0.0))
    settle(app)

    panel = window.station_panel
    ok &= check("loop tile visible at short-turn station", panel.tile_loop.isVisible())
    ok &= check(
        "arrival populated",
        panel.tile_arrival.value.text() != "--",
        panel.tile_arrival.value.text(),
    )
    ok &= check(
        "departure populated",
        panel.tile_departure.value.text() != "--",
        panel.tile_departure.value.text(),
    )
    ok &= check(
        "loop populated", panel.tile_loop.value.text() != "--", panel.tile_loop.value.text()
    )
    shots.append(save(window, "03-station-detail.png"))

    window.tabs.setCurrentIndex(1)
    settle(app)
    purple = simulation.network.line("purple")
    majestic = purple.station("kempegowda_majestic")
    window._select_station(majestic)

    running = next(
        (t for t in simulation.frame.trains["purple"] if 0.3 < t.progress < 0.8),
        None,
    )
    if running is not None:
        window._on_train_selected(running)
        settle(app)
        ok &= check("train panel populated", window.train_panel._run_id == running.run_id)
        ok &= check(
            "train panel shows a next stop",
            window.train_panel.tile_next.value.text() != "--",
            window.train_panel.tile_next.value.text(),
        )

    purple_item = window.panel.scene.line_item("purple")
    window.view.set_zoom(1.35)
    window.view.centerOn(purple_item.mapToScene(purple_item.x_for_index(majestic.index), 0.0))
    settle(app)
    ok &= check(
        "labels visible when zoomed in",
        window.panel.scene._labels_visible,
        f"zoom {window.view.zoom:.2f}",
    )
    shots.append(save(window, "04-zoomed-detail.png"))

    print()
    for path in shots:
        print("  " + describe(path))

    window.close()
    print("\n" + ("All screenshots captured." if ok else "Captured WITH FAILURES."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
