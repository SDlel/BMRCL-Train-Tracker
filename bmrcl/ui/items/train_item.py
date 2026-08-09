"""QGraphicsItem representing a single train."""

from __future__ import annotations

import contextlib

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem

from ... import config
from ...core.trains import Phase, TrainState
from .. import theme


class TrainItem(QGraphicsItem):
    """A rounded rectangle with a direction chevron and a service badge.

    Instances are pooled and reused by the renderer, so the item is designed to
    be cheaply reconfigured via :meth:`apply` rather than recreated.
    """

    def __init__(self, colour: QColor, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.colour = QColor(colour)
        self.state: TrainState | None = None
        self._direction = 1
        self._short = False
        self._phase = Phase.RUNNING
        self._selected = False
        self.tooltip_provider = None
        self.setZValue(40)
        self.setAcceptHoverEvents(True)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        w, h = config.TRAIN_WIDTH, config.TRAIN_HEIGHT
        return QRectF(-w / 2 - 4.0, -h / 2 - 4.0, w + 8.0, h + 8.0)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = config.TRAIN_WIDTH, config.TRAIN_HEIGHT
        body = QRectF(-w / 2, -h / 2, w, h)

        fill = QColor(self.colour)
        if self._phase is Phase.DWELL:
            fill = fill.darker(150)
        elif self._phase is Phase.TERMINATED:
            fill = QColor(theme.TEXT_FAINT)
        elif self._phase.at_terminal:
            fill = fill.darker(170)

        edge = QColor(theme.SHORT_TURN) if self._short else fill.lighter(150)
        if self._selected:
            edge = QColor(theme.TEXT)

        painter.setPen(QPen(edge, 2.0 if (self._short or self._selected) else 1.0))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(body, 3.5, 3.5)

        strip = QColor(theme.BG_DEEP)
        strip.setAlpha(150)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(strip))
        painter.drawRect(QRectF(-w / 2 + 4.0, -1.6, w - 8.0, 3.2))

        nose_x = (w / 2 - 3.0) * self._direction
        chevron = QPolygonF(
            [
                QPointF(nose_x, 0.0),
                QPointF(nose_x - 4.5 * self._direction, -3.6),
                QPointF(nose_x - 4.5 * self._direction, 3.6),
            ]
        )
        painter.setBrush(QBrush(QColor(theme.BG_DEEP)))
        painter.drawPolygon(chevron)

        if self._phase is Phase.DWELL:
            painter.setBrush(QBrush(theme.WARN))
            painter.drawEllipse(QPointF(-w / 2 + 3.0, -h / 2 + 3.0), 1.8, 1.8)
        elif self._phase in (Phase.ARRIVED_TERMINAL, Phase.TURNING, Phase.DEPARTING):
            # Amber dot as for a dwell, plus a reversal arc, so a terminal
            # turnaround is distinguishable from an ordinary station stop.
            painter.setBrush(QBrush(theme.WARN))
            painter.drawEllipse(QPointF(-w / 2 + 3.0, -h / 2 + 3.0), 1.8, 1.8)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(theme.WARN, 1.4))
            arc = QRectF(-5.0, -4.5, 10.0, 9.0)
            painter.drawArc(arc, 40 * 16, 280 * 16)

    def apply(self, state: TrainState, x: float, y: float, min_step: float = 0.0) -> None:
        """Reposition and restyle this item for ``state``.

        ``min_step`` is the smallest scene-space movement worth committing.  At
        low zoom levels a train advances a fraction of a device pixel per
        frame; moving the item anyway would dirty a viewport rectangle for a
        change nobody can see.  Skipping those updates is the single biggest
        win when the whole network is fitted on screen.
        """
        restyle = (
            self._direction != state.direction
            or self._short != state.short_turn
            or self._phase is not state.phase
        )
        self.state = state
        self._direction = state.direction
        self._short = state.short_turn
        self._phase = state.phase

        pos = self.pos()
        if restyle or abs(pos.x() - x) >= min_step or abs(pos.y() - y) >= min_step:
            self.setPos(x, y)
        if restyle:
            self.update()

    def set_selected(self, on: bool) -> None:
        if self._selected != on:
            self._selected = on
            self.update()

    def hoverEnterEvent(self, event) -> None:
        self.refresh_tooltip()
        super().hoverEnterEvent(event)

    def refresh_tooltip(self) -> None:
        """Build the tooltip only when the pointer actually reaches the item."""
        if self.tooltip_provider is None or self.state is None:
            return
        # A tooltip is cosmetic; never let one take down the render loop.
        with contextlib.suppress(Exception):  # pragma: no cover
            self.setToolTip(self.tooltip_provider(self.state))
