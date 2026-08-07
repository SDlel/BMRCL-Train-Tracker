"""A self-contained scene + view pair for one tab of the dashboard.

Each tab owns its own :class:`NetworkScene`, built over a subset of the
network.  Only the visible tab is fed frames, so inactive tabs cost nothing.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..core.network import Network
from ..core.simulation import Frame
from .scene import NetworkScene
from .view import NetworkView


class NetworkPanel(QWidget):
    """Scene, view and the plumbing needed to drive them.

    A panel is *dirty* whenever the simulation advanced while it was hidden.
    Switching to a stale tab triggers a catch-up refresh so the operator never
    sees a frozen picture.
    """

    station_clicked = Signal(object)
    train_clicked = Signal(object)
    zoom_changed = Signal(float)

    def __init__(
        self, network: Network, line_ids: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.line_ids = list(line_ids)
        self.network = network.subset(line_ids)
        self._dirty = True
        self._fitted = False

        self.scene = NetworkScene(self.network)
        self.view = NetworkView(self.scene)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)

        self.view.station_clicked.connect(self.station_clicked.emit)
        self.view.train_clicked.connect(self.train_clicked.emit)
        self.view.zoom_changed.connect(self.zoom_changed.emit)

    def apply_frame(self, frame: Frame, *, update_headers: bool = True) -> None:
        """Push a frame into this panel's scene."""
        self.scene.apply_frame(frame, update_headers=update_headers)
        self._dirty = False

    def mark_dirty(self) -> None:
        """Record that this panel missed at least one frame."""
        self._dirty = True

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def ensure_fitted(self) -> None:
        """Fit the network the first time this tab becomes visible.

        Fitting before the widget has a real size would compute a nonsense
        zoom, so it is deferred until the tab is actually shown.
        """
        if not self._fitted and self.width() > 50:
            self.view.fit_all()
            self._fitted = True

    @property
    def zoom(self) -> float:
        return self.view.zoom

    def has_line(self, line_id: str) -> bool:
        return line_id in self.line_ids
