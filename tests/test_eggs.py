"""Unit tests for the pure easter-egg logic (no Screen)."""
from __future__ import annotations

import random

from termtype.game.eggs import (
    KONAMI_SEQUENCE,
    SECRET_WORDS,
    cameo_due,
    feed_secret,
    frenzy_fin_xs,
    konami_progress,
    shark_arc_row,
)


# ── konami_progress ──────────────────────────────────────────────────────


def test_konami_completes_on_full_sequence():
    buf: list[str] = []
    results = [konami_progress(buf, tok) for tok in KONAMI_SEQUENCE]
    assert results[-1] is True
    assert all(r is False for r in results[:-1])


def test_konami_ignores_leading_garbage():
    buf: list[str] = []
    for tok in ("a", "x", "down", "esc"):
        assert konami_progress(buf, tok) is False
    # Now the real code lands — the stray prefix must not block it
    done = [konami_progress(buf, tok) for tok in KONAMI_SEQUENCE]
    assert done[-1] is True


def test_konami_buffer_stays_bounded():
    buf: list[str] = []
    for _ in range(500):
        konami_progress(buf, "up")
    assert len(buf) <= len(KONAMI_SEQUENCE)


def test_konami_wrong_key_midway_resets_suffix():
    buf: list[str] = []
    for tok in KONAMI_SEQUENCE[:-1]:  # all but final 'a'
        konami_progress(buf, tok)
    assert konami_progress(buf, "z") is False  # wrong final key
    assert konami_progress(buf, "a") is False  # 'a' alone no longer completes


# ── feed_secret ──────────────────────────────────────────────────────────


def test_feed_secret_detects_word():
    buf = ""
    effect = None
    for ch in "shark":
        buf, effect = feed_secret(buf, ch)
    assert effect == "frenzy"
    assert buf == ""  # consumed on hit


def test_feed_secret_boundary_resets():
    buf, effect = feed_secret("shar", "space")
    assert buf == "" and effect is None


def test_feed_secret_case_insensitive():
    buf = ""
    effect = None
    for ch in "GOLD":
        buf, effect = feed_secret(buf, ch)
    assert effect == "goldrush"


def test_feed_secret_buffer_capped():
    buf = ""
    for ch in "abcdefghijklmnop":
        buf, _ = feed_secret(buf, ch)
    assert len(buf) <= 8


def test_feed_secret_ignores_plain_words():
    buf = ""
    effect = None
    for ch in "hello":
        buf, effect = feed_secret(buf, ch)
    assert effect is None


def test_secret_words_are_family_friendly_lowercase():
    for word, effect in SECRET_WORDS.items():
        assert word.isalpha() and word.islower()
        assert effect in {"frenzy", "goldrush"}


# ── cameo_due ────────────────────────────────────────────────────────────


def test_cameo_due_is_rare_but_fires():
    rng = random.Random(0)
    fires = sum(cameo_due(rng) for _ in range(100_000))
    assert 0 < fires < 200  # rare, not never


def test_cameo_due_deterministic_with_seed():
    a = [cameo_due(random.Random(7), 0.5) for _ in range(20)]
    b = [cameo_due(random.Random(7), 0.5) for _ in range(20)]
    assert a == b


# ── frenzy_fin_xs ────────────────────────────────────────────────────────


def test_frenzy_fin_xs_count_and_bounds():
    xs = frenzy_fin_xs(2.0, 80, count=7)
    assert len(xs) == 7
    assert all(0 <= x < 80 for x in xs)


def test_frenzy_fin_xs_sweeps_and_wraps():
    span = 100
    a = frenzy_fin_xs(0.0, span)[0]
    b = frenzy_fin_xs(0.2, span)[0]
    assert b > a                                 # advances over time
    assert all(0 <= x < span for x in frenzy_fin_xs(999.0, span))  # wraps cleanly


# ── shark_arc_row ────────────────────────────────────────────────────────


def test_shark_arc_endpoints_at_water():
    assert shark_arc_row(0.0, 1, 20) == 20
    assert shark_arc_row(1.0, 1, 20) == 20


def test_shark_arc_peaks_in_the_middle():
    assert shark_arc_row(0.5, 1, 20, peak=6) == 14  # 6 rows above water


def test_shark_arc_clamps_to_top():
    # A huge peak can't escape above top_row
    assert shark_arc_row(0.5, 3, 20, peak=100) == 3
