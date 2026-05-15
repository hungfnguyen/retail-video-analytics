"""Unit tests for core.time_utils."""

from datetime import datetime, timedelta, timezone

from core.time_utils import ensure_utc, now_iso, now_utc


class TestEnsureUtc:
    def test_naive_datetime_treated_as_utc(self):
        ts = datetime(2026, 5, 11, 10, 30, 0)
        result = ensure_utc(ts)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10

    def test_aware_datetime_converted_to_utc(self):
        tz_plus7 = timezone(timedelta(hours=7))
        ts = datetime(2026, 5, 11, 10, 30, 0, tzinfo=tz_plus7)
        result = ensure_utc(ts)
        assert result.tzinfo == timezone.utc
        assert result.hour == 3  # 10 - 7 = 3

    def test_already_utc_stays_utc(self):
        ts = datetime(2026, 5, 11, 10, 30, 0, tzinfo=timezone.utc)
        result = ensure_utc(ts)
        assert result == ts


class TestNow:
    def test_now_utc_is_aware(self):
        result = now_utc()
        assert result.tzinfo is not None

    def test_now_iso_has_z_suffix(self):
        result = now_iso()
        assert "T" in result
        assert "+" in result or "Z" in result
