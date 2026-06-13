"""Visual effects, color management, and Screen rendering.

PLAN §8.1, §8.2, §8.9. Reads GameState, writes to Screen.
"""
from __future__ import annotations

import os
import random
import unicodedata
from typing import Any

from asciimatics.screen import Screen

from .entities import FallingWord, step_fin
from .eggs import cameo_due, frenzy_fin_xs, shark_arc_row
from .state import GameState
from . import levels

try:
    from wcwidth import wcswidth
except ImportError:
    def wcswidth(s: str) -> int:
        return len(s)


# Color tiers
TIER_256 = 256
TIER_8 = 8
TIER_MONO = 0

# Color palette (colorblind-safe: blue → yellow → red)
COLORS = {
    "word_far": (7, 7, 7),       # dim white
    "word_mid": (6, 6, 0),       # yellow-ish
    "word_near": (1, 1, 0),      # red-ish
    "locked": (2, 2, 0),         # bright
    "typed": (4, 4, 0),          # green-ish
    "water": (4, 4, 0),          # blue
    "hud": (7, 7, 7),            # white
    "error": (1, 1, 0),          # red
    "bonus": (6, 6, 0),          # yellow
    "popup_fast": (6, 6, 0),     # yellow
    "popup_good": (4, 4, 0),     # green
    "popup_slow": (7, 7, 7),     # white
}


def splash_frame(age: float, ttl: float = 0.5) -> list[tuple[int, str]]:
    """Expanding water-splash burst as (dx, glyph) offsets for a given age.

    Pure so it's unit-testable. Droplets fly outward from the drown point: a
    tight burst that widens, then thins out as it ages. Empty once expired.
    """
    if age < 0 or age >= ttl:
        return []
    spread = int(age / ttl * 4) + 1          # 1 → 4 cells out as it ages
    glyph = "'" if age > ttl * 0.6 else "*"  # droplets thin to flecks late
    out = [(0, glyph)]
    for d in range(1, spread + 1):
        out.append((-d, glyph))
        out.append((d, glyph))
    return out


