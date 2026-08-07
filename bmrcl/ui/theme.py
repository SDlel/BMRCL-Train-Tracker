"""Dark operations-room theme: palette, colours and global stylesheet."""

from __future__ import annotations

import contextlib

from PySide6.QtGui import QColor, QFont, QPalette

# True black, so OLED panels switch pixels off entirely.
BG_DEEP = QColor("#000000")
BG_BASE = QColor("#000000")
BG_PANEL = QColor("#0a0a0a")
BG_RAISED = QColor("#141414")
GRID = QColor("#101010")
BORDER = QColor("#242424")

TEXT = QColor("#f2f2f2")
TEXT_DIM = QColor("#8a8a8a")
TEXT_FAINT = QColor("#565656")

ACCENT = QColor("#ffffff")
OK = QColor("#37d67a")
WARN = QColor("#f5a524")
ALERT = QColor("#f2555a")

TRACK_BASE = QColor("#1a1a1a")
STATION_FILL = QColor("#000000")
SHORT_TURN = QColor("#f5a524")

HEX = {
    "bg_deep": BG_DEEP.name(),
    "bg_base": BG_BASE.name(),
    "bg_panel": BG_PANEL.name(),
    "bg_raised": BG_RAISED.name(),
    "border": BORDER.name(),
    "text": TEXT.name(),
    "text_dim": TEXT_DIM.name(),
    "text_faint": TEXT_FAINT.name(),
    "accent": ACCENT.name(),
    "ok": OK.name(),
    "warn": WARN.name(),
    "alert": ALERT.name(),
    "bg_hover": "#1c1c1c",
    "on_accent": "#000000",
}

UI_FAMILIES = ["Arial", "Helvetica Neue", "Helvetica", "Liberation Sans", "sans-serif"]
MONO_FAMILIES = UI_FAMILIES
MONO_CSS = "Arial, Helvetica, sans-serif"


def mono_font(size: int = 10, bold: bool = False) -> QFont:
    """Font for times, codes and telemetry.

    Arial is proportional, so digits would jitter as a clock or counter ticks.
    Tabular figures are requested where the Qt build supports the OpenType
    feature, which keeps every digit the same advance width.
    """
    font = QFont()
    font.setFamilies(MONO_FAMILIES)
    font.setPointSize(size)
    font.setBold(bold)
    _apply_tabular_figures(font)
    return font


def _apply_tabular_figures(font: QFont) -> None:
    """Make digit runs stable so clocks and counters do not jitter.

    Arial's digits are already equal width; what shifts a ticking readout is
    kerning between glyph pairs. Disabling kerning fixes the width of strings
    like ``18:38:11``. The ``tnum`` feature is also requested where the Qt
    build supports it, for fonts whose digits are proportional.
    """
    font.setKerning(False)
    with contextlib.suppress(AttributeError, TypeError, ValueError):  # Qt < 6.7
        font.setFeature(QFont.Tag("tnum"), 1)


def ui_font(size: int = 10, bold: bool = False) -> QFont:
    """Return the general user-interface font."""
    font = QFont()
    font.setFamilies(UI_FAMILIES)
    font.setPointSize(size)
    font.setBold(bold)
    return font


def apply_palette(app) -> None:
    """Force a dark palette regardless of the host desktop theme."""
    palette = QPalette()
    palette.setColor(QPalette.Window, BG_BASE)
    palette.setColor(QPalette.WindowText, TEXT)
    palette.setColor(QPalette.Base, BG_PANEL)
    palette.setColor(QPalette.AlternateBase, BG_RAISED)
    palette.setColor(QPalette.ToolTipBase, BG_RAISED)
    palette.setColor(QPalette.ToolTipText, TEXT)
    palette.setColor(QPalette.Text, TEXT)
    palette.setColor(QPalette.Button, BG_RAISED)
    palette.setColor(QPalette.ButtonText, TEXT)
    palette.setColor(QPalette.Highlight, ACCENT)
    palette.setColor(QPalette.HighlightedText, QColor("#000000"))
    palette.setColor(QPalette.PlaceholderText, TEXT_FAINT)
    palette.setColor(QPalette.Disabled, QPalette.Text, TEXT_FAINT)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, TEXT_FAINT)
    app.setPalette(palette)
    app.setStyle("Fusion")


