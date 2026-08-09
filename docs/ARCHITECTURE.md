# Architecture

## Layering

The codebase is split into two layers with a hard boundary between them.

```
┌─────────────────────────────────────────────┐
│  bmrcl.ui        PySide6, QGraphicsScene    │
│                  scene, view, widgets       │
└───────────────────┬─────────────────────────┘
                    │  Simulation, Frame,
                    │  StationBoard, TrainState
┌───────────────────▼─────────────────────────┐
│  bmrcl.core      pure Python, zero Qt       │
│                  network, timetable, clock  │
└───────────────────┬─────────────────────────┘
                    │  JSON
┌───────────────────▼─────────────────────────┐
│  bmrcl.data      lines/*.json, timetable    │
└─────────────────────────────────────────────┘
```

`bmrcl.core` imports nothing from Qt. This is enforceable rather than aspirational:

```python
import sys


class Block:
    def find_module(self, name, path=None):
        if name.startswith("PySide6"):
            return self

    def load_module(self, name):
        raise ImportError("PySide6 is blocked")


sys.meta_path.insert(0, Block())

from bmrcl.core.simulation import Simulation  # still works
```

The full simulation runs with Qt unimportable. That is what makes the domain
logic testable headlessly and keeps rendering concerns out of the model.

The UI depends on exactly six public names: `Simulation`, `Frame`, `Network`,
`Station`, `TrainState` and `format_hhmm`. Nothing reaches into `RunResolver`,
`DayPlan` or `Window`.

## Data flow

One frame, sixty times a second:

```
QTimer
  └─ Simulation.step()
       ├─ SimulationClock.tick()        advance simulated time
       └─ Simulation.rebuild()
            ├─ TrainManager.snapshot()  positions from time
            └─ LineStats                per-line counters
                  │
                  ▼  Frame
       ┌──────────┴────────────┬──────────────┐
       ▼                       ▼              ▼
  NetworkScene            HeaderBar       StatusBar
  (visible tab only)      (10 Hz)         (10 Hz)
```

Peripheral widgets run at lower rates. Only the geometry update is on the
full 60 Hz path.

## Positions are a pure function of time

Nothing is integrated frame to frame. A train's position derives entirely from
its departure time and the current instant:

```python
CYCLE = INTER_STATION_SECONDS + DWELL_SECONDS  # 120 + 20
elapsed = now - departure_time
hop = elapsed // CYCLE
rem = elapsed % CYCLE

if rem < INTER_STATION_SECONDS:  # running
    position = from_index + direction * (rem / INTER_STATION_SECONDS)
else:  # dwelling
    position = to_index
```

Consequences:

- **Seeking is exact.** Jumping to 18:30 needs no replay.
- **Pausing is free.** No state accumulates while stopped.
- **Rendering is deterministic.** The same instant always yields the same
  picture, which is what makes `test_position_is_a_pure_function_of_time`
  possible.
- **No drift.** A session left running overnight stays correct.

## Timetable expansion

The JSON stores headway windows, not departure times. Expansion happens once,
lazily, and is memoised per `(line, day_type)`.

```
Window(start, end, headway)
   └─ departures()  →  [05:20, 05:30, 05:40, ...]
        └─ Service (origin → destination)
             └─ Departure (time, trip_index)
                  └─ DayPlan (sorted, bisectable)
```

`end` is exclusive, because it is the moment the next window takes over and
therefore owns that departure. The exception is the final window of a service,
where `end` is the published last train, the `closing` flag. Getting this
wrong silently deleted the last train of every day, which is why
`test_last_train_of_the_day_is_not_dropped` exists.

Rendering code never sees a frequency. It consumes `Departure` objects only.

## Rendering

`NetworkScene` maintains a pool of `TrainItem` objects per line. Each frame the
pool is resized to the live train count and existing items are repositioned;
items are hidden rather than destroyed. Cost is proportional to the number of
trains, with no allocation churn.

