"""Domain layer: network, timetable, clock, trains and the simulation facade."""

from .arrivals import ArrivalBoard, BoardEntry, LoopEvent, StationBoard
from .clock import ClockState, SimulationClock
from .network import Line, Network, Station
from .simulation import Frame, LineStats, Simulation
from .timetable import Departure, Service, Timetable, format_hhmm, format_hhmmss, parse_hhmm
from .trains import LineTrainManager, Phase, TrainManager, TrainState

__all__ = [
    "ArrivalBoard",
    "BoardEntry",
    "ClockState",
    "Departure",
    "Frame",
    "Line",
    "LineStats",
    "LineTrainManager",
    "LoopEvent",
    "Network",
    "Phase",
    "Service",
    "Simulation",
    "SimulationClock",
    "Station",
    "StationBoard",
    "Timetable",
    "TrainManager",
    "TrainState",
    "format_hhmm",
    "format_hhmmss",
    "parse_hhmm",
]
