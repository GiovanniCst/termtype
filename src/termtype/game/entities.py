"""Game entities: FallingWord, WaterLine, Effects.

Pure data + render-free behavior — no asciimatics, no terminal IO.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FallingWord:
    """A word falling from the top of the screen.

    Attributes:
        text: The word string (NFC-normalized).
        x: Column position (float, rounded only at render).
        row: Vertical position in rows (float, 0 = top).
        speed: Fall speed in rows per second.
        locked: Whether this word is currently locked by the player.
        typed: Characters typed so far (the prefix matched).
        error_count: Rejected keystrokes + backspaced typos for this word.
        lock_time: Monotonic timestamp when the word was locked (for speed_bonus).
        spawn_time: Monotonic timestamp when the word spawned.
    """
    text: str
    x: float
    row: float
    speed: float
    locked: bool = False
    typed: str = ""
    error_count: int = 0
    lock_time: float | None = None
    spawn_time: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.typed == self.text

    @property
    def next_char(self) -> str | None:
        """The next expected character, or None if complete."""
        if len(self.typed) < len(self.text):
            return self.text[len(self.typed)]
        return None

    def advance(self, dt: float) -> None:
        """Move the word down by speed * dt rows."""
        self.row += self.speed * dt

    def reached_water(self, water_row: float) -> bool:
        return self.row >= water_row


def step_fin(x: float, direction: int, dt: float, width: int, rng,
             speed: float = 9.0, turn_per_sec: float = 0.5) -> tuple[float, int]:
    """Advance a shark fin patrolling the water line. Pure; rng injected.

    Moves horizontally, bounces off the edges, and randomly reverses now and
    then. Returns the new (x, direction). Cosmetic only — no gameplay effect.
    """
    x += direction * speed * dt
    if x <= 1:
        return 1.0, 1
    if x >= width - 2:
        return float(width - 2), -1
    if rng.random() < turn_per_sec * dt:
        direction = -direction
    return x, direction


@dataclass
class WaterLine:
    """The water line at the bottom of the play area.

    row: The row number where the water line sits (fixed per screen size).
    """
    row: float

    def set_row(self, row: float) -> None:
        self.row = row


@dataclass
class Effects:
    """Transient visual/audio effects state.

    Tracks active popups, flashes, shakes, etc.
    All render-free — the renderer reads this state to draw effects.
    """
    # Score popups: list of (text, x, row, spawn_time, tier)
    popups: list[tuple[str, float, float, float, str]] = field(default_factory=list)
    # Life-loss flash: (start_time, duration)
    life_loss_flash: tuple[float, float] | None = None
    # Screen shake: (start_time, duration, intensity)
    shake: tuple[float, float, float] | None = None
    # Combo break effect: (start_time,)
    combo_break: float | None = None
    # Level-up banner: (start_time, level)
    level_up: tuple[float, int] | None = None

    # At most this many popups on screen at once (newest win, §8.1)
    MAX_POPUPS = 3

    def add_popup(self, text: str, x: float, row: float, now: float, tier: str = "good") -> None:
        """Add a score/combo popup, capping concurrency (newest wins)."""
        self.popups.append((text, x, row, now, tier))
        if len(self.popups) > self.MAX_POPUPS:
            self.popups = self.popups[-self.MAX_POPUPS:]

    def clear_expired(self, now: float, popup_ttl: float = 0.6) -> None:
        """Remove expired effects."""
        self.popups = [
            p for p in self.popups
            if now - p[3] < popup_ttl
        ]
        if self.life_loss_flash and now - self.life_loss_flash[0] > self.life_loss_flash[1]:
            self.life_loss_flash = None
        if self.shake and now - self.shake[0] > self.shake[1]:
            self.shake = None
        if self.level_up and now - self.level_up[0] > 1.2:
            self.level_up = None
