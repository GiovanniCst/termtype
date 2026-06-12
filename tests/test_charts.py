"""Tests for charts.py — sparkline and bar-chart builders."""
import pytest
from termtype.game.charts import (
    sparkline, bar_chart,
    SPARKLINE_RAMP, ASCII_SPARKLINE_RAMP,
    URGENCY_GUTTER, GAP_GLYPH_UTF8, GAP_GLYPH_ASCII,
)
from termtype.game import levels


class TestSparkline:
    def test_empty_data(self):
        result = sparkline([], 10)
        assert len(result) == 10
        assert result == GAP_GLYPH_UTF8 * 10

    def test_width_zero(self):
        assert sparkline([1, 2, 3], 0) == ""

    def test_single_value(self):
        result = sparkline([5.0], 5)
        assert len(result) == 5
        # Single value: flat series, first is mid-level, rest are gaps
        mid = SPARKLINE_RAMP[len(SPARKLINE_RAMP) // 2]
        assert result[0] == mid
        # Remaining are gap glyphs (NaN padding)
        for c in result[1:]:
            assert c == GAP_GLYPH_UTF8

    def test_normalizes_to_range(self):
        result = sparkline([0, 1, 2, 3, 4], 5)
        assert len(result) == 5
        # First should be lowest level, last should be highest
        assert result[0] == SPARKLINE_RAMP[0]
        assert result[-1] == SPARKLINE_RAMP[-1]

    def test_decimation(self):
        """More data than width should be decimated."""
        data = list(range(100))
        result = sparkline(data, 10)
        assert len(result) == 10

    def test_padding(self):
        """Less data than width should be padded with gaps."""
        result = sparkline([1, 2], 5)
        assert len(result) == 5

    def test_ascii_mode(self):
        result = sparkline([0, 1, 2], 3, ascii_mode=True)
        assert len(result) == 3
        # Should use ASCII ramp
        for c in result:
            assert c in ASCII_SPARKLINE_RAMP or c == GAP_GLYPH_ASCII


class TestFlatSeries:
    def test_flat_series_mid_level(self):
        """All same values should render as mid-level row."""
        result = sparkline([5.0, 5.0, 5.0, 5.0, 5.0], 5)
        mid = SPARKLINE_RAMP[len(SPARKLINE_RAMP) // 2]
        assert all(c == mid for c in result)

    def test_single_distinct_value(self):
        """Single distinct value (no range) should be flat mid-level."""
        result = sparkline([42.0, 42.0, 42.0, 42.0, 42.0], 5)
        mid = SPARKLINE_RAMP[len(SPARKLINE_RAMP) // 2]
        assert all(c == mid for c in result)


class TestASCII:
    def test_ascii_ramp_steps_distinct(self):
        """ASCII 6-level ramp steps are pairwise distinct."""
        for i in range(len(ASCII_SPARKLINE_RAMP)):
            for j in range(i + 1, len(ASCII_SPARKLINE_RAMP)):
                assert ASCII_SPARKLINE_RAMP[i] != ASCII_SPARKLINE_RAMP[j]

    def test_ascii_gap_differs_from_lowest(self):
        """ASCII gap glyph (space) differs from _ (lowest real glyph)."""
        assert GAP_GLYPH_ASCII != ASCII_SPARKLINE_RAMP[0]

    def test_utf8_ramp_length(self):
        assert len(SPARKLINE_RAMP) == 8

    def test_ascii_ramp_length(self):
        assert len(ASCII_SPARKLINE_RAMP) == 6


class TestUrgencyGutter:
    def test_non_blank(self):
        """All three urgency states are non-blank."""
        for state in URGENCY_GUTTER:
            assert state.strip() != ""

    def test_pairwise_distinct(self):
        """All three urgency states are pairwise distinct."""
        assert len(set(URGENCY_GUTTER)) == 3

    def test_constant_width(self):
        """All urgency states are exactly 2 characters wide."""
        for state in URGENCY_GUTTER:
            assert len(state) == 2


class TestBarChart:
    def test_empty_data(self):
        result = bar_chart([], 10)
        assert len(result) == 10

    def test_normalizes(self):
        result = bar_chart([0, 1, 2, 3, 4], 5)
        assert len(result) == 5

    def test_ascii_mode(self):
        result = bar_chart([0, 1, 2], 3, ascii_mode=True)
        assert len(result) == 3