class Renderer:
    """Handles all screen rendering."""

    def __init__(self, screen: Screen, ascii_mode: bool = False, reduced_motion: bool = False):
        self.screen = screen
        self.ascii_mode = ascii_mode
        self.reduced_motion = reduced_motion
        self._color_tier = self._detect_color_tier()

        # Starfield
        self._stars: list[tuple[int, int, str]] = []
        if not reduced_motion:
            self._init_starfield()

        # Shark fin patrolling the water line (cosmetic juice)
        self._fin_rng = random.Random()
        self._fin_x: float | None = None
        self._fin_dir = 1
        self._last_fin_t = 0.0

        # Rare "shark leaps over the words" cameo (easter egg)
        self._cameo_rng = random.Random()
        self._cameo_start: float | None = None   # game-clock time the leap began
        self._cameo_dir = 1                       # +1 left→right, -1 right→left

    def _detect_color_tier(self) -> int:
        """Detect the color tier based on terminal capabilities."""
        if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
            return TIER_MONO
        try:
            colors = self.screen.colours
            if colors and colors >= 256:
                return TIER_256
            elif colors and colors >= 8:
                return TIER_8
        except (AttributeError, TypeError):
            pass
        return TIER_MONO

    def _init_starfield(self) -> None:
        """Initialize a subtle starfield background."""
        import random
        h, w = self.screen.dimensions
        for _ in range(max(1, (w * h) // 80)):
            x = random.randint(0, w - 1)
            y = random.randint(1, h - 4)  # skip HUD row (0) and reserved rows
            glyphs = [".", ",", "`"] if self.ascii_mode else [".", ",", "`", "·"]
            glyph = random.choice(glyphs)
            self._stars.append((x, y, glyph))

    def render_frame(self, state: GameState, hud_line: str = "") -> None:
        """Render a complete frame including HUD."""
        h, w = self.screen.dimensions
        # Blank the back-buffer only (not a physical clear): refresh() then diffs it
        # against the displayed frame and writes just the changed cells — no flicker.
        self.screen.clear_buffer(7, 0, 0)

        # Age out transient effects against the game clock
        now = state.time_played_seconds
        state.effects.clear_expired(now)

        # Bounded ±1 horizontal shake during a life-loss beat (§8.1): fall-zone
        # only, auto-disabled under reduced-motion / mono / no screen margin.
        dx = 0
        if (state.effects.shake and not self.reduced_motion
                and self._color_tier != TIER_MONO and w >= 82 and h >= 26):
            dx = 1 if int(now * 22) % 2 else -1

        # Water row — flashes red during the life-loss beat
        water_row = int(state.water_row)
        water_char = "~" if self.ascii_mode else "≈"
        flash = bool(state.effects.life_loss_flash) and not self.reduced_motion
        try:
            self.screen.print_at(water_char * w, 0, water_row,
                                 colour=1 if flash else 4, attr=1 if flash else 0)
        except Exception:
            pass

        # Shark fin slicing along the surface
        self._render_fin(state, w, water_row)

        # Rare shark-leap cameo arcing over the playfield (easter egg)
        self._render_cameo(state, w, water_row)

        # Starfield (rendered before HUD so HUD overwrites any stars on row 0)
        if not self.reduced_motion:
            for sx, sy, glyph in self._stars:
                if 0 <= sx < w and 0 <= sy < h:
                    try:
                        self.screen.print_at(glyph, sx, sy, colour=7)
                    except Exception:
                        pass

        # Score/combo popups — drawn UNDER words (a word glyph wins a cell)
        self._render_popups(state, w, water_row, dx)

        # Water splashes (drowns) and golden sparkles (secret-word clears)
        self._render_splashes(state, w, water_row, dx)

        # HUD at row 0 (last to render — wins any cell conflicts)
        if hud_line:
            try:
                self.screen.print_at(hud_line, 0, 0, colour=7)
            except Exception:
                pass

        # Words
        for i, word in enumerate(state.words):
            self._render_word(word, i == state.locked_word_index, state, w, water_row, dx)

        # Urgency gutter
        for i, word in enumerate(state.words):
            self._render_urgency_gutter(word, water_row, w, dx)

        # Story presentation: HN page on the right, or the bottom ribbon
        if state.mode == "story" and state.story_skin == "hn":
            self._render_hn_panel(state, h, w)
        elif state.mode == "story" and state.story_words:
            self._render_story_ribbon(state, h, w)

        # Level-up banner (on top of the field, briefly)
        self._render_levelup_banner(state, h, w)

        self.screen.refresh()

    # Popup tier → colour
    _POPUP_COLORS = {"clutch": 6, "blazing": 6, "fast": 4, "good": 7, "combo": 5}

    def _render_popups(self, state: GameState, w: int, water_row: int, dx: int) -> None:
        """Draw score/combo popups drifting up from cleared words (§8.1).

        Suppressed under reduced-motion / mono, where the score lives in the HUD.
        """
        if self.reduced_motion or self._color_tier == TIER_MONO:
            return
        now = state.time_played_seconds
        for text, px, prow, spawn, tier in state.effects.popups:
            age = now - spawn
            drift = int(age / 0.3)  # rise ~1 row every 0.3s
            row = int(round(prow)) - drift
            x = int(round(px)) + dx
            if row < 1 or row >= water_row or x < 0 or x + len(text) > w:
                continue
            colour = self._POPUP_COLORS.get(tier, 7)
            try:
                self.screen.print_at(text, x, row, colour=colour, attr=1)
            except Exception:
                pass

    def _render_splashes(self, state: GameState, w: int, water_row: int, dx: int) -> None:
        """Draw water splashes (drowns) and golden sparkles (secret clears).

        Suppressed under reduced motion. ASCII-safe glyphs only. Splash droplets
        ride just above the water line; sparkles twinkle at the clear point.
        """
        if self.reduced_motion:
            return
        now = state.time_played_seconds
        # Drown splashes — blue droplets fanning out along the surface
        for sx, srow, spawn in state.effects.splashes:
            age = now - spawn
            row = int(round(srow)) - 1  # just above the water line
            cx = int(round(sx)) + dx
            for off, glyph in splash_frame(age, state.effects.SPLASH_TTL):
                x = cx + off
                if 0 <= x < w and 1 <= row < water_row:
                    try:
                        self.screen.print_at(glyph, x, row, colour=6, attr=1)
                    except Exception:
                        pass
        # Golden sparkles — bright twinkle where a secret/golden word cleared
        if self._color_tier == TIER_MONO:
            return
        twinkle = "+x*" if self.ascii_mode else "✦✧*"
        for sx, srow, spawn in state.effects.sparkles:
            age = now - spawn
            if age < 0 or age >= state.effects.SPARKLE_TTL:
                continue
            row = int(round(srow))
            cx = int(round(sx)) + dx
            spread = int(age / state.effects.SPARKLE_TTL * 3) + 1
            glyph = twinkle[int(now * 20) % len(twinkle)]
            for off in range(-spread, spread + 1):
                x = cx + off
                if 0 <= x < w and 1 <= row < water_row and abs(off) % 2 == spread % 2:
                    try:
                        self.screen.print_at(glyph, x, row, colour=6, attr=1)
                    except Exception:
                        pass

    def _render_fin(self, state: GameState, w: int, water_row: int) -> None:
        """A shark fin patrols the water line — cosmetic menace.

        Suppressed under reduced motion. Patrols within the playfield so it
        never strays under a side panel (e.g. the HN page).
        """
        if self.reduced_motion:
            return
        play_w = int(state.play_cols) if state.play_cols else w
        play_w = max(6, min(play_w, w))
        if self._fin_x is None:
            self._fin_x = self._fin_rng.uniform(2, play_w - 3)
        now = state.time_played_seconds
        dt = min(max(0.0, now - self._last_fin_t), 0.1)
        self._last_fin_t = now
        self._fin_x, self._fin_dir = step_fin(
            self._fin_x, self._fin_dir, dt, play_w, self._fin_rng,
        )
        glyph = "^" if self.ascii_mode else "▲"

        # Shark-frenzy egg: a school of fins sweeps past for a couple of seconds
        # (armed by the 'shark'/'kraken' secret word). Cosmetic only.
        if now < state.fin_frenzy_until:
            for sx in frenzy_fin_xs(now, play_w):
                if 0 <= sx < w:
                    try:
                        self.screen.print_at(glyph, sx, water_row, colour=7, attr=1)
                    except Exception:
                        pass
            return

        fx = int(round(self._fin_x))
        if 0 <= fx < w:
            try:
                self.screen.print_at(glyph, fx, water_row, colour=7, attr=1)
            except Exception:
                pass

    # How long a shark-leap cameo takes to arc across the playfield.
    _CAMEO_DUR = 1.1

    def _render_cameo(self, state: GameState, w: int, water_row: int) -> None:
        """A shark rarely leaps in an arc over the falling words (easter egg).

        Suppressed under reduced motion. Starts on a rare per-frame roll, then
        glides edge-to-edge following a parabola. Purely cosmetic.
        """
        if self.reduced_motion:
            return
        now = state.time_played_seconds
        play_w = int(state.play_cols) if state.play_cols else w
        play_w = max(8, min(play_w, w))

        # Maybe begin a new leap (rare); never overlap an in-flight one.
        if self._cameo_start is None and cameo_due(self._cameo_rng):
            self._cameo_start = now
            self._cameo_dir = self._cameo_rng.choice((1, -1))

        if self._cameo_start is None:
            return
        t = (now - self._cameo_start) / self._CAMEO_DUR
        if t >= 1.0:
            self._cameo_start = None
            return

        # Horizontal sweep across the playfield, vertical parabola above water.
        frac = t if self._cameo_dir == 1 else (1.0 - t)
        x = int(2 + frac * (play_w - 4))
        row = shark_arc_row(t, 1, water_row, peak=max(4, water_row // 3))
        # Simple ASCII-art shark so glyph widths stay 1 cell on every terminal.
        shark = ">=^>" if self._cameo_dir == 1 else "<^=<"
        for i, ch in enumerate(shark):
            cx = x + (i if self._cameo_dir == 1 else -i)
            if 0 <= cx < w and 1 <= row < water_row:
                try:
                    self.screen.print_at(ch, cx, row, colour=7, attr=1)
                except Exception:
                    pass

    def _render_levelup_banner(self, state: GameState, h: int, w: int) -> None:
        """Centered level-up banner for a brief beat after each level-up."""
        if not state.effects.level_up:
            return
        _, level = state.effects.level_up
        star = "*" if self.ascii_mode else "✦"
        text = f"{star}  LEVEL {level}  {star}"
        x = max(0, (w - len(text)) // 2)
        row = max(1, h // 2 - 1)
        try:
            self.screen.print_at(text, x, row, colour=6, attr=1)
        except Exception:
            pass

    def _render_hn_panel(self, state: GameState, h: int, w: int) -> None:
        """Render a live 'Hacker News' front page on the right that fills in
        as titles are typed. Styled to resemble news.ycombinator.com."""
        x0 = state.play_cols or max(24, w - min(levels.STORY_PANEL_COLS, w // 2))
        px = x0 + 1                      # content starts after the divider column
        pw = max(10, w - px)             # panel content width
        fancy = self._color_tier == TIER_256

        # Two-tier palette. Fancy (256): orange #ff6600 bar, beige page, gray meta.
        # 8-colour fallback keeps the light-page identity — black on a white page
        # with a yellow bar (the nearest 8-colour orange) — instead of a black
        # void, and uses blue meta so subtext stays visible on white.
        if fancy:
            PAGE_FG, PAGE_BG = 232, 230
            HEAD_FG, HEAD_BG = 15, 202
            META, DIVIDER = 244, 244
        else:
            PAGE_FG, PAGE_BG = 0, 7
            HEAD_FG, HEAD_BG = 0, 3
            META, DIVIDER = 4, 7

        def fill(y, text="", fg=PAGE_FG, bg=PAGE_BG, attr=0):
            if 0 <= y < h:
                line = text[:pw].ljust(pw)
                try:
                    self.screen.print_at(line, px, y, colour=fg, attr=attr, bg=bg)
                except Exception:
                    pass

        # Divider column between the play area and the page
        for y in range(h):
            try:
                self.screen.print_at("|" if self.ascii_mode else "│", x0, y, colour=DIVIDER)
            except Exception:
                pass

        # Page background — clears water/stars/words behind the panel on every tier
        for y in range(h):
            fill(y)

        # Header bar with the Y logo + wordmark
        logo = "[Y]" if self.ascii_mode else "Y"
        header = f" {logo} Hacker News"
        fill(0, header, fg=HEAD_FG, bg=HEAD_BG, attr=1)

        # Footer nav, HN-style
        footer = "guidelines | faq | api | security | legal"
        fill(h - 1, footer, fg=META)

        # Which titles are fully typed yet (one sentence boundary per title)
        done = state.story_words_done
        titles_done = sum(1 for se in state.sentence_ends if se < done)
        lines = state.story_display_lines

        top, bottom = 2, h - 2          # rows available for the list
        per_item = 2                    # title row + subtext row
        capacity = max(1, (bottom - top) // per_item)
        end = min(titles_done, len(lines))
        start = max(0, end - capacity)  # keep the most recently revealed in view

        y = top
        for rank in range(start, end):
            title = lines[rank]
            num = f"{rank + 1}."
            head = f"{num} {title}"
            fill(y, head[:pw], fg=PAGE_FG, attr=1)
            # subtext mimicking HN's points/comments meta line
            pts = 30 + (rank * 17) % 380
            cmts = 3 + (rank * 7) % 120
            sub = f"    ▲ {pts} points  |  {cmts} comments"
            if self.ascii_mode:
                sub = f"    ^ {pts} points  |  {cmts} comments"
            fill(y + 1, sub, fg=META)
            y += per_item
            if y >= bottom:
                break

        # "next page" hint while more headlines remain to be typed
        if end < len(lines):
            fill(bottom, f"   typing... {end}/{len(lines)} headlines", fg=META)

    def _render_story_ribbon(self, state: GameState, h: int, w: int) -> None:
        """Render the assembled-so-far story text + progress on the bottom row."""
        total = len(state.story_words)
        done = min(state.story_words_done, total)

        # Trailing window of already-typed words, with sentence punctuation restored
        start = max(0, done - 14)
        pieces = []
        for idx in range(start, done):
            word = state.story_words[idx]
            if idx in state.sentence_ends:
                word += "."
            pieces.append(word)
        ribbon = " ".join(pieces)

        progress = f"  [{done}/{total}]"
        avail = max(0, w - len(progress) - 1)
        if len(ribbon) > avail:
            ellipsis = "..." if self.ascii_mode else "…"
            ribbon = ellipsis + ribbon[-(avail - len(ellipsis)):]

        line = (ribbon + progress)[:w]
        try:
            self.screen.print_at(line, 0, h - 1, colour=6)
        except Exception:
            pass

    def _render_word(
        self,
        word: FallingWord,
        is_locked: bool,
        state: GameState,
        screen_width: int,
        water_row: int,
        dx: int = 0,
    ) -> None:
        """Render a single falling word."""
        row = int(round(word.row))
        x = int(round(word.x)) + dx

        text = word.text
        display = text

        # Lock affordance
        if is_locked and x > 0 and x + len(text) + 2 < screen_width:
            display = f">{text}<"
            x -= 1  # adjust for bracket

        # Render characters
        for ci, char in enumerate(display):
            cx = x + ci
            if cx < 0 or cx >= screen_width:
                continue

            colour = 7  # default white
            attr = 0

            if is_locked:
                if ci <= len(word.typed) + 1:  # +1 for '>'
                    if char == '>' or char == '<':
                        colour = 2
                        attr = 1
                    elif ci - 1 < len(word.typed):
                        # Typed character
                        colour = 4
                        attr = 1
                    elif ci - 1 == len(word.typed):
                        # Caret (reverse-video on next glyph)
                        colour = 7
                        attr = Screen.A_REVERSE
                    else:
                        colour = 7
                else:
                    colour = 7
            else:
                # Urgency coloring
                dist = water_row - word.row
                if dist <= levels.RED_ZONE_ROWS:
                    colour = 1  # red
                    attr = 1
                elif dist <= levels.RED_ZONE_ROWS * 2:
                    colour = 6  # yellow
                else:
                    colour = 7  # dim

                # First-game onboarding (§2.3): highlight each word's first
                # letter so a new player sees the valid "press me" keys.
                if state.is_first_game and ci == 0:
                    colour = 3  # cyan, bold — stands out on every tier
                    attr = 1

            try:
                self.screen.print_at(char, cx, row, colour=colour, attr=attr)
            except Exception:
                pass

    def _render_urgency_gutter(self, word: FallingWord, water_row: int, screen_width: int, dx: int = 0) -> None:
        """Render the urgency gutter to the left of the word."""
        row = int(round(word.row))
        dist = water_row - word.row
        x = int(round(word.x)) - 2 + dx

        if x < 0:
            return

        if dist <= levels.RED_ZONE_ROWS:
            glyph = "!!"
        elif dist <= levels.RED_ZONE_ROWS * 2:
            glyph = " !"
        else:
            glyph = " ." if self.ascii_mode else " ·"

        try:
            self.screen.print_at(glyph, x, row, colour=7)
        except Exception:
            pass

    def render_below_minimum(self, min_h: int = 24, min_w: int = 80) -> bool:
        """Show resize prompt if below minimum. Returns True if below."""
        h, w = self.screen.dimensions
        if h >= min_h and w >= min_w:
            return False

        self.screen.clear()
        prompt = "Terminal too small. Please resize."
        x = max(0, (w - len(prompt)) // 2)
        y = max(0, h // 2)
        try:
            self.screen.print_at(prompt, x, y)
            self.screen.refresh()
        except Exception:
            pass
        return True
