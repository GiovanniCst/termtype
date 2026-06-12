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
    crawl_done,
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


def test_crawl_done_boundary():
    total, h = 18, 24
    # not done while content is still on/below the top edge
    assert not crawl_done(0.0, total, h)
    assert not crawl_done(float(h + total - 1), total, h)  # last line at y=0
    # done once the last line has risen above the top
    assert crawl_done(float(h + total), total, h)
    assert crawl_done(9999.0, total, h)


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


def test_backdrop_words_get_varied_colours():
    from termtype.game.title import _WORD_PALETTE
    rng = random.Random(11)
    pool = ["alpha", "beta", "gamma", "delta", "omega", "parola", "ciao"]
    bd = Backdrop()
    colours, speeds = set(), set()
    for _ in range(400):
        step_backdrop(bd, pool, 1 / 30.0, 80, 22, rng)
        for w in bd.words:
            assert w.colour in _WORD_PALETTE
            colours.add(w.colour)
            speeds.add(round(w.speed, 2))
    assert len(colours) >= 3       # confetti, not one flat colour
    assert max(speeds) - min(speeds) > 0.8   # speeds genuinely vary


def test_backdrop_collision_destroys_one_and_pops_points():
    from termtype.game.entities import FallingWord
    from termtype.game.title import _FAKE_POINTS
    rng = random.Random(0)
    bd = Backdrop(spawn_in=999.0)  # suppress spawning
    # Two words sharing a column, a hair apart → collide on the next step.
    bd.words.append(FallingWord(text="aaaa", x=10.0, row=5.0, speed=1.0))
    bd.words.append(FallingWord(text="bbbb", x=11.0, row=5.2, speed=1.0))
    step_backdrop(bd, ["x"], 1 / 30.0, 80, 22, rng)
    assert len(bd.words) == 1               # one destroyed
    assert len(bd.popups) == 1
    assert bd.popups[0][0] in _FAKE_POINTS   # fake points text


def test_backdrop_popups_expire():
    from termtype.game.title import POPUP_TTL
    rng = random.Random(0)
    bd = Backdrop(spawn_in=999.0)
    bd.popups.append(["+9001!", 5.0, 4.0, 0.0])
    steps = int(POPUP_TTL / (1 / 30.0)) + 2
    for _ in range(steps):
        step_backdrop(bd, ["x"], 1 / 30.0, 80, 22, rng)
    assert bd.popups == []


def test_step_fin_stays_in_bounds():
    from termtype.game.entities import step_fin
    rng = random.Random(3)
    x, d = 5.0, 1
    for _ in range(1000):
        x, d = step_fin(x, d, 1 / 30.0, 80, rng)
        assert 1.0 <= x <= 78.0
        assert d in (1, -1)


def test_step_fin_bounces_at_edges():
    from termtype.game.entities import step_fin
    rng = random.Random(0)
    x, d = step_fin(0.5, -1, 0.1, 40, rng)   # past the left edge
    assert x == 1.0 and d == 1
    x, d = step_fin(39.0, 1, 0.1, 40, rng)   # past the right edge (width-2 = 38)
    assert x == 38.0 and d == -1


# ── credits secret-key egg ────────────────────────────────────────────────


def test_credits_secret_key_reveals_bonus():
    from termtype.game.title import credits_key_action
    assert credits_key_action("f") == "reveal"
    assert credits_key_action("F") == "reveal"   # case-insensitive


def test_credits_other_keys_exit():
    from termtype.game.title import credits_key_action
    for key in ("enter", "esc", "a", "up", "space"):
        assert credits_key_action(key) == "exit"


def test_bonus_credit_line_is_not_a_required_line():
    # The hidden bonus line must never live in the required crawl content.
    from termtype.game.title import BONUS_CREDIT_LINE, CREDITS_LINES
    assert BONUS_CREDIT_LINE not in CREDITS_LINES


# ── Konami frenzy helpers ─────────────────────────────────────────────────


def test_frenzy_fins_count_and_bounds():
    from termtype.game.title import _frenzy_fins
    fins = _frenzy_fins(1.3, 80, count=7)
    assert len(fins) == 7
    assert all(0 <= fx < 80 for fx in fins)


def test_frenzy_fins_sweep_over_time():
    from termtype.game.title import _frenzy_fins
    # The lead fin advances as elapsed grows (before wrap-around).
    a = _frenzy_fins(0.0, 200)[0]
    b = _frenzy_fins(0.1, 200)[0]
    assert b > a


def test_rainbow_colour_cycles_palette():
    from termtype.game.title import _rainbow_colour, _RAINBOW
    seen = {_rainbow_colour(r, 0) for r in range(len(_RAINBOW))}
    assert seen == set(_RAINBOW)
    # Shifting the tick rotates the colour for a given row.
    assert _rainbow_colour(0, 0) != _rainbow_colour(0, 1)


def test_credits_copyright_matches_license_file():
    license_path = Path(__file__).resolve().parents[1] / "LICENSE"
    text = license_path.read_text(encoding="utf-8")
    license_line = next(
        ln.strip() for ln in text.splitlines() if ln.strip().startswith("Copyright (c)")
    )
    assert license_line == COPYRIGHT_LINE
    assert COPYRIGHT_LINE in CREDITS_LINES
