"""Tests for the text-aware sizing helpers."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from bmrcl.ui import theme
from bmrcl.ui.metrics import fit_minimum, fit_width, text_width


@pytest.fixture
def button(qapp) -> QPushButton:
    widget = QPushButton()
    widget.setFont(theme.mono_font(8))
    return widget


def test_text_width_returns_the_widest_candidate(button: QPushButton) -> None:
    assert text_width(button, "x", "xxxxxxxx") == text_width(button, "xxxxxxxx")


def test_text_width_of_nothing_is_zero(button: QPushButton) -> None:
    assert text_width(button) == 0


def test_fit_width_accommodates_every_label(button: QPushButton) -> None:
    labels = ("0.5x", "1x", "2x", "5x", "20x")
    fit_width(button, *labels)
    for label in labels:
        button.setText(label)
        assert button.sizeHint().width() <= button.width(), f"{label} is clipped"


def test_fit_width_is_stable_across_labels(qapp) -> None:
    """A row of buttons sized from the same candidates must all match."""
    labels = ("0.5x", "1x", "20x")
    widths = set()
    for label in labels:
        widget = QPushButton(label)
        widget.setFont(theme.mono_font(8))
        widths.add(fit_width(widget, *labels))
    assert len(widths) == 1


def test_fit_width_respects_the_size_hint_floor(qapp) -> None:
    """Composite widgets reserve internal space text measurement cannot see."""
    from PySide6.QtWidgets import QTimeEdit

    widget = QTimeEdit()
    widget.setFont(theme.mono_font(9))
    applied = fit_width(widget, "00:00", padding=0)
    assert applied >= widget.sizeHint().width()


def test_fit_width_honours_an_explicit_minimum(button: QPushButton) -> None:
    assert fit_width(button, "+", padding=0, minimum=90) == 90


def test_fit_minimum_allows_growth(qapp) -> None:
    label = QLabel()
    label.setFont(theme.ui_font(9))
    fit_minimum(label, "short")
    assert label.minimumWidth() > 0
    assert label.maximumWidth() > label.minimumWidth()
