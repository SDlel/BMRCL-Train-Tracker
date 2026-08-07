"""The QGraphicsScene that renders the whole network."""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSimpleTextItem

from .. import config
from ..core.network import Network
from ..core.simulation import Frame
from ..core.timetable import format_hhmm
from ..core.trains import TrainState
from . import theme
from .items import LineItem, TrainItem


class NetworkScene(QGraphicsScene):
    """Draws static line scenery once and updates train items every frame.

    Train items are pooled per line: on each frame the pool is resized to the
    number of live trains and the existing items are repositioned.  This keeps
    the per-frame cost proportional to the number of trains, with no item
    churn, which is what makes 60 FPS achievable.
    """

    #: A train must move at least this many *device* pixels before the scene
    #: bothers to move its item. Half a pixel is imperceptible.
    SUBPIXEL_THRESHOLD = 0.5

    def __init__(self, network: Network, parent=None) -> None:
        super().__init__(parent)
        self.network = network
        self.setBackgroundBrush(QBrush(theme.BG_BASE))
        # Trains move every frame; maintaining a BSP index for them costs more
        # than it saves at this item count.
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.line_items: dict[str, LineItem] = {}
        self._pools: dict[str, list[TrainItem]] = {}
        self._time_caption: QGraphicsSimpleTextItem | None = None
        self._selected_run: str | None = None
        self._labels_visible = True
        self._min_step = 0.0
        self._build()

    def _build(self) -> None:
        spacing = (
            config.LINE_ROW_SPACING if len(self.network) > 1 else config.SINGLE_LINE_ROW_HEIGHT
        )
        for row, line in enumerate(self.network):
            item = LineItem(line)
            item.setPos(0.0, row * spacing)
            self.addItem(item)
            self.line_items[line.id] = item
            self._pools[line.id] = []

        widest = max(((len(line) - 1) * config.STATION_SPACING) for line in self.network)
        rows = len(self.network)
        self.setSceneRect(
            QRectF(
                -config.SCENE_MARGIN_X - 210.0,
                -config.SCENE_MARGIN_TOP,
                widest + config.SCENE_MARGIN_X * 2 + 260.0,
                (rows - 1) * spacing + config.SCENE_MARGIN_TOP + config.SCENE_MARGIN_BOTTOM,
            )
        )
        self._build_time_caption()

    def _build_time_caption(self) -> None:
        caption = QGraphicsSimpleTextItem("")
        caption.setFont(theme.mono_font(26, bold=True))
        caption.setBrush(QBrush(QColor(theme.TEXT)))
        caption.setOpacity(0.10)
        caption.setZValue(0)
        caption.setPos(self.sceneRect().left() + 24.0, self.sceneRect().top() + 16.0)
        self.addItem(caption)
        self._time_caption = caption

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, theme.BG_BASE)
        painter.setPen(QPen(theme.GRID, 1.0))
        step = config.STATION_SPACING * 2
        x = rect.left() - (rect.left() % step)
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += step
        row = config.LINE_ROW_SPACING if len(self.network) > 1 else config.SINGLE_LINE_ROW_HEIGHT
        y = rect.top() - (rect.top() % row)
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += row

    def set_min_step(self, zoom: float) -> None:
        """Set the sub-pixel movement threshold for the current zoom level."""
        self._min_step = (self.SUBPIXEL_THRESHOLD / zoom) if zoom > 1e-6 else 0.0

    def apply_frame(self, frame: Frame, *, update_headers: bool = True) -> None:
        """Synchronise the scene with a simulation frame.

        ``update_headers`` is disabled on most frames because the header text
        only changes about once a second and repainting it forces extra scene
        invalidation.
        """
        if update_headers and self._time_caption is not None:
            self._time_caption.setText(frame.clock.hhmm)

        for line_id, item in self.line_items.items():
            trains = frame.trains.get(line_id, ())
            self._sync_pool(line_id, item, trains)
            if update_headers:
                stat = frame.stats.get(line_id)
                if stat is not None:
                    item.header.set_detail(
                        f"{len(item.line)} stn  |  {stat.active:>2} live  |  {stat.short_turns} short"
                    )

    def _sync_pool(self, line_id: str, line_item: LineItem, trains) -> None:
        pool = self._pools[line_id]
        colour = QColor(line_item.line.colour)
        selected = self._selected_run

        while len(pool) < len(trains):
            item = TrainItem(colour, line_item)
            item.tooltip_provider = lambda state, li=line_item: self.train_tooltip(state, li)
            pool.append(item)

        min_step = self._min_step
        for i, state in enumerate(trains):
            item = pool[i]
            x = line_item.x_for_index(state.position)
            y = line_item.y_for_direction(state.direction)
            item.apply(state, x, y, min_step)
            if selected is not None or item._selected:
                item.set_selected(state.run_id == selected)
            if not item.isVisible():
                item.setVisible(True)

        for item in pool[len(trains) :]:
            if item.isVisible():
                item.setVisible(False)

    def train_tooltip(self, state: TrainState, line_item: LineItem) -> str:
        """Compose the hover tooltip for a train (called lazily on hover)."""
        line = line_item.line
        dest = line.at(state.destination_index).name
        nxt = line.at(state.to_index).name
        phase = state.phase.value.upper()
        badge = "SHORT TURN" if state.short_turn else "FULL ROUTE"
        eta = f"{int(state.seconds_to_next // 60):d}m {int(state.seconds_to_next % 60):02d}s"
        return (
            f"<b>{state.run_id}</b> <span style='color:{theme.HEX['warn']}'>{badge}</span><br>"
            f"<span style='color:{theme.HEX['text_dim']}'>{state.service_label}</span><br>"
            f"Departed {format_hhmm(state.departure_time)} &middot; {phase}<br>"
            f"Towards <b>{dest}</b><br>"
            f"Next stop <b>{nxt}</b> in {eta}<br>"
            f"Progress {state.progress * 100:.0f}%"
        )

    def set_labels_visible(self, visible: bool) -> None:
        """Show or hide every station caption in one pass."""
        if visible == self._labels_visible:
            return
        self._labels_visible = visible
        for line_item in self.line_items.values():
            for station_item in line_item.stations:
                station_item.set_label_visible(visible)

    def set_selected_run(self, run_id: str | None) -> None:
        self._selected_run = run_id

    def line_item(self, line_id: str) -> LineItem:
        return self.line_items[line_id]
