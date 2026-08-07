"""Global configuration constants for BMRCL Train Tracker.

Everything that tunes the physics of the simulation or the geometry of the
renderer lives here so that no magic numbers are buried inside UI code.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "BMRCL Train Tracker"
APP_ORG = "BMRCL"
APP_VERSION = "1.0.0"

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
LINES_DIR = DATA_DIR / "lines"
TIMETABLE_FILE = DATA_DIR / "timetable.json"


INTER_STATION_SECONDS = 120.0

DWELL_SECONDS = 20.0

#: Time a train occupies a terminal platform after arrival before it is
#: released from the simulation (or reversed, when reversal is enabled).
TURNAROUND_SECONDS = 180.0

#: Full-line services are scheduled independently from *both* terminals in the
#: published timetable, therefore automatically reversing an arriving train
#: would double the modelled service.  The reversal machinery is implemented
#: and can be switched on for scenarios driven by a single-ended timetable.
REVERSE_AT_TERMINAL = False

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

ZOOM_MIN = 0.18
ZOOM_MAX = 4.0
ZOOM_STEP = 1.15

SPEED_CHOICES = (0.5, 1.0, 2.0, 5.0, 20.0)
DEFAULT_SPEED = 1.0

TOOLTIP_ARRIVALS = 4
