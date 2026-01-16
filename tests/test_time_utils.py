from datetime import datetime

from backend.time_utils import now_poland_iso, now_poland_naive


def test_now_poland_naive_is_naive():
    dt = now_poland_naive()
    assert dt.tzinfo is None


def test_now_poland_iso_parseable_no_microseconds():
    iso_value = now_poland_iso()
    dt = datetime.fromisoformat(iso_value)
    assert dt.microsecond == 0
    assert dt.tzinfo is None


def test_now_poland_iso_close_to_now():
    iso_value = now_poland_iso()
    dt_from_iso = datetime.fromisoformat(iso_value)
    dt_now = now_poland_naive()
    delta = abs((dt_now - dt_from_iso).total_seconds())
    assert delta < 2