STYLESHEET = """
QWidget {{
    background: {bg_base};
    color: {text};
    font-family: Arial, Helvetica, sans-serif;
}}
QMainWindow::separator {{
    background: {border};
    width: 1px;
    height: 1px;
}}
QFrame#HeaderBar, QFrame#StatusBar {{
    background: {bg_panel};
    border: none;
}}
QFrame#HeaderBar {{
    border-bottom: 1px solid {border};
}}
QFrame#StatusBar {{
    border-top: 1px solid {border};
}}
QLabel#Brand {{
    color: {text};
    letter-spacing: 2px;
}}
QLabel#BrandSub {{
    color: {text_dim};
    letter-spacing: 3px;
}}
QLabel#Clock {{
    color: {accent};
    letter-spacing: 2px;
}}
QLabel#ClockDate, QLabel#StatusText {{
    color: {text_dim};
}}
QLabel.Metric {{
    color: {text_dim};
}}
QPushButton {{
    background: {bg_raised};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 5px 12px;
    color: {text};
}}
QPushButton:hover {{
    background: {bg_hover};
    border-color: {text_dim};
    color: {text};
}}
QPushButton:pressed {{
    background: {bg_deep};
}}
QPushButton:checked {{
    background: {accent};
    border-color: {accent};
    color: {on_accent};
    font-weight: bold;
}}
QPushButton:checked:hover {{
    background: {text};
    color: {on_accent};
}}
QPushButton:disabled {{
    color: #4a5768;
    border-color: #1c2531;
}}
QComboBox, QTimeEdit, QLineEdit {{
    background: {bg_raised};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: {accent};
    selection-color: {on_accent};
}}
QComboBox:hover, QTimeEdit:hover, QLineEdit:hover {{
    border-color: {text_dim};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background: {bg_raised};
    border: 1px solid {border};
    selection-background-color: {accent};
    selection-color: {on_accent};
    outline: none;
}}
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {border};
    background: {bg_base};
}}
QTabBar {{
    background: {bg_panel};
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: {bg_panel};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 20px;
    margin: 0;
    font-size: 10pt;
    font-weight: bold;
    color: {text_dim};
}}
QTabBar::tab:hover {{
    background: {bg_raised};
}}
QTabBar::tab:selected {{
    background: {bg_base};
    border-bottom: 2px solid {accent};
}}
QDockWidget {{
    titlebar-close-icon: none;
    color: {text_dim};
}}
QDockWidget::title {{
    background: {bg_panel};
    border-bottom: 1px solid {border};
    padding: 7px 10px;
    text-align: left;
}}
QTableView {{
    background: {bg_base};
    alternate-background-color: #0a0a0a;
    gridline-color: #1a1a1a;
    border: none;
    selection-background-color: #262626;
    selection-color: {text};
    outline: none;
}}
QHeaderView::section {{
    background: {bg_panel};
    color: {text_dim};
    border: none;
    border-right: 1px solid #1a1a1a;
    border-bottom: 1px solid {border};
    padding: 5px 6px;
    font-weight: bold;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {bg_base};
    border: none;
}}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{
    background: #2e2e2e;
    border-radius: 5px;
    min-height: 26px;
    min-width: 26px;
}}
QScrollBar::handle:hover {{ background: #454545; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{
    background: {bg_raised};
    color: {text};
    border: 1px solid {border};
    padding: 6px 8px;
}}
QMenuBar {{
    background: {bg_panel};
    border-bottom: 1px solid {border};
}}
QMenuBar::item:selected {{
    background: {bg_raised};
}}
QMenu {{
    background: {bg_raised};
    border: 1px solid {border};
}}
QMenu::item:selected {{
    background: {accent};
    color: {on_accent};
}}
""".format(**HEX)
