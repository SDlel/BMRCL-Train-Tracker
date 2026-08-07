"""Tests for timetable parsing and headway-window expansion."""

from __future__ import annotations

import pytest

from bmrcl.core.network import Network
from bmrcl.core.timetable import Timetable, Window, format_hhmm, parse_hhmm

DAY_TYPES = ("monday", "tue_fri", "saturday", "sunday")


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("00:00", 0), ("05:30", 19800), ("23:59", 86340), ("09:07:30", 32850)],
)
def test_parse_hhmm(text: str, seconds: int) -> None:
    assert parse_hhmm(text) == seconds


def test_parse_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        parse_hhmm("half past nine")


@pytest.mark.parametrize(("seconds", "text"), [(0, "00:00"), (19800, "05:30"), (86340, "23:59")])
def test_format_hhmm(seconds: int, text: str) -> None:
    assert format_hhmm(seconds) == text


def test_format_wraps_past_midnight() -> None:
    assert format_hhmm(86400 + 3600) == "01:00"


class TestWindow:
    """A window is inclusive of its start and exclusive of its end."""

    def test_expands_at_the_given_headway(self) -> None:
        window = Window(parse_hhmm("10:00"), parse_hhmm("10:30"), 10)
        assert window.departures() == [parse_hhmm(t) for t in ("10:00", "10:10", "10:20")]

    def test_end_belongs_to_the_next_window(self) -> None:
        window = Window(parse_hhmm("10:00"), parse_hhmm("10:30"), 10)
        assert parse_hhmm("10:30") not in window.departures()

    def test_closing_window_includes_the_last_train(self) -> None:
        window = Window(parse_hhmm("22:00"), parse_hhmm("22:30"), 15)
        assert window.departures(closing=True)[-1] == parse_hhmm("22:30")

    def test_fractional_headways_are_supported(self) -> None:
        window = Window(parse_hhmm("06:00"), parse_hhmm("06:22"), 5.5)
        assert len(window.departures()) == 4

    def test_zero_headway_yields_nothing(self) -> None:
        assert Window(0, 3600, 0).departures() == []


@pytest.mark.parametrize("day_type", DAY_TYPES)
def test_every_day_type_has_service(timetable: Timetable, day_type: str) -> None:
    assert timetable.total_departures(day_type) > 0


def test_weekday_mapping(timetable: Timetable) -> None:
    from datetime import date

    assert timetable.day_type_for(date(2026, 8, 3)) == "monday"
    assert timetable.day_type_for(date(2026, 8, 5)) == "tue_fri"
    assert timetable.day_type_for(date(2026, 8, 8)) == "saturday"
    assert timetable.day_type_for(date(2026, 8, 9)) == "sunday"


def test_monday_purple_starts_earlier_than_tue_fri(timetable: Timetable) -> None:
    monday = timetable.plan("purple", "monday").first_departure
    tue_fri = timetable.plan("purple", "tue_fri").first_departure
    assert monday == parse_hhmm("04:15")
    assert monday < tue_fri


def test_sunday_service_starts_at_seven(timetable: Timetable) -> None:
    for line_id in ("purple", "green"):
        assert timetable.plan(line_id, "sunday").first_departure == parse_hhmm("07:00")


def test_sunday_is_quieter_than_a_weekday(timetable: Timetable) -> None:
    assert timetable.total_departures("sunday") < timetable.total_departures("tue_fri")


def test_purple_short_loops_are_encoded(timetable: Timetable) -> None:
    shorts = [s for s in timetable.services("purple", "monday") if s.is_short_turn]
    assert len(shorts) >= 8
    ids = {s.id for s in shorts}
    assert "PPL-KGM-PTA-AM" in ids
    assert "PPL-MGR-CHG-PM" in ids


def test_explicit_departures_are_used_verbatim(timetable: Timetable) -> None:
    service = next(s for s in timetable.services("purple", "monday") if s.id == "PPL-KGM-PTA-AM")
    assert service.departure_times()[0] == parse_hhmm("08:58")


def test_departures_are_sorted_and_unique(timetable: Timetable) -> None:
    for day_type in DAY_TYPES:
        for line_id in ("purple", "green", "yellow"):
            times = [d.time for d in timetable.plan(line_id, day_type).departures]
            assert times == sorted(times)


def test_services_reference_real_stations(timetable: Timetable, network: Network) -> None:
    for day_type in DAY_TYPES:
        for line in network:
            for service in timetable.services(line.id, day_type):
                assert line.has(service.origin)
                assert line.has(service.destination)
                assert service.origin != service.destination


def test_plans_are_memoised(timetable: Timetable) -> None:
    assert timetable.plan("green", "sunday") is timetable.plan("green", "sunday")


def test_slice_is_half_open(timetable: Timetable) -> None:
    plan = timetable.plan("yellow", "tue_fri")
    window = plan.slice(parse_hhmm("09:00"), parse_hhmm("10:00"))
    assert all(parse_hhmm("09:00") <= d.time < parse_hhmm("10:00") for d in window)


def test_last_train_of_the_day_is_not_dropped(timetable: Timetable) -> None:
    """Regression: an exclusive final window silently deleted the last train."""
    plan = timetable.plan("yellow", "tue_fri")
    assert plan.last_departure == parse_hhmm("23:55")
