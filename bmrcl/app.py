"""Application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import config
from .core.simulation import Simulation
from .ui import theme
from .ui.main_window import MainWindow


def create_app(argv: list[str] | None = None) -> QApplication:
    """Create and configure the QApplication with the dark theme applied."""
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName(config.APP_ORG)
    app.setApplicationVersion(config.APP_VERSION)
    theme.apply_palette(app)
    app.setStyleSheet(theme.STYLESHEET)
    return app


def main(argv: list[str] | None = None) -> int:
    """Entry point: build the simulation, show the dashboard, run the loop."""
    app = create_app(argv)
    simulation = Simulation()
    window = MainWindow(simulation)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
