"""Simulation clock.

Decouples "wall clock" from "simulation clock" so that the dashboard can run
live, be paused, be rewound, or be fast-forwarded without any other subsystem
needing to know about it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .. import config


@dataclass(slots=True)
class ClockState:
    """Immutable snapshot handed to the simulation each frame."""

    seconds: float  # seconds after midnight of the simulated day
    day: date
    running: bool
    speed: float
    live: bool

    @property
    def datetime(self) -> datetime:
        return datetime.combine(self.day, datetime.min.time()) + timedelta(seconds=self.seconds)

    @property
    def hhmmss(self) -> str:
        total = int(self.seconds) % config.SECONDS_PER_DAY
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

    @property
    def hhmm(self) -> str:
        total = int(self.seconds) % config.SECONDS_PER_DAY
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


class SimulationClock:
    """Monotonic simulated time with pause, speed control and seeking.

    The clock is advanced by :meth:`tick`, which is driven by the render loop.
    Using a monotonic source keeps the simulation stable even if the machine's
    wall clock is adjusted while the dashboard is open.
    """

    def __init__(self, speed: float = config.DEFAULT_SPEED) -> None:
        now = datetime.now()
        self._day: date = now.date()
        self._seconds: float = (
            now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        )
        self._speed = float(speed)
        self._running = True
        self._live = True
        self._last_monotonic = time.monotonic()
        self._elapsed_sim = 0.0
        self._elapsed_real = 0.0

    def tick(self) -> float:
        """Advance the clock and return the simulated delta in seconds."""
        now = time.monotonic()
        real_delta = now - self._last_monotonic
        self._last_monotonic = now
        # Guard against huge jumps after the process was suspended.
        real_delta = min(real_delta, 0.5)
        self._elapsed_real += real_delta
        if not self._running:
            return 0.0
        delta = real_delta * self._speed
        self._seconds += delta
        self._elapsed_sim += delta
        while self._seconds >= config.SECONDS_PER_DAY:
            self._seconds -= config.SECONDS_PER_DAY
            self._day += timedelta(days=1)
        return delta

    # -- drift correction ---------------------------------------------------

    def drift(self) -> float | None:
        """Seconds the simulated clock is behind or ahead of the system clock.

        Only meaningful while running live at 1x. Returns ``None`` otherwise,
        because a paused or fast-forwarded clock is *supposed* to differ.

        Drift accumulates because each frame advances time by the measured
        interval since the previous frame, and those measurements are rounded,
        clamped when a frame stalls, and dropped entirely while the window is
        not being painted. In practice this loses a few seconds an hour.
        """
        if not self._live or not self._running:
            return None
        if abs(self._speed - 1.0) > 1e-9:
            return None
        now = datetime.now()
        if now.date() != self._day:
            return None
        wall = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        return self._seconds - wall

    def correct_drift(self) -> float | None:
        """Snap the simulated time back onto the system clock.

        Unlike :meth:`resync` this preserves the running state, the speed and
        the selected day, so it can run unattended without disturbing whatever
        the operator is doing.

        Returns:
            The correction applied in seconds, or ``None`` if the clock is not
            in a state where correction makes sense.
        """
        offset = self.drift()
        if offset is None:
            return None
        self._seconds -= offset
        self._last_monotonic = time.monotonic()
        return -offset

    def state(self) -> ClockState:
        return ClockState(
            seconds=self._seconds,
            day=self._day,
            running=self._running,
            speed=self._speed,
            live=self._live,
        )

    @property
    def seconds(self) -> float:
        return self._seconds

    @property
    def day(self) -> date:
        return self._day

    @property
    def running(self) -> bool:
        return self._running

    @property
    def live(self) -> bool:
        """True while the simulation is still aligned with the real clock."""
        return self._live

    @property
    def speed(self) -> float:
        return self._speed

    def set_speed(self, speed: float) -> None:
        self._speed = max(0.05, float(speed))
        if abs(self._speed - 1.0) > 1e-9:
            self._live = False

    def set_running(self, running: bool) -> None:
        if running and not self._running:
            self._last_monotonic = time.monotonic()
        self._running = running
        if not running:
            self._live = False

    def toggle(self) -> bool:
        self.set_running(not self._running)
        return self._running

    def seek(self, seconds: float, *, day: date | None = None) -> None:
        """Jump to an absolute time of day."""
        self._seconds = float(seconds) % config.SECONDS_PER_DAY
        if day is not None:
            self._day = day
        self._live = False
        self._last_monotonic = time.monotonic()

    def nudge(self, delta_seconds: float) -> None:
        """Move relative to the current simulated time."""
        self.seek(self._seconds + delta_seconds)

    def resync(self) -> None:
        """Snap back to the real system clock and resume live 1x operation."""
        now = datetime.now()
        self._day = now.date()
        self._seconds = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
        self._speed = 1.0
        self._running = True
        self._live = True
        self._last_monotonic = time.monotonic()
