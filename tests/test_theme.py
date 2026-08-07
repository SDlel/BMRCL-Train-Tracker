"""Tests for the AMOLED theme and typographic stability."""

from __future__ import annotations

import pytest

from bmrcl.ui import theme


def test_background_is_true_black() -> None:
    """AMOLED panels switch pixels off only at exactly #000000."""
    assert theme.BG_BASE.name() == "#000000"
    assert theme.BG_DEEP.name() == "#000000"
    assert theme.STATION_FILL.name() == "#000000"


def test_accent_is_white() -> None:
    assert theme.ACCENT.name() == "#ffffff"


def test_no_legacy_blue_remains() -> None:
    assert "#22d3ee" not in theme.STYLESHEET
    assert "#22d3ee" not in str(theme.HEX.values())


def test_fonts_are_neutral_grotesque() -> None:
    assert theme.UI_FAMILIES[0] == "Arial"
    assert theme.MONO_FAMILIES == theme.UI_FAMILIES


@pytest.mark.parametrize("size", [8, 10, 12, 21])
def test_clock_digits_do_not_jitter(qapp, size: int) -> None:
    """Arial is proportional, so kerning must not shift a ticking readout."""
    from PySide6.QtGui import QFontMetrics

    metrics = QFontMetrics(theme.mono_font(size))
    samples = ("00:00:00", "18:38:11", "23:59:59", "11:11:11", "09:07:45")
    widths = {metrics.horizontalAdvance(text) for text in samples}
    assert len(widths) == 1, f"clock width varies at {size}pt: {widths}"


def test_numeric_font_disables_kerning(qapp) -> None:
    assert theme.mono_font(10).kerning() is False


def test_stylesheet_has_no_unresolved_placeholders() -> None:
    """Every ``{key}`` token must have been substituted from HEX."""
    import re

    # The stylesheet is already formatted, so any remaining ``{word}`` would be
    # a typo'd key. CSS braces are followed by a newline or a property, never
    # by a bare identifier and a closing brace.
    leftovers = re.findall(r"\{([a-z_]+)\}", theme.STYLESHEET)
    assert leftovers == [], f"unsubstituted placeholders: {set(leftovers)}"


def test_palette_applies_cleanly(qapp) -> None:
    from PySide6.QtGui import QPalette

    theme.apply_palette(qapp)
    palette = qapp.palette()
    assert palette.color(QPalette.Window).name() == "#000000"


def test_hex_map_covers_referenced_keys() -> None:
    for key in (
        "bg_base",
        "bg_panel",
        "text",
        "text_dim",
        "text_faint",
        "accent",
        "warn",
        "alert",
        "ok",
        "border",
        "on_accent",
    ):
        assert key in theme.HEX