Static art, meaning tracks, station circles and header plates, is painted once
into a device-coordinate cache. The scene uses `NoIndex` because a BSP tree costs more
than it saves when most items move every frame.

### The sub-pixel threshold

The single largest performance win. At fitted zoom a train advances a fraction
of a device pixel per frame. Committing that move dirties a viewport rectangle
for a change nobody can perceive:

```python
if restyle or abs(pos.x() - x) >= min_step:
    self.setPos(x, y)
```

`min_step` is half a device pixel converted to scene units. This took the
fitted view from 25 ms to 6 ms per frame.

## Tabs

Each tab owns a `NetworkPanel`, an independent `NetworkScene` and
`NetworkView` over a `Network.subset()`. Line objects are shared, not copied.

Only the visible panel receives frames. Hidden panels are marked dirty and
catch up when selected, so idle tabs cost nothing. Each keeps its own zoom and
pan.

The active tab also scopes the roster, the line-status cards, the status-bar
counters and the legend, via `MainWindow.active_line_ids`.

## Terminal turnaround

A run does not end the instant it reaches its destination. The resolver keeps
producing states for a further `TURNAROUND_SECONDS`, split into an arrival
period and a turning period:

```python
terminal_elapsed = elapsed - total
if terminal_elapsed < TERMINAL_ARRIVAL_SECONDS:
    phase = Phase.ARRIVED_TERMINAL
elif terminal_elapsed < TURNAROUND_SECONDS:
    phase = Phase.TURNING
else:
    phase = Phase.TERMINATED
```

The two terminal periods sum to `TURNAROUND_SECONDS` exactly. Changing that
constant rescales the turning period and leaves the arrival period alone.

Because state is still derived purely from elapsed time, seeking into or past a
turnaround is exact, and pausing freezes the countdown without special cases.

## Physical train linkage

`core/linkage.py` pairs each arrival with a later departure from the same
station, so one vehicle can work several runs in sequence. The table is built
once per line and day type, cached in a `LinkageRegistry`, and consulted by
`RunResolver` through a dictionary lookup, so the per-frame cost is negligible.

A linked run stays resolvable until its onward departure rather than expiring
after the turnaround, which is what keeps the train on the platform. The
candidate lookback widens by `MAX_LAYOVER_SECONDS` to compensate.

`physical_train_id` is shared along a chain. The renderer keys its item pool by
that id rather than by list position, so the same `QGraphicsItem` represents
the vehicle before and after it reverses. Without this the train would blink
out and a different rectangle would appear heading the other way.

The matching is greedy over time-ordered arrivals, which makes it deterministic
and therefore reproducible from a timestamp, the same property the rest of the
simulation depends on.

## Extending the network

Adding Blue, Orange or the Airport line is a data-only change:

1. Drop `bmrcl/data/lines/blue.json` in place.
2. Add a matching `lines.blue` entry to `timetable.json`.

No Python changes. There are zero hardcoded line or station names in the
codebase. The scene lays out by `row`, the legend and panels enumerate the
loaded network, and a tab is generated per line.

## Performance budget

60 FPS means 16.7 ms. Measured at the morning peak (98 trains, 1920×1050):

| Stage | Cost |
| --- | --- |
| `Simulation.rebuild()` | 1.2 ms |
| Scene sync | 0.8 ms |
| Paint and event dispatch | ~4 ms |
| **Total** | **~7 ms** |

Optimisations, in order of impact:

1. Sub-pixel movement threshold (25 ms → 6 ms fitted)
2. Lazy tooltips, computed on hover rather than per frame (−11 ms)
3. Label level of detail, with captions hidden below 0.55 zoom
4. Pooled train items
5. Device-coordinate caching, `NoIndex` scene
6. Tiered refresh: 60 Hz geometry, 10 Hz text, 3 Hz roster
7. Idle hidden tabs
8. Dirty-span roster updates, touching only the volatile columns of changed rows
9. Cached label text, because `setText` repaints even when the string is unchanged
