"""Colour-portability regression tests.

The Windows console backend reports exactly 8 colours (indices 0-7) and raises
KeyError at refresh() time on any higher index. Palette index 8 ("bright black"
/ grey) only exists on 16+ colour terminals, so dim chrome must degrade to a
valid index on an 8-colour console. These tests reproduce that constraint on
Linux by recording every colour handed to print_at.
"""
from __future__ import annotations

import random

from termtype.game.title import _draw_stars, _make_stars, dim_colour
from termtype.game import menus


class RecordingScreen:
    """Minimal screen that records the colour of every print_at call."""

    def __init__(self, colours=8, w=110, h=30):
        self.colours = colours
        self._w, self._h = w, h
        self.colours_seen = []

    @property
    def dimensions(self):
        return (self._h, self._w)

    def print_at(self, text, x, y, colour=7, attr=0, bg=0):
        self.colours_seen.append(colour)

    def refresh(self):
        pass


def _max_colour(screen):
    return max(screen.colours_seen, default=0)


def test_dim_colour_degrades_below_16():
    # Grey (index 8) needs a 16+ colour palette; below that, fall back to white.
    assert dim_colour(_S(256)) == 8
    assert dim_colour(_S(16)) == 8
    assert dim_colour(_S(8)) == 7      # Windows console
    assert dim_colour(_S(None)) == 7   # attribute missing entirely


def test_draw_stars_never_exceeds_8_colour_palette():
    rng = random.Random(1)
    stars = _make_stars(110, 30, rng, ascii_mode=False)
    screen = RecordingScreen(colours=8)
    _draw_stars(screen, stars, water_row=22)
    assert screen.colours_seen, "expected stars to be drawn"
    assert _max_colour(screen) <= 7


def test_draw_stars_keeps_grey_on_capable_terminal():
    rng = random.Random(1)
    stars = _make_stars(110, 30, rng, ascii_mode=False)
    screen = RecordingScreen(colours=256)
    _draw_stars(screen, stars, water_row=22)
    assert 8 in screen.colours_seen  # grey preserved where the palette has it


def test_menu_header_never_exceeds_8_colour_palette():
    screen = RecordingScreen(colours=8)
    menus._draw_header(screen, 110, subtitle="Select Profile")
    assert screen.colours_seen
    assert _max_colour(screen) <= 7


class _S:
    """Bare screen stand-in carrying only a colours attribute (or none)."""

    def __init__(self, colours):
        if colours is not None:
            self.colours = colours
