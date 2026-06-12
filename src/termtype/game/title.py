"""Title splash, drop-into-water transition, and the credits crawl.

Pure helpers (logo rendering, drop curve, backdrop stepper, crawl layout) are
render-free and unit-tested. Screen-driven functions live below them and follow
the engine's 30 FPS / clear_buffer / ResizeScreenError discipline.

Implements TITLE_SCREEN_PLAN.md.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from asciimatics.exceptions import ResizeScreenError

from .entities import FallingWord, step_fin
from .eggs import konami_progress
from .input_handler import drain_events
from .wordsource import load_vocab, t

try:
    import pyfiglet
    HAS_PYFIGLET = True
except ImportError:
    HAS_PYFIGLET = False


TITLE_TEXT = "TERMTYPE"

# Reused CC0 effect for the title hitting the water (no new audio files).
THUD_SFX = "clutch.wav"

# Mirrors the repo LICENSE copyright line verbatim — a unit test enforces it so
# the in-game credit and GitHub can never drift apart.
COPYRIGHT_LINE = "Copyright (c) 2026 Giovanni J. Costantini"

CREDITS_LINES = [
    "TERMTYPE",
    "",
    "Imagined and orchestrated by",
    "Giovanni J. Costantini",
    "",
    "Coded with autonomous AI agents",
    "(Opus, Kimi, Fable)",
    "",
    "https://costantini.pw",
    "",
    "A terminal typing game where words",
    "fall like Space Invaders.",
    "",
    "MIT License",
    COPYRIGHT_LINE,
    "",
    "Music & SFX: Juhani Junkala (SubspaceAudio) - CC0 1.0",
    "Stories: public-domain texts",
]


# ── Logo rendering ───────────────────────────────────────────────────────


def _figlet_lines(font: str, width: int) -> list[str] | None:
    """Render TITLE_TEXT in a pyfiglet font at natural width.

    Returns the trimmed lines, or None if pyfiglet is missing, the font fails,
    or the banner's natural width exceeds `width` (so callers fall back to a
    smaller font / plain text rather than letting pyfiglet wrap into a mess).
    """
    if not HAS_PYFIGLET:
        return None
    try:
        # Render with an effectively unbounded width so pyfiglet never wraps;
        # we decide the fit ourselves against the real terminal width.
        fig = pyfiglet.Figlet(font=font, width=10_000)
        rendered = fig.renderText(TITLE_TEXT)
    except Exception:
        return None

    lines = [ln.rstrip() for ln in rendered.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    while lines and not lines[0]:
        lines.pop(0)
    if not lines or max(len(ln) for ln in lines) > width:
        return None
    return lines


def splash_logo(width: int) -> list[str]:
    """Large centered logo for the splash: big font, else small, else plain."""
    for font in ("big", "small"):
        lines = _figlet_lines(font, width)
        if lines is not None:
            return lines
    return [TITLE_TEXT]


def header_logo(width: int) -> list[str]:
    """Compact logo used as the persistent menu/profile header (small font)."""
    lines = _figlet_lines("small", width)
    return lines if lines is not None else [TITLE_TEXT]


# ── Drop curve ───────────────────────────────────────────────────────────


def logo_drop_row(t: float, start_row: int, water_row: int) -> int:
    """Quadratic-gravity vertical position of the logo's top during the drop.

    t in [0, 1] (clamped): 0 → start_row, 1 → water_row, accelerating.
    """
    t = max(0.0, min(1.0, t))
    return round(start_row + (water_row - start_row) * t * t)


# ── Backdrop (decorative falling words) ──────────────────────────────────


MAX_BACKDROP_WORDS = 10


@dataclass
class Backdrop:
    """Ambient falling-word state for the splash. Decorative only."""
    words: list[FallingWord] = field(default_factory=list)
    spawn_in: float = 0.0


def step_backdrop(
    bd: Backdrop,
    pool: list[str],
    dt: float,
    width: int,
    water_row: int,
    rng: random.Random,
) -> None:
    """Advance the backdrop one frame: maybe spawn, fall, drown at the water."""
    bd.spawn_in -= dt
    if bd.spawn_in <= 0 and len(bd.words) < MAX_BACKDROP_WORDS and pool:
        text = rng.choice(pool)
        x = rng.uniform(0, max(0, width - len(text)))
        bd.words.append(FallingWord(text=text, x=x, row=0.0, speed=rng.uniform(0.6, 1.4)))
        bd.spawn_in = rng.uniform(0.5, 0.9)

    for w in bd.words:
        w.advance(dt)
    # Words that reach the water line drown — exactly like gameplay.
    bd.words[:] = [w for w in bd.words if w.row < water_row]


# ── Credits crawl layout ─────────────────────────────────────────────────


def crawl_visible(lines: list[str], offset: float, height: int) -> list[tuple[str, int]]:
    """Map crawl lines to (text, y) at a given scroll offset.

    Lines start below the bottom edge and rise as offset grows. Empty strings
    only create vertical spacing. Only on-screen rows are returned.
    """
    base = height - int(offset)
    out: list[tuple[str, int]] = []
    for i, text in enumerate(lines):
        if not text:
            continue
        y = base + i
        if 0 <= y < height:
            out.append((text, y))
    return out


def crawl_done(offset: float, total: int, height: int) -> bool:
    """True once the last crawl line (index total-1) has risen past the top."""
    return height - int(offset) + (total - 1) < 0


# ── Screen-driven splash (not unit-tested; render + IO) ──────────────────

FRAME_BUDGET = 1.0 / 30.0
DROP_DUR = 0.4      # seconds for the logo to fall into the water
FLASH_DUR = 0.25    # seconds the water flashes red on impact
MIN_H, MIN_W = 24, 80


def _poll(screen) -> list[str]:
    """Drain input, unwinding to the wrapper re-entry loop on resize."""
    if screen.has_resized():
        raise ResizeScreenError("resized", None)
    return drain_events(screen)


def _pace(frame_start: float) -> None:
    remaining = FRAME_BUDGET - (time.monotonic() - frame_start)
    if remaining > 0:
        time.sleep(remaining)


def _draw_block(screen, lines: list[str], top: int, w: int, colour: int,
                clip_at: int | None = None) -> None:
    """Draw a centered text block; skip rows at/below clip_at (sinks below water)."""
    block_w = max((len(ln) for ln in lines), default=0)
    x = max(0, (w - block_w) // 2)
    for i, line in enumerate(lines):
        y = top + i
        if y < 0 or (clip_at is not None and y >= clip_at):
            continue
        try:
            screen.print_at(line, x, y, colour=colour, attr=1)
        except Exception:
            pass


def _word_colour(row: float, water_row: int) -> int:
    """Colour a falling word by how close it is to drowning (cool → hot)."""
    frac = row / max(1.0, water_row)
    if frac < 0.40:
        return 6   # cyan — just spawned
    if frac < 0.70:
        return 5   # magenta
    if frac < 0.88:
        return 3   # yellow — getting close
    return 1       # red — about to drown


def _draw_backdrop(screen, bd: "Backdrop", water_row: int) -> None:
    for word in bd.words:
        row = int(round(word.row))
        if row < 0 or row >= water_row:
            continue
        try:
            screen.print_at(word.text, int(round(word.x)), row,
                            colour=_word_colour(word.row, water_row))
        except Exception:
            pass


def _make_stars(w: int, h: int, rng: random.Random, ascii_mode: bool) -> list[tuple[int, int, str]]:
    """Generate a sparse starfield (above the water line)."""
    glyphs = [".", ",", "`"] if ascii_mode else [".", ",", "`", "·"]
    stars = []
    for _ in range(max(1, (w * h) // 90)):
        x = rng.randint(0, w - 1)
        y = rng.randint(1, max(1, h - 3))
        stars.append((x, y, rng.choice(glyphs)))
    return stars


def _draw_stars(screen, stars: list[tuple[int, int, str]], water_row: int) -> None:
    for sx, sy, glyph in stars:
        if sy >= water_row:
            continue
        try:
            screen.print_at(glyph, sx, sy, colour=8)
        except Exception:
            pass


def _draw_fin(screen, fx: int, water_row: int, w: int, ascii_mode: bool) -> None:
    if not (0 <= fx < w):
        return
    glyph = "^" if ascii_mode else "▲"
    try:
        screen.print_at(glyph, fx, water_row, colour=7, attr=1)
    except Exception:
        pass


# ── Konami easter egg: a frenzy of fins sweeps the surface ────────────────

# Keys that are part of the hidden code — they don't dismiss the splash, so a
# player entering the code mid-stream isn't kicked out before completing it.
_KONAMI_KEYS = frozenset({"up", "down", "left", "right", "b", "a"})

# Rotating bright palette for the rainbow logo flash during the frenzy.
_RAINBOW = (1, 3, 2, 6, 4, 5)


def _frenzy_fins(elapsed: float, w: int, count: int = 7) -> list[int]:
    """X positions of a school of fins sweeping right across the surface.

    Evenly spaced, wrapping around the width — pure so it's trivially testable.
    """
    span = max(1, w)
    head = (elapsed * 26.0) % span  # lead fin position
    return [int((head + i * (span / count)) % span) for i in range(count)]


def _rainbow_colour(row: int, tick: int) -> int:
    """Cycle the rainbow palette by row + animation tick (frenzy logo flash)."""
    return _RAINBOW[(row + tick) % len(_RAINBOW)]


def _draw_water(screen, w: int, water_row: int, ascii_mode: bool, flash: bool = False) -> None:
    ch = "~" if ascii_mode else "≈"
    try:
        screen.print_at(ch * w, 0, water_row,
                        colour=1 if flash else 4, attr=1 if flash else 0)
    except Exception:
        pass


def title_splash(screen, audio, lang: dict, *, ascii_mode: bool = False,
                 reduced_motion: bool = False) -> None:
    """Arcade attract splash: falling words behind a big logo, then a drop.

    Returns when the player presses any key (after the drop animation, unless
    reduced_motion). Resize unwinds via ResizeScreenError and replays.
    """
    pool = load_vocab("en") + load_vocab("it")
    prompt = t("press_any_key", lang, "Press any key...")

    if reduced_motion:
        _splash_static(screen, prompt, ascii_mode)
        return

    rng = random.Random()
    bd = Backdrop()
    logo: list[str] = []
    stars: list[tuple[int, int, str]] = []
    logo_w = -1
    fin_x: float | None = None
    fin_dir = 1
    konami: list[str] = []        # rolling buffer for the hidden code
    frenzy_until = 0.0            # monotonic time the fin frenzy ends
    start = time.monotonic()
    last = start

    while True:
        frame_start = time.monotonic()
        h, w = screen.dimensions
        if h < MIN_H or w < MIN_W:
            _render_below_min(screen)
            _poll(screen)
            time.sleep(0.05)
            last = time.monotonic()
            continue

        now = time.monotonic()
        dt = min(now - last, 0.1)
        last = now
        elapsed = now - start
        water_row = h - 2
        if w != logo_w:
            logo, logo_w = splash_logo(w), w
            stars = _make_stars(w, h, rng, ascii_mode)
        if fin_x is None:
            fin_x = rng.uniform(2, w - 3)

        step_backdrop(bd, pool, dt, w, water_row, rng)
        fin_x, fin_dir = step_fin(fin_x, fin_dir, dt, w, rng)
        frenzy = now < frenzy_until

        screen.clear_buffer(7, 0, 0)
        _draw_stars(screen, stars, water_row)
        _draw_backdrop(screen, bd, water_row)
        _draw_water(screen, w, water_row, ascii_mode)
        if frenzy:
            for fx in _frenzy_fins(elapsed, w):
                _draw_fin(screen, fx, water_row, w, ascii_mode)
        else:
            _draw_fin(screen, int(round(fin_x)), water_row, w, ascii_mode)
        if int(elapsed * 2) % 2 == 0:  # ~1 Hz blink
            _centered(screen, prompt, h - 1, w, colour=7)
        logo_top = h // 2 - len(logo) // 2
        if frenzy:  # rainbow flash on the logo while the school sweeps past
            tick = int(elapsed * 12)
            for i, line in enumerate(logo):
                _draw_block(screen, [line], logo_top + i, w,
                            colour=_rainbow_colour(i, tick))
        else:
            _draw_block(screen, logo, logo_top, w, colour=6)
        screen.refresh()

        # Drain input. A key that advances/completes the hidden code is
        # swallowed (and may light the frenzy); any other key exits the splash.
        exit_splash = False
        for key in _poll(screen):
            if konami_progress(konami, key):
                frenzy_until = time.monotonic() + 2.5
            elif key not in _KONAMI_KEYS:
                exit_splash = True
        if exit_splash and now >= frenzy_until:
            break
        _pace(frame_start)

    _splash_drop(screen, audio, bd, logo, ascii_mode, stars)


def _splash_static(screen, prompt: str, ascii_mode: bool) -> None:
    """Reduced-motion splash: static logo + prompt, any key returns."""
    while True:
        h, w = screen.dimensions
        if h < MIN_H or w < MIN_W:
            _render_below_min(screen)
            _poll(screen)
            time.sleep(0.05)
            continue
        logo = splash_logo(w)
        screen.clear_buffer(7, 0, 0)
        _draw_block(screen, logo, h // 2 - len(logo) // 2, w, colour=6)
        _centered(screen, prompt, h - 1, w, colour=7)
        screen.refresh()
        if _poll(screen):
            return
        time.sleep(0.05)


def _splash_drop(screen, audio, bd: "Backdrop", logo: list[str], ascii_mode: bool,
                 stars: list[tuple[int, int, str]]) -> None:
    """Logo falls into the water with gravity, then a thud + red flash beat."""
    h, w = screen.dimensions
    water_row = h - 2
    start_top = h // 2 - len(logo) // 2
    target_top = water_row - 1  # crest just above the surface, rest sinks under

    start = time.monotonic()
    while True:
        frame_start = time.monotonic()
        if screen.has_resized():
            drain_events(screen)
            raise ResizeScreenError("resized", None)
        t_frac = (time.monotonic() - start) / DROP_DUR
        top = logo_drop_row(t_frac, start_top, target_top)

        screen.clear_buffer(7, 0, 0)
        _draw_stars(screen, stars, water_row)
        _draw_backdrop(screen, bd, water_row)
        _draw_water(screen, w, water_row, ascii_mode)
        _draw_block(screen, logo, top, w, colour=6, clip_at=water_row)
        screen.refresh()

        if t_frac >= 1.0:
            break
        _pace(frame_start)

    # Impact beat: thud + red water flash (the life-loss juice grammar).
    if audio is not None:
        audio.play_sfx(THUD_SFX)
    flash_start = time.monotonic()
    while time.monotonic() - flash_start < FLASH_DUR:
        frame_start = time.monotonic()
        if screen.has_resized():
            drain_events(screen)
            raise ResizeScreenError("resized", None)
        screen.clear_buffer(7, 0, 0)
        _draw_stars(screen, stars, water_row)
        _draw_backdrop(screen, bd, water_row)
        _draw_water(screen, w, water_row, ascii_mode, flash=True)
        _draw_block(screen, logo, target_top, w, colour=6, clip_at=water_row)
        screen.refresh()
        _pace(frame_start)


def _centered(screen, text: str, y: int, w: int, colour: int = 7) -> None:
    x = max(0, (w - len(text)) // 2)
    try:
        screen.print_at(text, x, y, colour=colour)
    except Exception:
        pass


def _render_below_min(screen) -> None:
    """Shared below-minimum resize prompt (lazy import dodges a menus cycle)."""
    from .menus import _render_resize_prompt
    _render_resize_prompt(screen)


# ── Credits crawl ────────────────────────────────────────────────────────

CRAWL_SPEED = 2.0     # rows per second
CREDITS_HOLD = 1.0    # seconds held after the last line clears the top

# Highlighted (title / personal-brand) lines.
_CREDITS_ACCENT = {"TERMTYPE", "Giovanni J. Costantini", "https://costantini.pw"}


def credits_screen(screen, lang: dict, *, ascii_mode: bool = False, audio=None) -> None:
    """Star-Wars-style upward credits crawl. Any key (or end + hold) returns.

    Music is left untouched (the title track keeps playing). Resize unwinds via
    ResizeScreenError back to the menu phase.
    """
    has_color = bool(getattr(screen, "colours", 0)) and screen.colours >= 8
    total = len(CREDITS_LINES)
    offset = 0.0
    last = time.monotonic()
    done_at: float | None = None

    while True:
        frame_start = time.monotonic()
        h, w = screen.dimensions
        if h < MIN_H or w < MIN_W:
            _render_below_min(screen)
            _poll(screen)
            time.sleep(0.05)
            last = time.monotonic()
            continue

        now = time.monotonic()
        dt = min(now - last, 0.1)
        last = now
        offset += CRAWL_SPEED * dt

        screen.clear_buffer(7, 0, 0)
        for text, y in crawl_visible(CREDITS_LINES, offset, h):
            if not has_color:
                colour = 7
            elif y <= 1 or y >= h - 2:
                colour = 8                       # edge fade
            elif text in _CREDITS_ACCENT:
                colour = 6
            else:
                colour = 7
            _centered(screen, text, y, w, colour=colour)
        _centered(screen, "Esc back", h - 1, w, colour=8 if has_color else 7)
        screen.refresh()

        if _poll(screen):
            return

        # When the final line has risen past the top, hold briefly then return.
        if crawl_done(offset, total, h):
            if done_at is None:
                done_at = now
            elif now - done_at >= CREDITS_HOLD:
                return
        _pace(frame_start)
