"""Global configuration constants for BMRCL Train Tracker.

Everything that tunes the physics of the simulation or the geometry of the
renderer lives here so that no magic numbers are buried inside UI code.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "BMRCL Train Tracker"
APP_ORG = "BMRCL"
APP_VERSION = "1.3"

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
LINES_DIR = DATA_DIR / "lines"
TIMETABLE_FILE = DATA_DIR / "timetable.json"


INTER_STATION_SECONDS = 120.0

DWELL_SECONDS = 20.0

#: Total time a physical train occupies a terminal platform after arriving:
#: the initial arrival period plus the operational turnaround that follows.
#:
#: This is a SIMULATION ASSUMPTION, not published BMRCL data. The official
#: timetable states frequencies and notes that timings may change; it does not
#: establish a universal turnaround rule. Five minutes is a plausible default
#: and is meant to be adjusted (180, 240, 300 and so on) rather than trusted.
TURNAROUND_SECONDS = 300.0

#: Opening portion of the turnaround, representing the train sitting at the
#: terminal immediately after arrival while passengers alight. Counted inside
#: TURNAROUND_SECONDS, never added on top of it.
TERMINAL_ARRIVAL_SECONDS = 30.0

#: How long a run that has finished its turnaround with no onward working
#: remains visible at the terminal before leaving the simulation. Without this
#: the terminated state would be instantaneous and could never be inspected.
TERMINAL_CLEAR_SECONDS = 60.0

#: Whether an arriving train may continue into a later opposite-direction
#: working as the same physical vehicle.
#:
#: This never creates a service. Every working a train is linked to already
#: exists in the timetable; linkage only decides which physical vehicle is
#: assumed to work it. Public timetable data does not state rolling-stock
#: assignments, so the pairing is an inference, not a fact.
PHYSICAL_RETURN_LINKAGE = True

#: Longest gap between arriving and departing again that still counts as a
#: through working. Beyond this the vehicle is assumed to be stabled or sent to
#: depot, and the arriving run simply terminates.
MAX_LAYOVER_SECONDS = 1800.0

SECONDS_PER_DAY = 86400


STATION_SPACING = 88.0
LINE_ROW_SPACING = 330.0
SINGLE_LINE_ROW_HEIGHT = 300.0
SCENE_MARGIN_X = 140.0
SCENE_MARGIN_TOP = 150.0
SCENE_MARGIN_BOTTOM = 260.0

TRACK_OFFSET = 13.0
TRACK_WIDTH = 5.0

STATION_RADIUS = 7.5
INTERCHANGE_RADIUS = 11.5
TERMINUS_RADIUS = 10.0

STATION_LABEL_ANGLE = 40.0
STATION_LABEL_OFFSET = 30.0
STATION_LABEL_POINT_SIZE = 8

LABEL_LOD_ZOOM = 0.55

TRAIN_WIDTH = 34.0
TRAIN_HEIGHT = 15.0


TARGET_FPS = 60
FRAME_INTERVAL_MS = 1000 // TARGET_FPS

#: How often the clock is automatically re-checked against system time.
#: Each frame advances time by a measured interval, and those measurements are
#: rounded and clamped, so a few seconds an hour accumulate without this.
AUTO_REFRESH_MINUTES = 10

#: Corrections smaller than this are not worth reporting to the operator.
REFRESH_REPORT_THRESHOLD_SECONDS = 0.5

ZOOM_MIN = 0.18
ZOOM_MAX = 4.0
ZOOM_STEP = 1.15

SPEED_CHOICES = (0.5, 1.0, 2.0, 5.0, 20.0)
DEFAULT_SPEED = 1.0

TOOLTIP_ARRIVALS = 4
