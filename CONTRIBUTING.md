# Contributing

## Setup

```bash
git clone https://github.com/SDlel/bmrcl-train-tracker
cd bmrcl-train-tracker
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -e ".[dev]"
```

## Checks

Run all three before opening a pull request:

```bash
ruff check .          # lint
ruff format .         # format
python -m pytest      # 170 tests, ~15 s
python selftest.py    # end-to-end integration pass
```

CI runs the same commands on Linux, Windows and macOS against Python 3.12
and 3.13.

## Layering rule

`bmrcl/core/` must not import Qt. This is the project's one hard architectural
constraint. It keeps the domain logic headlessly testable and stops rendering
concerns leaking into the model.

To verify:

```bash
grep -r "PySide6" bmrcl/core/    # must return nothing
```

The UI should depend only on the public surface: `Simulation`, `Frame`,
`Network`, `Station`, `TrainState` and the formatting helpers. If you find
yourself importing `RunResolver` or `DayPlan` into a widget, add a method to
`Simulation` instead.

## Where things live

| Change | Files |
| --- | --- |
| New line or station | `bmrcl/data/lines/*.json` only |
| Timetable edit | `bmrcl/data/timetable.json` only |
| Colours, fonts, spacing | `bmrcl/ui/theme.py`, `bmrcl/config.py` |
| Movement rules | `bmrcl/config.py` |
| New drawn element | `bmrcl/ui/items/` |
| New dock or bar | `bmrcl/ui/widgets/` |
| Domain logic | `bmrcl/core/` |

Never hardcode a line or station name in Python. There are currently zero, and
that is what makes the network data-driven.

## Style

- Ruff enforces formatting and imports; do not hand-format.
- Type annotations on public functions.
- Docstrings explain **why**, not what. A comment that restates the code is
  noise; one that records a non-obvious decision is valuable.
- No comments unless they carry information the code cannot.

## Tests

Add tests beside the behaviour they cover:

| File | Covers |
| --- | --- |
| `test_network.py` | JSON loading, station metadata, geometry helpers |
| `test_timetable.py` | Parsing, window expansion, day types |
| `test_trains.py` | Motion, phases, ETA, midnight rollover |
| `test_arrivals.py` | Station board, short-turn loops |
| `test_clock.py` | Pause, speed, seeking, rollover |
| `test_theme.py` | AMOLED palette, typographic stability |
| `test_metrics.py` | Text-aware sizing helpers |
| `test_ui.py` | Header layout, tabs, docks, controls |
| `test_performance.py` | Frame budget |

Prefer a test that would have caught a real bug. Two examples already in the
suite:

- `test_last_train_of_the_day_is_not_dropped`. An exclusive final window
  silently deleted the final departure of every service.
- `test_nothing_is_clipped`. Hardcoded pixel widths cut off the `0.5x` and
  `20x` buttons.

## Performance

The frame budget is 16.7 ms. `test_performance.py` guards it with a 3× CI
tolerance.

If you touch the render path, measure before and after:

```python
import time

start = time.perf_counter()
for _ in range(120):
    window._on_frame()
    app.processEvents()
print((time.perf_counter() - start) / 120 * 1000, "ms")
```

Watch for the two traps this project already hit: `setText` schedules a repaint
even when the string is unchanged, and moving an item by a sub-pixel amount
still dirties a viewport rectangle.

## Screenshots

README images are generated, not hand-captured, so they stay consistent:

```bash
python tools/capture_screenshots.py
```

The script parks the simulation at a fixed instant (Tuesday to Friday, 09:12) and
asserts the expected content is present in each frame before saving, so a shot
can never silently capture an empty network. Regenerate after any visual
change.

## Commits

Present tense, imperative, explain the reasoning:

```
Fix last train of the day being dropped

The final headway window treated `end` as exclusive, so the published
last departure was never emitted. Closing windows now include it.
```
