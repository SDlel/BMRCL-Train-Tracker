# Data format

Everything the dashboard draws comes from JSON. Adding a line requires no
Python changes.

## Line definition

One file per line in `bmrcl/data/lines/`.

```json
{
  "id": "blue",
  "name": "Blue Line",
  "short_name": "BLU",
  "colour": "#3b82f6",
  "colour_dim": "#1e40af",
  "row": 3,
  "order": 4,
  "terminals": { "up": "central_silk_board", "down": "kempapura" },
  "stations": [
    {
      "id": "central_silk_board",
      "name": "Central Silk Board",
      "code": "CSB",
      "terminus": true,
      "interchange": true,
      "interchange_with": ["Yellow Line"]
    }
  ]
}
```

### Line fields

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable key, referenced by the timetable |
| `name` | string | Passenger-facing name, used as the tab label |
| `short_name` | string | Three-letter code for the legend and roster |
| `colour` | hex | Track, station rings, train bodies |
| `colour_dim` | hex | Unlit track fill |
| `row` | int | Vertical position in the overview tab |
| `order` | int | Sort order in the roster and tab bar |
| `terminals` | object | `up` and `down` station ids, must match the ends |

### Station fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `id` | string | required | Unique within the line |
| `name` | string | required | Displayed label |
| `code` | string | derived | Short code in tooltips and the roster |
| `terminus` | bool | ends only | Filled centre, medium circle |
| `interchange` | bool | `false` | Large double ring |
| `short_turn` | bool | `false` | Amber tick; enables the loop tile |
| `depot` | bool | `false` | Small square badge |
| `interchange_with` | array | `[]` | Connecting lines, shown in the tooltip |

Station order in the array **is** the track order. Index 0 is the `up`
terminal.

## Timetable

`bmrcl/data/timetable.json` holds every service for every day type.

```json
{
  "day_types": {
    "monday":   { "label": "Monday",          "weekdays": [0] },
    "tue_fri":  { "label": "Tuesday-Friday",  "weekdays": [1, 2, 3, 4] },
    "saturday": { "label": "Saturday",        "weekdays": [5] },
    "sunday":   { "label": "Sunday",          "weekdays": [6] }
  },
  "lines": {
    "purple": {
      "services": {
        "tue_fri": [ /* service objects */ ]
      }
    }
  }
}
```

`weekdays` uses Python's `date.weekday()`, where Monday is 0.

### Service object

```json
{
  "id": "PPL-WFD-FULL",
  "label": "Whitefield to Challaghatta",
  "type": "full",
  "origin": "whitefield_kadugodi",
  "destination": "challaghatta",
  "windows": [
    { "start": "05:20", "end": "10:57", "headway": 10 },
    { "start": "10:57", "end": "15:21", "headway": 8 }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | Shown in the roster as `ID#trip` |
| `label` | Human description, used in tooltips |
| `type` | `full` or `short`. `short` draws an amber outline |
| `origin` / `destination` | Station ids on this line |
| `windows` | Headway windows, expanded into departures |
| `departures` | Explicit times, for one-off workings |

### How windows expand

A window emits a departure every `headway` minutes starting at `start`.

```
{ "start": "10:00", "end": "10:30", "headway": 10 }
  →  10:00, 10:10, 10:20
```

`end` is **exclusive**: it is the moment the next window takes over, so that
departure belongs to the following window. This prevents a doubled train at
every boundary.

The exception is the **final** window of a service, where `end` is the
published last train and is therefore included:

```
{ "start": "22:40", "end": "23:05", "headway": 12.5 }
  →  22:40, 22:52, 23:05      ← last train kept
```

Fractional headways are supported (`5.5`, `12.5`).

### Explicit departures

For irregular workings such as the Purple Line short loops, list the times
directly instead of using windows:

```json
{
  "id": "PPL-KGM-PTA-AM",
  "type": "short",
  "origin": "kempegowda_majestic",
  "destination": "pattandur_agrahara",
  "departures": ["08:58", "09:07", "09:18", "09:28"]
}
```

Both `windows` and `departures` may appear on one service; the results are
merged, sorted and de-duplicated.

### Short-turn services

A short working is an ordinary service with `"type": "short"` whose origin or
destination is an intermediate station. It runs *alongside* the full-route
service rather than replacing it, which is how the real timetable increases
frequency on the busy core.

For the station detail panel to show a loop tile, the origin station must also
carry `"short_turn": true` in its line definition.

## Movement model

Not stored per service. These are global constants in `bmrcl/config.py`.

| Constant | Value | Meaning |
| --- | --- | --- |
| `INTER_STATION_SECONDS` | 120 | Run time between adjacent stations |
| `DWELL_SECONDS` | 20 | Stop at an intermediate station |
| `TERMINAL_ARRIVAL_SECONDS` | 30 | Opening portion of the turnaround |
| `TURNAROUND_SECONDS` | 300 | Total terminal occupancy after arrival |
| `TERMINAL_CLEAR_SECONDS` | 60 | Visibility after the turnaround completes |
| `PHYSICAL_RETURN_LINKAGE` | `True` | See below |
| `MAX_LAYOVER_SECONDS` | 1800 | Longest gap still counted as a through working |

Terminal turnaround is modelled explicitly: an arriving train holds the
platform for `TURNAROUND_SECONDS`, split into an arrival period and a turning
period. The 300 second default is a simulation assumption rather than published
BMRCL data.

Physical return linkage pairs an arriving train with a later departure that
already exists in the timetable, so a vehicle can be followed through a
turnaround. It never creates a departure. Rolling-stock assignments are not
published, so the pairing is an inference and can be switched off.

## Adding a line: checklist

1. Create `bmrcl/data/lines/<id>.json` with a unique `row` and `order`.
2. Add `lines.<id>.services` to `timetable.json` for each day type.
3. Run `python -m pytest tests/test_network.py`. Station counts, contiguous
   indices and terminal consistency are all validated.
4. Launch. The line appears in the overview, gains its own tab, and joins the
   legend and roster automatically.

## Accuracy

Timetable values are transcribed from published BMRCL frequency tables and
interpreted as headway windows for simulation. They are **not** an
authoritative passenger schedule, and departures are generated from terminal
frequencies rather than being real per-station times.
