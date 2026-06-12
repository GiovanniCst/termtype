"""Unit tests for the pure helpers in game/title.py (no Screen)."""
from __future__ import annotations

import random
from pathlib import Path

from termtype.game.title import (
    TITLE_TEXT,
    COPYRIGHT_LINE,
    CREDITS_LINES,
    MAX_BACKDROP_WORDS,
    Backdrop,
    crawl_visible,
    header_logo,
    logo_drop_row,
    splash_logo,
    step_backdrop,
)


# ── logo_drop_row ────────────────────────────────────────────────────────


def test_logo_drop_endpoints():
    assert logo_drop_row(0.0, 5, 20) == 5
    assert logo_drop_row(1.0, 5, 20) == 20


def test_logo_drop_clamps():
    assert logo_drop_row(-3.0, 5, 20) == 5
    assert logo_drop_row(9.0, 5, 20) == 20


def test_logo_drop_monotonic_and_accelerating():
    rows = [logo_drop_row(i / 10.0, 0, 100) for i in range(11)]
    # non-decreasing
    assert all(b >= a for a, b in zip(rows, rows[1:]))
    # accelerating: second half covers at least as much ground as the first
    assert (rows[-1] - rows[5]) >= (rows[5] - rows[0])


# ── step_backdrop ────────────────────────────────────────────────────────


def test_backdrop_spawns_and_caps():
    rng = random.Random(42)
    pool = ["alpha", "beta", "gamma", "parola", "ciao"]
    bd = Backdrop()
    width, water = 80, 22
    # Run many frames; words should appear and never exceed the cap.
    for _ in range(2000):
        step_backdrop(bd, pool, 1 / 30.0, width, water, rng)
        assert len(bd.words) <= MAX_BACKDROP_WORDS
    assert bd.words  # at least some on screen


def test_backdrop_x_within_bounds():
    rng = random.Random(7)
    pool = ["alpha", "beta", "gamma", "intrepido"]
    bd = Backdrop()
    width, water = 80, 22
    for _ in range(500):
        step_backdrop(bd, pool, 1 / 30.0, width, water, rng)
        for w in bd.words:
            assert 0 <= w.x <= width - len(w.text)


def test_backdrop_drowns_at_water():
    rng = random.Random(1)
    bd = Backdrop(words=[], spawn_in=999.0)  # suppress spawning
    from termtype.game.entities import FallingWord
    bd.words.append(FallingWord(text="sink", x=3.0, row=21.99, speed=2.0))
    step_backdrop(bd, ["sink"], 1 / 30.0, 80, 22, rng)
    # 21.99 + 2.0/30 = 22.06 ≥ water_row 22 → drowned/removed
    assert bd.words == []


# ── crawl_visible ────────────────────────────────────────────────────────


def test_crawl_nothing_visible_at_zero_offset():
    assert crawl_visible(["a", "b", "c"], 0.0, 24) == []


def test_crawl_enters_rises_exits():
    lines = ["one", "two", "three"]
    h = 10
    seen_rows = set()
    exited = False
    for step in range(40):
        vis = crawl_visible(lines, step * 1.0, h)
        for text, y in vis:
            assert 0 <= y < h
            seen_rows.add((text, y))
        if step > 20 and not vis:
            exited = True
    assert ("one", 0) in seen_rows or ("one", 1) in seen_rows  # reached the top
    assert exited  # fully scrolled off


def test_crawl_skips_blank_lines():
    vis = crawl_visible(["x", "", "y"], 5.0, 10)
    texts = [t for t, _ in vis]
    assert "" not in texts


# ── logos ────────────────────────────────────────────────────────────────


def test_splash_logo_fits_80():
    lines = splash_logo(80)
    assert lines
    assert all(len(ln) <= 80 for ln in lines)


def test_header_logo_fits_80():
    lines = header_logo(80)
    assert lines
    assert all(len(ln) <= 80 for ln in lines)


def test_logo_plain_fallback_on_tiny_width():
    assert splash_logo(10) == [TITLE_TEXT]
    assert header_logo(10) == [TITLE_TEXT]


# ── license consistency ──────────────────────────────────────────────────


def test_credits_copyright_matches_license_file():
    license_path = Path(__file__).resolve().parents[1] / "LICENSE"
    text = license_path.read_text(encoding="utf-8")
    license_line = next(
        ln.strip() for ln in text.splitlines() if ln.strip().startswith("Copyright (c)")
    )
    assert license_line == COPYRIGHT_LINE
    assert COPYRIGHT_LINE in CREDITS_LINES
