"""Tests for the HUD row, including the ASCII fallback."""
from termtype.game.hud import render_hud


def _hud(**kw):
    base = dict(level=2, score=1234, lives=3, wpm=58, accuracy=96, combo_count=7, width=80)
    base.update(kw)
    return render_hud(**base)


def test_unicode_heart_by_default():
    line = _hud()
    assert "♥" in line


def test_ascii_heart_fallback():
    line = _hud(ascii_mode=True)
    assert "*" in line
    assert "♥" not in line


def test_lives_collapse_to_count_above_max():
    line = _hud(lives=9, ascii_mode=True)
    assert "*x9" in line


def test_lives_and_score_never_truncated_when_narrow():
    line = _hud(width=40, score=1234567, lives=3)
    assert "1,234,567" in line  # score kept even when narrow
