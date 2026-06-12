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
from termtype.main import _clamp_colour, _install_colour_guard


class RecordingScreen:
    """Minimal screen that records the colour of every print_at call."""

    A_REVERSE = 0

    def __init__(self, colours=8, w=110, h=30):
        self.colours = colours
        self._w, self._h = w, h
        self.colours_seen = []

    @property
    def dimensions(self):
        return (self._h, self._w)

    def clear(self):
        pass

    def clear_buffer(self, fg, attr, bg, x=0, y=0, w=None, h=None):
        pass

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


def test_clamp_colour_maps_out_of_palette_to_white():
    assert _clamp_colour(8, 8) == 7      # gray index absent on 8-colour console
    assert _clamp_colour(244, 8) == 7    # 256-palette HN gray
    assert _clamp_colour(6, 8) == 6      # in range -> untouched
    assert _clamp_colour(7, 8) == 7
    assert _clamp_colour(None, 8) is None


def test_guard_clamps_any_high_colour_on_limited_terminal():
    # The boundary guard is the catch-all: even a 256-palette colour like the
    # HN divider's 244 must not reach an 8-colour console's refresh().
    screen = RecordingScreen(colours=8)
    _install_colour_guard(screen)
    screen.print_at("x", 0, 0, colour=8)
    screen.print_at("y", 0, 1, colour=244, bg=230)
    screen.print_at("z", 0, 2, colour=6)
    assert screen.colours_seen == [7, 7, 6]


def test_guard_is_noop_on_full_palette():
    screen = RecordingScreen(colours=256)
    _install_colour_guard(screen)
    screen.print_at("x", 0, 0, colour=244)
    assert screen.colours_seen == [244]  # 256-colour dev terminal untouched


def test_hn_divider_safe_on_8_colour_console():
    # The story/HN renderer draws its divider with a raw 256-palette gray (244),
    # ungated by colour tier. Through the guard on an 8-colour screen it must
    # never emit an index the Windows console would KeyError on.
    from termtype.game.renderer import Renderer
    from termtype.game.state import GameState

    screen = RecordingScreen(colours=8)
    _install_colour_guard(screen)
    r = Renderer(screen, reduced_motion=True)
    state = GameState(
        mode="story", story_skin="hn", play_cols=66,
        story_words=["alpha", "beta", "gamma", "delta"],
        sentence_ends={1, 3},
        story_display_lines=["Alpha Beta Headline", "Gamma Delta Headline"],
        story_words_done=2,
    )
    r.render_frame(state, hud_line="HUD")
    assert screen.colours_seen
    assert max(screen.colours_seen) <= 7


class _S:
    """Bare screen stand-in carrying only a colours attribute (or none)."""

    def __init__(self, colours):
        if colours is not None:
            self.colours = colours
