"""Tests for the formatting helpers."""

from __future__ import annotations

import pytest

from sarplot.formatting import (
    format_bytes,
    format_cpu_time,
    format_percent,
    format_uptime,
)


class TestFormatBytes:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "0.0B"),
            (1, "1.0B"),
            (1023, "1023.0B"),
            (1024, "1.0K"),
            (1536, "1.5K"),
            (1024**2, "1.0M"),
            (1024**3, "1.0G"),
            (1024**4, "1.0T"),
            (1024**5, "1.0P"),
            (1024**6, "1.0E"),
        ],
    )
    def test_scales_through_units(self, value, expected):
        assert format_bytes(value) == expected

    def test_enormous_values_clamp_instead_of_returning_none(self):
        """Regression: the loop fell through and implicitly returned None.

        The original implementation stopped at 'P', so anything at or above
        1 EiB produced None and blew up at the call site.
        """
        result = format_bytes(10**30)
        assert result is not None
        assert result.endswith("Y")

    def test_negative_values_keep_their_sign(self):
        assert format_bytes(-2048) == "-2.0K"

    def test_precision_is_configurable(self):
        assert format_bytes(1536, precision=3) == "1.500K"


class TestFormatCpuTime:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "00:00.00"),
            (0.5, "00:00.50"),
            (61.25, "01:01.25"),
            (599.99, "09:59.99"),
        ],
    )
    def test_renders_minutes_and_hundredths(self, seconds, expected):
        assert format_cpu_time(seconds) == expected

    def test_widens_to_hours_past_one_hour(self):
        assert format_cpu_time(3661) == "1:01:01"

    def test_negative_input_is_clamped(self):
        assert format_cpu_time(-5) == "00:00.00"


class TestFormatPercent:
    def test_rounds_to_one_decimal(self):
        assert format_percent(12.3456) == "12.3"

    def test_precision_is_configurable(self):
        assert format_percent(12.3456, precision=2) == "12.35"


class TestFormatUptime:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0, "0d 0h 0m"),
            (90, "0d 0h 1m"),
            (3600, "0d 1h 0m"),
            (90061, "1d 1h 1m"),
        ],
    )
    def test_renders_days_hours_minutes(self, seconds, expected):
        assert format_uptime(seconds) == expected

    def test_negative_input_is_clamped(self):
        assert format_uptime(-100) == "0d 0h 0m"
