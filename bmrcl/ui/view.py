"""Zoomable, pannable QGraphicsView tuned for smooth 60 FPS updates."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

from .. import config
from .items.station_item import StationItem
from .items.train_item import TrainItem


class NetworkView(QGraphicsView):
    """Interactive viewport.

    * mouse wheel      - zoom about the cursor
    * middle / space   - pan
    * left drag        - pan (hand cursor)
    * ``+`` / ``-``    - zoom
    * ``0``            - fit whole network
    """

    zoom_changed = Signal(float)
    station_clicked = Signal(object)
    train_clicked = Signal(object)

    def __init__(self, scene, parent=None) -> None:
        super().__init__(scene, parent)
        self._zoom = 1.0
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
        )
        # Only the rectangles that actually changed are repainted, which keeps
        # the cost proportional to the number of moving trains.
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setMouseTracking(True)
        self._apply_lod()

    def _apply_lod(self) -> None:
        """Hide station captions when they would be too small to read."""
        scene = self.scene()
        if hasattr(scene, "set_labels_visible"):
            scene.set_labels_visible(self._zoom >= config.LABEL_LOD_ZOOM)
        if hasattr(scene, "set_min_step"):
            scene.set_min_step(self._zoom)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float) -> None:
        value = max(config.ZOOM_MIN, min(config.ZOOM_MAX, value))
        if abs(value - self._zoom) < 1e-6:
            return
        factor = value / self._zoom
        self._zoom = value
        self.scale(factor, factor)
        self._apply_lod()
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * config.ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / config.ZOOM_STEP)

    def fit_all(self) -> None:
        """Fit the entire scene, keeping the internal zoom bookkeeping honest."""
        rect = self.scene().sceneRect()
        if rect.isEmpty():
            return
        self.resetTransform()
        self._zoom = 1.0
        self.fitInView(rect, Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._apply_lod()
        self.zoom_changed.emit(self._zoom)

    def reset_zoom(self) -> None:
        self.resetTransform()
        self._zoom = 1.0
        self._apply_lod()
        self.zoom_changed.emit(self._zoom)

    def focus_on(self, scene_pos: QPointF, zoom: float | None = None) -> None:
        if zoom is not None:
            self.set_zoom(zoom)
        self.centerOn(scene_pos)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        if event.modifiers() & Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
            return
        self.set_zoom(self._zoom * (config.ZOOM_STEP if delta > 0 else 1 / config.ZOOM_STEP))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.position().toPoint())
            node = item
            while node is not None:
                if isinstance(node, TrainItem):
                    self.train_clicked.emit(node.state)
                    break
                if isinstance(node, StationItem):
                    self.station_clicked.emit(node.station)
                    break
                node = node.parentItem()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_in()
        elif key == Qt.Key_Minus:
            self.zoom_out()
        elif key == Qt.Key_0:
            self.fit_all()
        else:
            super().keyPressEvent(event)
