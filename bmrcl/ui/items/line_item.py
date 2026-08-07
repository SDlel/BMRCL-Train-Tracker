"""Static scenery for one metro line: header plate, tracks and stations."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem

from ... import config
from ...core.network import Line
from .. import theme
from .station_item import StationItem


class LineHeaderItem(QGraphicsItem):
    """Left-hand plate showing the line name, colour chip and terminals."""

    WIDTH = 210.0
    HEIGHT = 58.0

    def __init__(self, line: Line, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.line = line
        self.colour = QColor(line.colour)
        self._subtitle = f"{line.first.name}  <->  {line.last.name}"
        self._detail = f"{len(line)} stations"
        self.setZValue(15)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        return QRectF(-self.WIDTH, -self.HEIGHT / 2, self.WIDTH, self.HEIGHT)

    def set_detail(self, text: str) -> None:
        if text != self._detail:
            self._detail = text
            self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(-self.WIDTH, -self.HEIGHT / 2, self.WIDTH - 16.0, self.HEIGHT)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(theme.BG_PANEL))
        painter.drawRoundedRect(rect, 5.0, 5.0)

        chip = QRectF(rect.left(), rect.top(), 5.0, rect.height())
        painter.setBrush(QBrush(self.colour))
        painter.drawRoundedRect(chip, 2.5, 2.5)

        painter.setPen(QPen(theme.TEXT))
        painter.setFont(theme.ui_font(11, bold=True))
        painter.drawText(
            QRectF(rect.left() + 14.0, rect.top() + 7.0, rect.width() - 20.0, 16.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.line.name.upper(),
        )

        painter.setPen(QPen(theme.TEXT_DIM))
        painter.setFont(theme.ui_font(7))
        painter.drawText(
            QRectF(rect.left() + 14.0, rect.top() + 24.0, rect.width() - 20.0, 13.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._subtitle,
        )

        painter.setPen(QPen(theme.TEXT_DIM))
        painter.setFont(theme.mono_font(7))
        painter.drawText(
            QRectF(rect.left() + 14.0, rect.top() + 38.0, rect.width() - 20.0, 13.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._detail,
        )


class TrackItem(QGraphicsItem):
    """One directional running line drawn as a flat capsule."""

    def __init__(
        self, length: float, colour: QColor, dim: QColor, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self._length = length
        self.colour = QColor(colour)
        self.dim = QColor(dim)
        self.setZValue(5)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        h = config.TRACK_WIDTH + 4.0
        return QRectF(-8.0, -h / 2, self._length + 16.0, h)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        h = config.TRACK_WIDTH
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.dim))
        painter.drawRoundedRect(QRectF(0.0, -h / 2, self._length, h), h / 2, h / 2)


class LineItem(QGraphicsItem):
    """Container item that owns the header, tracks and station markers."""

    def __init__(self, line: Line, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.line = line
        self.colour = QColor(line.colour)
        self.dim = QColor(line.colour_dim)
        self.setZValue(1)
        self.setFlag(QGraphicsItem.ItemHasNoContents, True)

        self.span = (len(line) - 1) * config.STATION_SPACING
        self.header = LineHeaderItem(line, self)
        self.header.setPos(0.0, 0.0)

        self.track_up = TrackItem(self.span, self.colour, self.dim, self)
        self.track_up.setPos(0.0, -config.TRACK_OFFSET)
        self.track_down = TrackItem(self.span, self.colour, self.dim, self)
        self.track_down.setPos(0.0, config.TRACK_OFFSET)

        self.stations: list[StationItem] = []
        for station in line:
            item = StationItem(station, self.colour, self)
            item.setPos(station.index * config.STATION_SPACING, 0.0)
            self.stations.append(item)

        self._direction_captions()

    def _direction_captions(self) -> None:
        """Small ``UP``/``DN`` markers clarifying which track is which."""
        for text, y in (
            ("UP \u2192", -config.TRACK_OFFSET - 11.0),
            ("\u2190 DN", config.TRACK_OFFSET + 3.0),
        ):
            caption = QGraphicsSimpleTextItem(text, self)
            caption.setFont(theme.mono_font(6))
            caption.setBrush(QBrush(theme.TEXT_FAINT))
            caption.setPos(-4.0, y)
            caption.setZValue(6)

    def boundingRect(self) -> QRectF:
        return QRectF(-LineHeaderItem.WIDTH, -70.0, self.span + LineHeaderItem.WIDTH + 60.0, 190.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        return

    def x_for_index(self, index: float) -> float:
        """Scene-local X for a continuous station index."""
        return index * config.STATION_SPACING

    def y_for_direction(self, direction: int) -> float:
        return -config.TRACK_OFFSET if direction > 0 else config.TRACK_OFFSET

    def station_item(self, index: int) -> StationItem:
        return self.stations[index]
