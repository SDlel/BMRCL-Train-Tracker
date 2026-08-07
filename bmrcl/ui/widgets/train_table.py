"""Dockable live train roster - the operator's textual view of the network."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from ...core.network import Network
from ...core.timetable import format_hhmm
from ...core.trains import Phase, TrainState
from .. import theme

COLUMNS = ("RUN", "LINE", "DEP", "NEXT STOP", "ETA", "DESTINATION", "STATE")


def _mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:d}:{seconds % 60:02d}"


class TrainTableModel(QAbstractTableModel):
    """Read-only model over the current list of live trains."""

    VOLATILE_FIRST = 3
    VOLATILE_LAST = len(COLUMNS) - 1

    def __init__(self, network: Network, parent=None) -> None:
        super().__init__(parent)
        self.network = network
        self._rows: list[TrainState] = []

    # The default-argument calls below are mandated by the Qt override
    # signature, hence the B008 suppressions.
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or orientation != Qt.Horizontal:
            return None
        return COLUMNS[section]

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        train = self._rows[index.row()]
        line = self.network.line(train.line_id)
        column = index.column()

        if role == Qt.DisplayRole:
            if column == 0:
                return train.run_id
            if column == 1:
                return line.short_name
            if column == 2:
                return format_hhmm(train.departure_time)
            if column == 3:
                return line.at(train.to_index).name
            if column == 4:
                if train.phase is Phase.DWELL:
                    return "dwell"
                if train.phase is Phase.TERMINATED:
                    return "-"
                return _mmss(train.seconds_to_next)
            if column == 5:
                return line.at(train.destination_index).name
            if column == 6:
                return ("SHORT " if train.short_turn else "") + train.phase.value.upper()
            return None

        if role == Qt.ForegroundRole:
            if column == 1:
                return QBrush(QColor(line.colour))
            if column == 6 and train.short_turn:
                return QBrush(theme.SHORT_TURN)
            if column == 4 and train.phase is Phase.DWELL:
                return QBrush(theme.WARN)
            if column in (0, 2, 4):
                return QBrush(theme.TEXT_DIM)
            return None

        if role == Qt.FontRole:
            return theme.mono_font(8) if column in (0, 1, 2, 4, 6) else theme.ui_font(8)

        if role == Qt.TextAlignmentRole and column in (1, 2, 4):
            return int(Qt.AlignCenter)

        if role == Qt.UserRole:
            return train
        return None

    def set_rows(self, rows: list[TrainState]) -> None:
        """Replace the roster, preserving scroll position where possible.

        A full reset would drop the selection and scroll position, so when the
        row count is unchanged the rows are swapped in place.  Only the
        genuinely volatile span of columns is invalidated - the run id, line
        and departure time never change for a given row, and repainting them
        every refresh was measurably expensive.
        """
        if len(rows) == len(self._rows):
            changed = [
                i
                for i, (a, b) in enumerate(zip(self._rows, rows, strict=False))
                if a.run_id != b.run_id
                or a.to_index != b.to_index
                or a.phase is not b.phase
                or int(a.seconds_to_next) != int(b.seconds_to_next)
            ]
            self._rows = rows
            if changed:
                top = self.index(changed[0], self.VOLATILE_FIRST)
                bottom = self.index(changed[-1], self.VOLATILE_LAST)
                self.dataChanged.emit(top, bottom, [Qt.DisplayRole, Qt.ForegroundRole])
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def train_at(self, row: int) -> TrainState | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class TrainTable(QTableView):
    """Table view wired for single-row selection and train focusing."""

    train_selected = Signal(object)

    def __init__(self, network: Network, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model_ = TrainTableModel(network, self)
        self.setModel(self.model_)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(21)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        self.setColumnWidth(0, 128)
        self.setColumnWidth(1, 44)
        self.setColumnWidth(2, 52)
        self.setColumnWidth(3, 168)
        self.setColumnWidth(4, 50)
        self.setColumnWidth(5, 168)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, index: QModelIndex) -> None:
        train = self.model_.train_at(index.row())
        if train is not None:
            self.train_selected.emit(train)

    def refresh(self, trains: list[TrainState]) -> None:
        self.model_.set_rows(trains)
