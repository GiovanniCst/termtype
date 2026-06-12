"""Tests for menu description helpers and i18n key parity."""
from __future__ import annotations

import json
from pathlib import Path

from termtype.game.menus import _RAINBOW, _draw_header, _norm_items, _wrap_desc


class _RecScreen:
    """Minimal recording screen for header-draw assertions."""

    def __init__(self, w=80, h=24):
        self._w, self._h = w, h
        self.calls = []  # (text, x, y, colour)

    @property
    def dimensions(self):
        return (self._h, self._w)

    def print_at(self, text, x, y, colour=7, attr=0, bg=0):
        self.calls.append((text, x, y, colour))

_LANG_DIR = Path(__file__).resolve().parents[1] / "src" / "termtype" / "data" / "lang"


def test_norm_items_pads_short_tuples():
    items = [
        ("a", "Label A"),
        ("b", "Label B", "x"),
        ("c", "Label C", "y", "A description."),
    ]
    norm = _norm_items(items)
    assert norm[0] == ("a", "Label A", None, None)
    assert norm[1] == ("b", "Label B", "x", None)
    assert norm[2] == ("c", "Label C", "y", "A description.")


def test_norm_items_uniform_length():
    norm = _norm_items([("a", "A"), ("b", "B", "x", "d")])
    assert all(len(t) == 4 for t in norm)


def test_wrap_desc_empty():
    assert _wrap_desc("", 40) == []
    assert _wrap_desc("anything", 2) == []


def test_wrap_desc_single_line():
    out = _wrap_desc("Exit TermType.", 40)
    assert out == ["Exit TermType."]


def test_wrap_desc_two_lines():
    text = "Endless falling words. Type them before they hit the water."
    out = _wrap_desc(text, 30)
    assert 1 <= len(out) <= 2
    assert all(len(line) <= 30 for line in out)


def test_wrap_desc_truncates_to_two_lines_with_ellipsis():
    text = " ".join(["word"] * 60)
    out = _wrap_desc(text, 20)
    assert len(out) == 2
    assert out[-1].endswith("...")


def test_header_default_colour_is_cyan():
    screen = _RecScreen()
    _draw_header(screen, 80)
    colours = {c[3] for c in screen.calls if c[0].strip()}
    assert colours == {6}                       # plain cyan header by default


def test_header_rainbow_tick_uses_palette():
    screen = _RecScreen()
    _draw_header(screen, 80, rainbow_tick=0)
    colours = {c[3] for c in screen.calls if c[0].strip()}
    assert colours                              # something drawn
    assert colours <= set(_RAINBOW)             # only palette colours
    assert colours != {6}                       # not the plain header


def test_lang_files_have_identical_keys():
    en = json.loads((_LANG_DIR / "en.json").read_text(encoding="utf-8"))
    it = json.loads((_LANG_DIR / "it.json").read_text(encoding="utf-8"))
    assert set(en) == set(it), set(en).symmetric_difference(set(it))


def test_new_description_keys_present():
    en = json.loads((_LANG_DIR / "en.json").read_text(encoding="utf-8"))
    for key in (
        "menu_credits", "credits_title",
        "desc_continue", "desc_vocab", "desc_story", "desc_stats",
        "desc_settings", "desc_switch", "desc_credits", "desc_quit",
        "desc_story_challenge", "desc_story_zen", "desc_hn", "desc_story_generic",
        "desc_opt_numbers", "desc_opt_accents", "desc_opt_punctuation",
    ):
        assert key in en, key
