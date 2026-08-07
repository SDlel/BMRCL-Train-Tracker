"""Text-aware sizing helpers.

Hardcoded pixel widths break as soon as the font, the DPI or a label changes -
which is exactly how ``0.5x`` and ``20x`` ended up clipped inside 42 px
buttons. These helpers measure the real rendered text instead, so a control is
always wide enough for every state it can display.
"""

from __future__ import annotations

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QWidget

BUTTON_PADDING = 26

COMBO_PADDING = 40

FIELD_PADDING = 22

SPACING_TIGHT = 4
SPACING_GROUP = 10
SPACING_SECTION = 18


def text_width(widget: QWidget, *candidates: str) -> int:
    """Widest rendering of ``candidates`` using ``widget``'s own font."""
    metrics = QFontMetrics(widget.font())
    return max((metrics.horizontalAdvance(text) for text in candidates), default=0)


def fit_width(
    widget: QWidget, *candidates: str, padding: int = BUTTON_PADDING, minimum: int = 0
) -> int:
    """Pin ``widget`` to the width of its widest possible label.

    Fixing the width - rather than letting it grow - keeps a row of controls
    from reflowing when their text changes (``PAUSE`` becoming ``RESUME``, for
    instance).

    The widget's own ``sizeHint`` is respected as a floor, because composite
    controls such as ``QTimeEdit`` reserve internal space for spin buttons that
    a pure text measurement cannot see.

    Returns:
        The width that was applied.
    """
    width = max(
        text_width(widget, *candidates) + padding,
        widget.sizeHint().width(),
        minimum,
    )
    widget.setFixedWidth(width)
    return width


def fit_minimum(widget: QWidget, *candidates: str, padding: int = BUTTON_PADDING) -> int:
    """Give ``widget`` a floor width but allow it to grow.

    Used for controls whose content is not fully known up front, such as a
    combo box populated from data.
    """
    width = text_width(widget, *candidates) + padding
    widget.setMinimumWidth(width)
    return width
