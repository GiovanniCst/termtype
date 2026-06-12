"""Pure Unicode sparkline and bar-chart string builders.

PLAN §8.4, §8.9. Render-free, testable.
"""
from __future__ import annotations

from . import levels

# UTF-8 sparkline ramp (8 levels)
SPARKLINE_RAMP = "▁▂▃▄▅▆▇█"

# UTF-8 bar glyph
BAR_GLYPH = "█"

# ASCII sparkline ramp (6 levels, PLAN §8.9)
ASCII_SPARKLINE_RAMP = "_.-=+#"

# ASCII bar glyph
ASCII_BAR_GLYPH = "#"

# Gap/missing/zero glyph
GAP_GLYPH_UTF8 = " "  # distinct low glyph
GAP_GLYPH_ASCII = " "  # space, distinct from _

# Urgency gutter ramp (PLAN §8.1) — pure module-level tuple, asciimatics-free
URGENCY_GUTTER = (" ·", " !", "!!")


def sparkline(
    data: list[float],
    width: int,
    *,
    ascii_mode: bool = False,
) -> str:
    """Render a one-row sparkline from a data series.

    Args:
        data: Numeric values (may be empty).
        width: Available columns.
        ascii_mode: Use ASCII ramp instead of UTF-8.

    Returns:
        A string of exactly `width` characters.
    """
    if width <= 0:
        return ""

    ramp = ASCII_SPARKLINE_RAMP if ascii_mode else SPARKLINE_RAMP
    gap = GAP_GLYPH_ASCII if ascii_mode else GAP_GLYPH_UTF8
    n_levels = len(ramp)

    if not data:
        return gap * width

    # Decimate to available columns
    if len(data) > width:
        # Take evenly spaced samples
        step = len(data) / width
        sampled = [data[int(i * step)] for i in range(width)]
    else:
        sampled = list(data)

    # Pad with gaps if fewer than width
    while len(sampled) < width:
        sampled.append(float("nan"))

    # Normalize to [min, max]
    valid = [v for v in sampled if v == v]  # filter NaN
    if not valid:
        return gap * width

    vmin = min(valid)
    vmax = max(valid)

    # Flat-series guard
    if vmax - vmin < levels.FLAT_THRESHOLD:
        # Render as mid-level row
        mid = n_levels // 2
        return "".join(
            ramp[mid] if v == v else gap for v in sampled
        )

    # Render
    result = []
    for v in sampled:
        if v != v:  # NaN
            result.append(gap)
        else:
            idx = int((v - vmin) / (vmax - vmin) * (n_levels - 1))
            idx = max(0, min(n_levels - 1, idx))
            result.append(ramp[idx])

    return "".join(result)


def bar_chart(
    data: list[float],
    width: int,
    *,
    ascii_mode: bool = False,
) -> str:
    """One-row block-bar series for the Score / Highest-level graphs (§8.4).

    These are "vertical block-bar sparklines" — the same one-row block-ramp
    technique as sparkline (a single cell encodes each value's height), so it
    shares the implementation rather than duplicating it.
    """
    return sparkline(data, width, ascii_mode=ascii_mode)
