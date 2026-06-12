"""Pure game state and fixed-timestep step function.

No Screen, no time import — dt is injected.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from .entities import FallingWord, WaterLine, Effects
from . import levels


@dataclass
class GameState:
    """Complete render-free game state.

    All fields are plain data — the renderer reads them, advance() mutates them.
    """
    # Core game state
    words: list[FallingWord] = field(default_factory=list)
    score: int = 0
    lives: int = levels.DEFAULT_LIVES
    level: int = 1
    paused: bool = False

    # Combo (char-based step counter, PLAN §4.2)
    combo_count: int = 0
    combo_shield: bool = False
    combo_typo_window: list[int] = field(default_factory=list)  # keystroke indices of uncorrected typos

    # Spawn timer
    spawn_timer: float = 0.0

    # Plateau depth (increments each surge survived) + the words_typed mark of
    # the last surge, so the schedule fires every PLATEAU_SURGE_EVERY words.
    plateau_depth: int = 0
    last_plateau_surge_words: int = 0

    # Opening hook: the very first word of a fresh run is short + slow (§3.1)
    first_spawn_done: bool = False

    # RNG
    rng: random.Random = field(default_factory=random.Random)

    # Mode / options
    mode: str = "vocab"  # "vocab" or "story"
    language: str = "en"
    option_flags: dict[str, bool] = field(default_factory=lambda: {
        "numbers": False,
        "accents": False,
        "punctuation": False,
    })

    # Water line position (set by engine based on screen size)
    water_row: float = 20.0

    # Per-game stat counters (PLAN §4.3)
    correct_characters: int = 0
    words_typed: int = 0
    words_missed: int = 0
    time_played_seconds: float = 0.0
    total_keystrokes: int = 0
    total_correct_keystrokes: int = 0

    # Peak score rate tracking (PLAN §3.1)
    # Rolling 60-s window: list of (timestamp, points)
    score_history: list[tuple[float, int]] = field(default_factory=list)
    peak_score_rate: float = 0.0

    # Badge-feeding extras (PLAN §3.1)
    max_word_wpm: float = 0.0
    reached_plateau: bool = False
    story_completed: bool = False

    # Bonus wave state
    bonus_wave_active: bool = False
    bonus_wave_timer: float = 0.0
    last_bonus_wave_level: int = 0  # prevent re-trigger on same level

    # First-game / returning-player flags
    is_first_game: bool = True
    first_keystroke_time: float | None = None

    # Word pool (provided by wordsource)
    word_pool: list[str] = field(default_factory=list)

    # Story mode (PLAN §5.2): ordered text spawned in reading order
    story_words: list[str] = field(default_factory=list)   # full ordered word list
    story_position: int = 0                                 # next index to spawn
    sentence_ends: set[int] = field(default_factory=set)    # story_words indices ending a sentence
    stopwords: set[str] = field(default_factory=set)        # down-weighted in story scoring
    story_words_done: int = 0                               # completed count (for the ribbon/progress)

    # Per-sentence pace chain + chapter fluency (PLAN §5.2)
    pace_chain: int = 0                                     # consecutive sentences cleared on pace
    max_pace_chain: int = 0
    sentences_completed: int = 0
    chapter_fluency: int = 0                                # set when the story completes

    # Story Zen sub-mode (PLAN §5.2): no fail; a drowned word auto-completes
    # into the prose, scores 0, and breaks the combo.
    zen: bool = False

    # Story presentation: "" = bottom ribbon; "hn" = right-side Hacker News page
    story_skin: str = ""
    story_display_lines: list[str] = field(default_factory=list)  # real lines (e.g. HN titles)
    play_cols: int = 0                                      # playfield width when a side panel is shown (0 = full)

    # Transient visual effects (popups, life-loss flash, shake, level-up banner).
    # Timed against time_played_seconds so the renderer needs no separate clock.
    effects: Effects = field(default_factory=Effects)

    # Word lock state
    locked_word_index: int | None = None  # index into self.words

    @property
    def water_line(self) -> WaterLine:
        return WaterLine(row=self.water_row)

    def find_lowest_matching(self, char: str) -> int | None:
        """Find the index of the lowest (highest row) word starting with char."""
        best_idx = None
        best_row = -1.0
        for i, w in enumerate(self.words):
            if w.text and w.text[0] == char and w.row > best_row:
                best_row = w.row
                best_idx = i
        return best_idx


def advance(state: GameState, dt: float) -> GameState:
    """Pure fixed-timestep advance — the heart of the game loop.

    Integrates fall, runs the spawn timer, detects water-line hits.
    Pauses freeze the clock (early-return unchanged).
    Combo/score effects of a clear live in scoring.py; this only owns
    motion, spawning, and life-loss.
    """
    if state.paused:
        return state

    # ── Time accounting ──
    state.time_played_seconds += dt

    # ── Move words ──
    for word in state.words:
        word.advance(dt)

    # ── Water-line hits ──
    # Track the locked word by identity — indices shift when words drown
    locked_word: FallingWord | None = None
    if state.locked_word_index is not None and state.locked_word_index < len(state.words):
        locked_word = state.words[state.locked_word_index]

    survived: list[FallingWord] = []
    for word in state.words:
        if word.reached_water(state.water_row):
            if state.mode == "story":
                state.pace_chain = 0  # a drowned word breaks the pace chain (§5.2)
            if state.zen:
                # Zen: no life lost; the word auto-completes into the prose,
                # scores 0, and breaks the combo (PLAN §5.2).
                state.story_words_done += 1
                state.combo_count = 0
                state.combo_shield = False
                state.combo_typo_window.clear()
            else:
                state.lives -= 1
                state.words_missed += 1
                # Reset combo on drowned word (except during bonus wave)
                if not state.bonus_wave_active:
                    state.combo_count = 0
                    state.combo_shield = False
                    state.combo_typo_window.clear()
        else:
            survived.append(word)
    state.words = survived

    # Re-derive the lock index (None if the locked word drowned)
    state.locked_word_index = next(
        (i for i, w in enumerate(survived) if w is locked_word), None,
    ) if locked_word is not None else None

    # ── Bonus wave timer ──
    if state.bonus_wave_active:
        state.bonus_wave_timer -= dt
        if state.bonus_wave_timer <= 0:
            state.bonus_wave_active = False
            state.bonus_wave_timer = 0.0

    # ── Check for bonus wave trigger (once per level) ──
    if (not state.bonus_wave_active
            and levels.is_bonus_wave(state.level)
            and state.last_bonus_wave_level != state.level):
        state.bonus_wave_active = True
        state.bonus_wave_timer = levels.BONUS_WAVE_DURATION
        state.last_bonus_wave_level = state.level

    # ── Spawn timer ──
    max_sim = levels.max_simultaneous_for_level(state.level)
    current_count = len(state.words)

    # Modulate spawn speed during bonus wave or plateau surge
    spawn_interval = levels.SPAWN_TIMER_BASE
    if state.bonus_wave_active:
        spawn_interval *= 1.5  # slower spawns during bonus wave
    if state.plateau_depth > 0:
        _, spawn_mult = levels.plateau_surge_params(state.plateau_depth)
        spawn_interval /= spawn_mult

    # Scale by level: faster spawns at higher levels
    speed_min, speed_max = levels.speed_range_for_level(state.level)
    level_speed_factor = speed_min / 1.5  # normalize
    spawn_interval /= max(0.5, level_speed_factor)

    state.spawn_timer += dt

    should_spawn = False
    if current_count < levels.SPAWN_FLOOR:
        # Below floor: spawn promptly
        should_spawn = True
    elif current_count < max_sim and state.spawn_timer >= spawn_interval:
        should_spawn = True

    if should_spawn and (state.word_pool or state.story_words):
        _spawn_word(state)
        state.spawn_timer = 0.0

    # ── Plateau detection + escalating surge schedule (§3.1) ──
    if state.level >= levels.PLATEAU_LEVEL:
        state.reached_plateau = True
        # Every PLATEAU_SURGE_EVERY words at plateau, escalate (denser + faster).
        if state.words_typed - state.last_plateau_surge_words >= levels.PLATEAU_SURGE_EVERY:
            state.plateau_depth += 1
            state.last_plateau_surge_words = state.words_typed

    # ── Story completion: whole text spawned and cleared off-screen ──
    if (state.mode == "story"
            and state.story_words
            and state.story_position >= len(state.story_words)
            and not state.words):
        state.story_completed = True

    return state


def _spawn_word(state: GameState) -> None:
    """Spawn a new word at a random position, avoiding overlaps.

    Story mode emits the next word in reading order; vocab mode samples
    the pool at random.
    """
    is_opening = not state.first_spawn_done
    state.first_spawn_done = True

    if state.mode == "story":
        if state.story_position >= len(state.story_words):
            return  # whole story already spawned
        word_text = state.story_words[state.story_position]
        state.story_position += 1
    else:
        if not state.word_pool:
            return
        if is_opening:
            # Opening hook: a short first word for an immediate first kill (§3.1)
            short = [w for w in state.word_pool if 3 <= len(w) <= 4]
            word_text = state.rng.choice(short) if short else state.rng.choice(state.word_pool)
        else:
            word_text = state.rng.choice(state.word_pool)

    # Speed within the level's range
    speed_min, speed_max = levels.speed_range_for_level(state.level)
    speed = state.rng.uniform(speed_min, speed_max)

    # Plateau surge makes words fall faster as depth escalates (§3.1)
    if state.plateau_depth > 0:
        speed_mult, _ = levels.plateau_surge_params(state.plateau_depth)
        speed *= speed_mult

    # The opening word falls slowly so a new player clears it with margin
    if is_opening:
        speed *= 0.6

    # During bonus wave, words are slower
    if state.bonus_wave_active:
        speed *= 0.5

    # X position: keep the WHOLE word (plus its lock brackets ">word<") inside
    # the playfield. play_cols is the usable width — it already excludes any side
    # panel such as the HN page — so subtracting the word length here is what
    # stops long words from being truncated by the panel or the right edge.
    margin = 4
    min_x = margin
    right_limit = state.play_cols if state.play_cols else 80
    max_x = max(min_x, right_limit - len(word_text) - 2)

    # Find X positions of words near the top (row < 4)
    top_word_xs = [
        (w.x, len(w.text) + 4)  # (start_x, width_with_brackets)
        for w in state.words
        if w.row < 4.0
    ]

    # Try to find a non-overlapping X (up to 10 attempts)
    x = None
    for _ in range(10):
        candidate = state.rng.uniform(min_x, max_x)
        overlaps = False
        for wx, ww in top_word_xs:
            if abs(candidate - wx) < ww + 2:  # +2 for gap
                overlaps = True
                break
        if not overlaps:
            x = candidate
            break

    # If all attempts overlap, just pick a random one
    if x is None:
        x = state.rng.uniform(min_x, max_x)

    word = FallingWord(
        text=word_text,
        x=x,
        row=1.0,  # start below HUD row (row 0)
        speed=speed,
        spawn_time=state.time_played_seconds,
    )
    state.words.append(word)
