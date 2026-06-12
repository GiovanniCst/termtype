"""Title splash, drop-into-water transition, and the credits crawl.

Pure helpers (logo rendering, drop curve, backdrop stepper, crawl layout) are
render-free and unit-tested. Screen-driven functions live below them and follow
the engine's 30 FPS / clear_buffer / ResizeScreenError discipline.

Implements TITLE_SCREEN_PLAN.md.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .entities import FallingWord

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
