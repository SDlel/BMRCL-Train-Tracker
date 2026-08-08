"""The main dashboard window: composes every widget and drives the render loop."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QMainWindow,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core.network import Station
from ..core.simulation import Simulation
from ..core.timetable import format_hhmm
from ..core.trains import TrainState
from . import theme
from .network_panel import NetworkPanel
from .scene import NetworkScene
from .view import NetworkView
from .widgets import HeaderBar, LinePanel, StationPanel, StatusBar, TrainPanel, TrainTable


class MainWindow(QMainWindow):
    """Main application window.

    The render loop is a single :class:`QTimer` at the target frame interval.
    Each tick advances the simulation clock, recomputes the network picture and
    pushes it into the scene and the peripheral widgets.  Expensive secondary
    work (station tooltips, the roster table) is throttled to a lower rate.
    """

    SLOW_REFRESH_FRAMES = 20

    TEXT_REFRESH_FRAMES = 6

    def __init__(self, simulation: Simulation | None = None) -> None:
        super().__init__()
        self.simulation = simulation or Simulation()
        self.setWindowTitle(f"{config.APP_NAME}  v{config.APP_VERSION}")
        self.resize(1720, 980)
        self.setMinimumSize(1180, 720)
        self._frame_counter = 0
        self._selected_run: str | None = None
        self._selected_station: Station | None = None
        #: Suppresses tab-change handling until the window is fully built;
        #: adding the first tab emits ``currentChanged`` before the docks exist.
        self._ready = False

        self._build_central()
        self._build_docks()
        self._build_menu()
        self._connect()
        self._install_tooltip_providers()
        self._ready = True
        self._start_loop()

        self.simulation.rebuild()
        for panel in self.panels:
            panel.apply_frame(self.simulation.frame)
        self._update_roster_title()
        self._refresh_slow()
        # Fitting needs a realised widget size, so defer to the event loop.
        QTimer.singleShot(0, self._fit_active)

    def _fit_active(self) -> None:
        panel = self.panel
        if panel is not None:
            panel.ensure_fitted()

    def _build_central(self) -> None:
        day_types = [
            (key, self.simulation.timetable.day_type_label(key))
            for key in self.simulation.timetable.day_type_keys
        ]

        self.header = HeaderBar(day_types)
        self._install_bar(self.header, Qt.TopToolBarArea)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._build_tabs()
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.status = StatusBar(self.simulation.network)
        self._install_bar(self.status, Qt.BottomToolBarArea)

    def _install_bar(self, widget: QWidget, area) -> None:
        """Mount a fixed strip across the full width of the window."""
        bar = QToolBar()
        bar.setObjectName(f"{widget.objectName()}Container")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(widget)
        bar.setStyleSheet("QToolBar { border: none; padding: 0; spacing: 0; }")
        self.addToolBar(area, bar)

    def _build_tabs(self) -> None:
        """One overview tab showing every line, plus a tab per line."""
        self.panels: list[NetworkPanel] = []
        all_ids = [line.id for line in self.simulation.network]

        overview = self._add_panel("Network", all_ids)
        overview_index = self.tabs.indexOf(overview)
        self.tabs.setTabToolTip(overview_index, "All lines")
        self.tabs.tabBar().setTabTextColor(overview_index, theme.TEXT)

        for line in self.simulation.network:
            panel = self._add_panel(line.name, [line.id])
            index = self.tabs.indexOf(panel)
            self.tabs.setTabToolTip(index, f"{line.name}  -  {line.first.name} to {line.last.name}")
            self.tabs.tabBar().setTabTextColor(index, QColor(line.colour))

    def _add_panel(self, title: str, line_ids: list[str]) -> NetworkPanel:
        panel = NetworkPanel(self.simulation.network, line_ids)
        panel.station_clicked.connect(self._on_station_clicked)
        panel.train_clicked.connect(self._on_train_selected)
        self.tabs.addTab(panel, title)
        self.panels.append(panel)
        return panel

    @property
    def panel(self) -> NetworkPanel:
        """The panel the operator is currently looking at."""
        return self.tabs.currentWidget()

    @property
    def scene(self) -> NetworkScene:
        return self.panel.scene

    @property
    def view(self) -> NetworkView:
        return self.panel.view

    @property
    def active_line_ids(self) -> list[str] | None:
        """Lines shown in the active tab, or ``None`` on the overview tab."""
        panel = self.panel
        if panel is None or len(panel.line_ids) == len(self.simulation.network):
            return None
        return panel.line_ids

    def _build_docks(self) -> None:
        self.line_panel = LinePanel(self.simulation.network)
        left = QDockWidget("LINE STATUS")
        left.setObjectName("LineStatusDock")
        left.setWidget(self.line_panel)
        left.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        left.setMinimumWidth(300)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)
        self.dock_lines = left

        self.station_panel = StationPanel()
        right = QDockWidget("STATION DETAIL")
        right.setObjectName("StationDetailDock")
        right.setWidget(self.station_panel)
        right.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        right.setMinimumWidth(330)
        self.addDockWidget(Qt.RightDockWidgetArea, right)
        self.dock_station = right

        self.train_panel = TrainPanel()
        train_dock = QDockWidget("TRAIN DETAIL")
        train_dock.setObjectName("TrainDetailDock")
        train_dock.setWidget(self.train_panel)
        train_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        train_dock.setMinimumWidth(330)
        self.addDockWidget(Qt.RightDockWidgetArea, train_dock)
        self.dock_train = train_dock
        # Stack the two detail docks in one right-hand column so that clicking
        # anything on the diagram always answers in the same place.
        self.splitDockWidget(right, train_dock, Qt.Vertical)

        self.train_table = TrainTable(self.simulation.network)
        bottom = QDockWidget("LIVE TRAIN ROSTER")
        bottom.setObjectName("TrainRosterDock")
        bottom.setWidget(self.train_table)
        bottom.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        bottom.setMinimumHeight(190)
        self.addDockWidget(Qt.BottomDockWidgetArea, bottom)
        self.dock_trains = bottom

    def _build_menu(self) -> None:
        view_menu = self.menuBar().addMenu("&View")
        for text, shortcut, handler in (
            ("Zoom &In", QKeySequence.ZoomIn, self._zoom_in),
            ("Zoom &Out", QKeySequence.ZoomOut, self._zoom_out),
            ("&Fit Network", "0", self._fit),
            ("Reset &Zoom", "Ctrl+0", self._reset_zoom),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(handler)
            view_menu.addAction(action)

        view_menu.addSeparator()
        for position in range(self.tabs.count()):
            action = QAction(f"Tab: {self.tabs.tabText(position)}", self)
            action.setShortcut(f"Ctrl+{position + 1}")
            action.triggered.connect(lambda _=False, i=position: self.tabs.setCurrentIndex(i))
            view_menu.addAction(action)

        view_menu.addSeparator()
        view_menu.addAction(self.dock_lines.toggleViewAction())
        view_menu.addAction(self.dock_station.toggleViewAction())
        view_menu.addAction(self.dock_train.toggleViewAction())
        view_menu.addAction(self.dock_trains.toggleViewAction())

        sim_menu = self.menuBar().addMenu("&Simulation")
        pause = QAction("&Pause / Resume", self)
        pause.setShortcut(Qt.Key_Space)
        pause.triggered.connect(self._toggle_running)
        sim_menu.addAction(pause)

        for text, shortcut, delta in (
            ("Back 5 minutes", "Left", -300),
            ("Forward 5 minutes", "Right", 300),
            ("Back 1 hour", "Ctrl+Left", -3600),
            ("Forward 1 hour", "Ctrl+Right", 3600),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(lambda _=False, d=delta: self._nudge(d))
            sim_menu.addAction(action)

        sim_menu.addSeparator()
        live = QAction("Resync to &Live", self)
        live.setShortcut("Ctrl+L")
        live.triggered.connect(self._resync)
        sim_menu.addAction(live)

    def _connect(self) -> None:
        self.header.play_toggled.connect(self._set_running)
        self.header.speed_changed.connect(self._set_speed)
        self.header.seek_requested.connect(self._seek)
        self.header.resync_requested.connect(self._resync)
        self.header.day_type_changed.connect(self._set_day_type)
        self.header.zoom_in_requested.connect(self._zoom_in)
        self.header.zoom_out_requested.connect(self._zoom_out)
        self.header.fit_requested.connect(self._fit)

        self.train_table.train_selected.connect(self._on_train_selected)

    def _zoom_in(self) -> None:
        self.view.zoom_in()

    def _zoom_out(self) -> None:
        self.view.zoom_out()

    def _fit(self) -> None:
        self.view.fit_all()

    def _reset_zoom(self) -> None:
        self.view.reset_zoom()

    def _install_tooltip_providers(self) -> None:
        """Give every station marker in every tab a lazy arrivals provider.

        Computing arrivals for ~85 markers costs several milliseconds, so it is
        done on hover instead of on every frame.
        """
        for panel in self.panels:
            for line in panel.network:
                line_item = panel.scene.line_item(line.id)
                for station in line:
                    line_item.station_item(station.index).tooltip_provider = self._station_tooltip

    def _start_loop(self) -> None:
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(config.FRAME_INTERVAL_MS)
        self._timer.timeout.connect(self._on_frame)
        self._timer.start()

    def _on_frame(self) -> None:
        self._frame_counter += 1
        frame = self.simulation.step()

        active = self.panel
        text_tick = self._frame_counter % self.TEXT_REFRESH_FRAMES == 0

        # Only the visible tab is rendered; the others are flagged so they
        # catch up the moment they are selected.
        for panel in self.panels:
            if panel is active:
                panel.apply_frame(frame, update_headers=text_tick)
            else:
                panel.mark_dirty()

        if text_tick:
            self.header.update_frame(frame)
            self.status.update_frame(
                frame, self.simulation.day_type_label, active.zoom, self.active_line_ids
            )
            # Countdowns must tick visibly, so this rides the text cadence
            # rather than the slower roster cadence.
            if self._selected_station is not None:
                self._refresh_station_panel()
            if self._selected_run is not None:
                self._refresh_train_panel()

        if self._frame_counter % self.SLOW_REFRESH_FRAMES == 0:
            self._refresh_slow()

    def _refresh_slow(self) -> None:
        """Update widgets that do not need to run at the full frame rate."""
        frame = self.simulation.frame
        line_ids = self.active_line_ids
        self.line_panel.update_frame(frame, self.simulation, line_ids)
        self.train_table.refresh(self.simulation.all_trains_sorted(line_ids))

    def _on_tab_changed(self, index: int) -> None:
        """Bring a newly selected tab up to date and rescope the panels."""
        if not self._ready:
            return
        panel = self.tabs.widget(index)
        if panel is None:
            return
        panel.ensure_fitted()
        if panel.is_dirty:
            panel.apply_frame(self.simulation.frame, update_headers=True)
        self._refresh_slow()
        frame = self.simulation.frame
        self.status.update_frame(
            frame, self.simulation.day_type_label, panel.zoom, self.active_line_ids
        )
        self._update_roster_title()

    def _update_roster_title(self) -> None:
        line_ids = self.active_line_ids
        if line_ids is None:
            self.dock_trains.setWindowTitle("LIVE TRAIN ROSTER  -  ALL LINES")
        else:
            names = ", ".join(self.simulation.network.line(lid).name.upper() for lid in line_ids)
            self.dock_trains.setWindowTitle(f"LIVE TRAIN ROSTER  -  {names}")

    def _station_tooltip(self, station: Station) -> str:
        """Build the next-arrivals block for one station, on demand."""
        line = self.simulation.network.line(station.line_id)
        trains = self.simulation.frame.trains.get(station.line_id, ())
        arrivals = []
        for train in trains:
            eta = train.eta_to(station.index)
            if eta is not None:
                arrivals.append((train, eta))
        arrivals.sort(key=lambda pair: pair[1])
        return self._arrivals_html(line, arrivals[: config.TOOLTIP_ARRIVALS])

    def _arrivals_html(self, line, arrivals) -> str:
        if not arrivals:
            return f"<span style='color:{theme.HEX['text_dim']}'>No approaching trains</span>"
        rows = ["<b>Next arrivals</b>"]
        now = self.simulation.clock.seconds
        for train, eta in arrivals:
            dest = line.at(train.destination_index).name
            badge = (
                f" <span style='color:{theme.HEX['warn']}'>[ST]</span>" if train.short_turn else ""
            )
            rows.append(
                f"<span style='color:{line.colour}'>&#9632;</span> "
                f"{int(eta // 60):d}m {int(eta % 60):02d}s &rarr; {dest}"
                f" <span style='color:{theme.HEX['text_dim']}'>({format_hhmm(now + eta)})</span>{badge}"
            )
        return "<br>".join(rows)

    def _set_running(self, running: bool) -> None:
        self.simulation.clock.set_running(running)

    def _toggle_running(self) -> None:
        running = self.simulation.clock.toggle()
        self.header.set_running(running)

    def _set_speed(self, speed: float) -> None:
        self.simulation.clock.set_speed(speed)

    def _seek(self, seconds: int) -> None:
        self.simulation.clock.seek(seconds)
        self.simulation.rebuild()
        self._refresh_slow()

    def _nudge(self, delta: int) -> None:
        self.simulation.clock.nudge(delta)
        self.simulation.rebuild()
        self._refresh_slow()

    def _resync(self) -> None:
        self.simulation.clock.resync()
        self.header.set_running(True)
        self.header.set_speed(1.0)
        self.simulation.rebuild()
        self._refresh_slow()

    def _set_day_type(self, day_type) -> None:
        self.simulation.set_day_type(day_type)
        self.simulation.rebuild()
        self._refresh_slow()

    def _on_station_clicked(self, station: Station) -> None:
        panel = self.panel
        if panel is None or not panel.has_line(station.line_id):
            return
        self._select_station(station)
        line_name = self.simulation.network.line(station.line_id).name
        self.statusBar_message(f"{station.name} [{station.code}] on {line_name}")

    def _select_station(self, station: Station) -> None:
        """Make ``station`` the subject of the detail panel and highlight it."""
        previous = self._selected_station
        self._selected_station = station
        for p in self.panels:
            if previous is not None and p.has_line(previous.line_id):
                p.scene.line_item(previous.line_id).station_item(previous.index).set_highlight(
                    False
                )
            if p.has_line(station.line_id):
                p.scene.line_item(station.line_id).station_item(station.index).set_highlight(True)
        self._refresh_station_panel()

    def _refresh_station_panel(self) -> None:
        """Recompute the detail board for the selected station."""
        station = self._selected_station
        if station is None:
            self.station_panel.show_placeholder()
            return
        board = self.simulation.board_for(station)
        self.station_panel.update_board(board, self.simulation.clock.seconds)

    def _refresh_train_panel(self) -> None:
        """Re-find the selected run and update its readout.

        The run is looked up by identifier every refresh rather than holding a
        reference, because train states are rebuilt from scratch each frame and
        the selected run eventually leaves the network entirely.
        """
        run_id = self._selected_run
        if run_id is None:
            self.train_panel.show_placeholder()
            return
        for line_id, trains in self.simulation.frame.trains.items():
            for train in trains:
                if train.run_id == run_id:
                    self.train_panel.update_train(
                        train,
                        self.simulation.network.line(line_id),
                        self.simulation.clock.seconds,
                    )
                    return
        self.train_panel.show_finished()

    def _on_train_selected(self, train: TrainState | None) -> None:
        """Highlight a train and centre whichever tab can show it."""
        if train is None:
            return
        self._selected_run = train.run_id
        panel = self.panel
        if panel is None or not panel.has_line(train.line_id):
            panel = next((p for p in self.panels if p.has_line(train.line_id)), None)
            if panel is None:
                return
            self.tabs.setCurrentWidget(panel)

        for other in self.panels:
            other.scene.set_selected_run(train.run_id if other is panel else None)

        line_item = panel.scene.line_item(train.line_id)
        x = line_item.x_for_index(train.position)
        y = line_item.y_for_direction(train.direction)
        panel.view.focus_on(line_item.mapToScene(x, y))
        self._refresh_train_panel()
        self.statusBar_message(f"{train.run_label} - {train.service_label}")

    def statusBar_message(self, text: str) -> None:
        self.setWindowTitle(f"{config.APP_NAME}  v{config.APP_VERSION}   -   {text}")

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
