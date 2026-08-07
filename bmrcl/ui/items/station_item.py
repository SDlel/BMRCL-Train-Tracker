"""QGraphicsItem for a station marker and its angled label."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsSimpleTextItem

from ... import config
from ...core.network import Station
from .. import theme


class StationLabelItem(QGraphicsSimpleTextItem):
    """Rotated station caption drawn beneath the track."""

    def __init__(self, station: Station, parent: QGraphicsItem | None = None) -> None:
        super().__init__(station.name, parent)
        font = theme.ui_font(config.STATION_LABEL_POINT_SIZE, bold=station.interchange)
        self.setFont(font)
        colour = theme.TEXT if (station.interchange or station.terminus) else theme.TEXT_DIM
        self.setBrush(QBrush(colour))
        self.setRotation(config.STATION_LABEL_ANGLE)
        self.setPos(6.0, config.STATION_LABEL_OFFSET)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)


class StationItem(QGraphicsItem):
    """A circle marker whose size and styling encode the station's role.

    * plain station - small hollow circle
    * terminus      - medium circle with a thicker ring
    * interchange   - large double ring
    * short-turn    - amber tick above the marker
    * depot         - small square badge below the marker
    """

    def __init__(
        self, station: Station, line_colour: QColor, parent: QGraphicsItem | None = None
    ) -> None:
        super().__init__(parent)
        self.station = station
        self.line_colour = QColor(line_colour)
        self._radius = station.radius
        self._hover = False
        self._highlight = False
        self.tooltip_provider = None
        self.setAcceptHoverEvents(True)
        self.setZValue(20)
        self.setToolTip(self._base_tooltip())
        self.label = StationLabelItem(station, self)
        # Station art is static, so rasterise it once per zoom level.
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)

    def boundingRect(self) -> QRectF:
        r = self._radius + 8.0
        return QRectF(-r, -r - 10.0, 2 * r, 2 * r + 20.0)

    def set_label_visible(self, visible: bool) -> None:
        """Level-of-detail hook used by the view when zooming out."""
        if self.label.isVisible() != visible:
            self.label.setVisible(visible)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = self._radius
        st = self.station

        if self._highlight:
            painter.setPen(QPen(theme.TEXT, 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r + 6.0, r + 6.0)
        elif self._hover:
            glow = QColor(self.line_colour)
            glow.setAlpha(70)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(0, 0), r + 6.0, r + 6.0)

        ring = QColor(self.line_colour)
        width = 3.0 if st.interchange else 2.0
        painter.setPen(QPen(ring, width))
        painter.setBrush(QBrush(theme.STATION_FILL))
        painter.drawEllipse(QPointF(0, 0), r, r)

        if st.interchange:
            inner = QColor(theme.TEXT)
            painter.setPen(QPen(inner, 1.4))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r - 4.0, r - 4.0)
        elif st.terminus:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(ring))
            painter.drawEllipse(QPointF(0, 0), r - 4.0, r - 4.0)

        if st.short_turn:
            pen = QPen(theme.SHORT_TURN, 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(QPointF(-4.0, -r - 6.0), QPointF(4.0, -r - 6.0))

        if st.depot:
            painter.setPen(QPen(theme.TEXT_FAINT, 1.0))
            painter.setBrush(QBrush(theme.BG_RAISED))
            painter.drawRect(QRectF(-3.0, r + 3.0, 6.0, 4.0))

    def hoverEnterEvent(self, event) -> None:
        self._hover = True
        self.refresh_tooltip()
        self.update()
        super().hoverEnterEvent(event)

    def refresh_tooltip(self) -> None:
        """Rebuild the tooltip on demand using the installed provider."""
        if self.tooltip_provider is None:
            return
        try:
            body = self.tooltip_provider(self.station)
        except Exception:  # pragma: no cover - never break the UI over a tooltip
            return
        self.set_live_tooltip(body)

    def hoverLeaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().hoverLeaveEvent(event)

    def set_highlight(self, on: bool) -> None:
        if self._highlight != on:
            self._highlight = on
            self.update()

    def _base_tooltip(self) -> str:
        st = self.station
        roles = []
        if st.terminus:
            roles.append("Terminus")
        if st.interchange:
            roles.append("Interchange")
        if st.short_turn:
            roles.append("Short-turn point")
        if st.depot:
            roles.append("Depot access")
        role_text = " | ".join(roles) if roles else "Through station"
        extra = ""
        if st.interchange_with:
            extra = f"<br><span style='color:{theme.HEX['text_dim']}'>Connects: {', '.join(st.interchange_with)}</span>"
        return (
            f"<b>{st.name}</b> <span style='color:{theme.HEX['text_dim']}'>[{st.code}]</span><br>"
            f"<span style='color:{theme.HEX['text_dim']}'>{role_text}</span>{extra}"
        )

    def set_live_tooltip(self, arrivals_html: str) -> None:
        """Attach freshly computed arrival information to the tooltip."""
        self.setToolTip(f"{self._base_tooltip()}<hr>{arrivals_html}")
