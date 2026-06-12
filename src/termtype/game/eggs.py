"""Hidden easter-egg logic — pure, render-free, fully unit-tested.

Everything here is OFF the normal path: it only fires on secret triggers and
never changes default gameplay, balance, or scoring. Screen-driven payoffs live
in title.py / renderer.py and read the predicates below.
"""
from __future__ import annotations

# Konami code as named input tokens (the engine/menu emit these verbatim).
KONAMI_SEQUENCE: tuple[str, ...] = (
    "up", "up", "down", "down", "left", "right", "left", "right", "b", "a",
)

# In-game secret words: typing one as a whole word triggers its payoff.
# Family-friendly, terminal-native, nothing offensive. Value = effect name.
SECRET_WORDS: dict[str, str] = {
    "shark": "frenzy",     # a school of fins lunges across the surface
    "gold": "goldrush",    # the next clear sparkles golden
    "kraken": "frenzy",
}


def konami_progress(buffer: list[str], token: str) -> bool:
    """Feed one input token into the rolling Konami buffer (mutated in place).

    Keeps only the trailing KONAMI_SEQUENCE-length tokens so a stray key just
    resets the suffix rather than the whole attempt. Returns True on the frame
    the full code completes.
    """
    buffer.append(token)
    if len(buffer) > len(KONAMI_SEQUENCE):
        del buffer[:-len(KONAMI_SEQUENCE)]
    return tuple(buffer) == KONAMI_SEQUENCE


def feed_secret(buffer: str, ch: str, max_len: int = 8) -> tuple[str, str | None]:
    """Accumulate typed letters and detect a completed secret word.

    `ch` is a single char (or a token like 'space'/'enter'); only ascii letters
    extend the buffer, anything else clears it (word boundary). Returns the new
    buffer and the matched effect name (or None). The buffer is capped so it
    never grows without bound.
    """
    if len(ch) == 1 and ch.isascii() and ch.isalpha():
        buffer = (buffer + ch.lower())[-max_len:]
    else:
        return "", None  # boundary token resets the run

    for word, effect in SECRET_WORDS.items():
        if buffer.endswith(word):
            return "", effect  # consume the buffer on a hit
    return buffer, None


def cameo_due(rng, chance: float = 0.0006) -> bool:
    """Rare per-frame predicate for the 'shark jumps over the words' cameo.

    chance is per render frame (~30 FPS): 0.0006 ≈ once every ~55 s on average.
    rng is injected so it's deterministic in tests. Cosmetic only.
    """
    return rng.random() < chance


def frenzy_fin_xs(elapsed: float, width: int, count: int = 7, speed: float = 26.0) -> list[int]:
    """X positions of a school of fins sweeping across the surface.

    Evenly spaced and wrapping around the width. Pure/deterministic for tests;
    shared by the title splash and the in-game shark-frenzy egg.
    """
    span = max(1, width)
    head = (elapsed * speed) % span
    return [int((head + i * (span / count)) % span) for i in range(count)]


def shark_arc_row(t: float, top_row: int, water_row: int, peak: int = 6) -> int:
    """Parabolic height of a leaping shark over the playfield.

    t in [0, 1]: starts and ends at the water line, peaking `peak` rows above it
    at t=0.5. Pure — the renderer maps it to a glyph row.
    """
    t = max(0.0, min(1.0, t))
    height = 4.0 * peak * t * (1.0 - t)  # parabola, 0 at ends, `peak` at mid
    row = round(water_row - height)
    return max(top_row, row)
