"""asciimatics Screen + IO loop with injectable clock.

PLAN §2.5, §8.3. The only non-unit-tested logic — kept thin.
"""
from __future__ import annotations

import sys
import time
from typing import Any, Callable

from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError

from .state import GameState, advance
from .input_handler import drain_events
from .word_matcher import process_keystroke
from .eggs import feed_secret
from .scoring import (
    word_score, story_word_score, pace_chain_bonus, chapter_fluency_score,
    update_combo, update_peak_score_rate,
)
from .renderer import Renderer
from .hud import render_hud
from .audio import NullAudio
from . import levels


FRAME_BUDGET = 1.0 / 30.0  # 30 FPS


def play_session(
    screen: Screen,
    state: GameState,
    *,
    now: Callable[[], float] = time.monotonic,
    hard_lock: bool = False,
    no_backspace: bool = False,
    ascii_mode: bool = False,
    reduced_motion: bool = False,
    audio: Any = None,
) -> None:
    """Run the game loop on an existing Screen.

    Raises ResizeScreenError on resize — the caller's Screen.wrapper
    re-entry loop rebuilds the screen and calls back in with the live
    GameState, so the run continues where it left off.
    """
    if audio is None:
        audio = NullAudio()

    # Windows: timeBeginPeriod(1) for smoother pacing
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass

    try:
        _game_loop(screen, state, now, hard_lock, no_backspace, ascii_mode, reduced_motion, audio)
    finally:
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


def _game_loop(
    screen: Screen,
    state: GameState,
    now: Callable[[], float],
    hard_lock: bool,
    no_backspace: bool,
    ascii_mode: bool,
    reduced_motion: bool,
    audio: Any,
) -> None:
    """The main game loop."""
    renderer = Renderer(screen, ascii_mode=ascii_mode, reduced_motion=reduced_motion)
    last_time = now()

    while True:
        frame_start = now()

        # Resize: drain one final event (keystroke during resize survives),
        # then unwind to the caller's wrapper re-entry loop
        if screen.has_resized():
            drain_events(screen)
            raise ResizeScreenError("resized", None)

        # Below minimum
        if renderer.render_below_minimum():
            time.sleep(0.1)
            last_time = now()
            continue

        # Drain input
        keys = drain_events(screen)
        for key in keys:
            _process_input(state, key, hard_lock, no_backspace, audio)

        # Show pause screen when paused
        if state.paused:
            from .menus import pause_screen
            from .wordsource import load_lang
            lang = load_lang(state.language)
            action = pause_screen(screen, lang, ascii_mode=ascii_mode, audio=audio)
            if action == "resume":
                state.paused = False
                last_time = now()  # reset clock to avoid dt spike
                continue
            elif action == "quit":
                state.lives = 0  # trigger game over on exit
                return

        # Compute dt
        current_time = now()
        dt = current_time - last_time
        last_time = current_time

        # Clamp dt to avoid spiral of death
        dt = min(dt, 0.1)

        # Report the usable playfield width to the spawner BEFORE advancing, so
        # even the first spawn spans the whole screen. The HN skin reserves the
        # right side for the live page; every other mode uses the full width.
        h, w = screen.dimensions
        if state.story_skin == "hn":
            state.play_cols = max(24, w - min(levels.STORY_PANEL_COLS, w // 2))
        else:
            state.play_cols = w

        # Advance physics
        lives_before = state.lives
        advance(state, dt)
        if state.lives < lives_before:
            audio.play_sfx("life_lost.wav")
            # Life-loss juice: brief red flash + bounded shake (§8.1)
            state.effects.life_loss_flash = (state.time_played_seconds, 0.4)
            state.effects.shake = (state.time_played_seconds, 0.4, 1.0)

        # Check game over
        if state.lives <= 0:
            return  # Exit the loop, caller handles game over

        # Story finished — the whole text was typed and cleared (a win)
        if state.mode == "story" and state.story_completed:
            state.chapter_fluency = chapter_fluency_score(
                _calc_wpm(state), _calc_accuracy(state), state.max_pace_chain,
            )
            audio.play_sfx("level_up.wav")
            return

        # Render (HUD included in render_frame); h, w computed above this frame
        hud_line = render_hud(
            level=state.level,
            score=state.score,
            lives=state.lives,
            wpm=_calc_wpm(state),
            accuracy=_calc_accuracy(state),
            combo_count=state.combo_count,
            width=w,
            ascii_mode=ascii_mode,
        )
        renderer.render_frame(state, hud_line=hud_line)

        # Frame pacing
        elapsed = now() - frame_start
        remaining = FRAME_BUDGET - elapsed
        if remaining > 0:
            time.sleep(remaining)


def _process_input(
    state: GameState,
    key: str,
    hard_lock: bool,
    no_backspace: bool,
    audio: Any,
) -> None:
    """Process a single key through the matcher and update state."""
    # Esc pauses the game (handled before word matcher)
    if key == "esc":
        state.paused = not state.paused
        audio.play_sfx("pause.wav", volume=0.6)
        return

    # Skip input while paused
    if state.paused:
        return

    # Secret-word observer (cosmetic only): watches the raw key stream in
    # parallel with the matcher, never altering locks/scoring (§ easter eggs).
    _observe_secret(state, key, audio)

    result = process_keystroke(
        state, key,
        hard_lock=hard_lock,
        no_backspace=no_backspace,
        is_first_game=state.is_first_game,
    )

    # Set lock_time when a word is newly locked
    if result.lock_changed and state.locked_word_index is not None:
        if state.locked_word_index < len(state.words):
            state.words[state.locked_word_index].lock_time = state.time_played_seconds

    state.total_keystrokes += 1

    if result.accepted:
        state.total_correct_keystrokes += 1
        audio.play_sfx("key.wav", volume=0.35)

        if result.completed:
            # Word completed — score it and remove from screen
            word_text = result.completed_word
            if word_text:
                # Find and remove the completed word
                completed_idx = None
                for i, w in enumerate(state.words):
                    if w.text == word_text and w.typed == word_text:
                        completed_idx = i
                        break

                if completed_idx is not None:
                    word_obj = state.words.pop(completed_idx)
                    # Fix locked_word_index after removal
                    if state.locked_word_index is not None:
                        if state.locked_word_index == completed_idx:
                            state.locked_word_index = None
                        elif state.locked_word_index > completed_idx:
                            state.locked_word_index -= 1

                    # Determine if word was in red zone
                    is_red = levels.is_red_zone(word_obj.row, state.water_row)
                    audio.play_sfx("clutch.wav" if is_red else "word.wav", volume=0.8)

                    state.words_typed += 1
                    state.correct_characters += len(word_text)

                    # Level up every WORDS_PER_LEVEL destroyed words (PLAN §3.1)
                    if state.words_typed % levels.WORDS_PER_LEVEL == 0:
                        state.level += 1
                        state.effects.level_up = (state.time_played_seconds, state.level)
                        audio.play_sfx("level_up.wav")

                    # Calculate time taken (from lock to completion)
                    time_taken = max(0.1, state.time_played_seconds - (word_obj.lock_time or word_obj.spawn_time))

                    if state.mode == "story":
                        # Story scoring: fluency-focused, stopwords down-weighted (§5.2)
                        is_stop = word_text.lower() in state.stopwords
                        score = int(story_word_score(
                            word_text, time_taken, word_obj.error_count,
                            is_stopword=is_stop,
                        ))
                        state.story_words_done += 1
                        # Per-sentence pace chain (§5.2): award an escalating
                        # bonus for each sentence cleared without a drown.
                        prev_done = state.sentences_completed
                        state.sentences_completed = sum(
                            1 for se in state.sentence_ends if se < state.story_words_done
                        )
                        for _ in range(state.sentences_completed - prev_done):
                            state.pace_chain += 1
                            bonus = pace_chain_bonus(state.pace_chain)
                            state.score += bonus
                            state.max_pace_chain = max(state.max_pace_chain, state.pace_chain)
                            state.effects.add_popup(
                                f"PACE x{state.pace_chain} +{bonus}",
                                word_obj.x, word_obj.row - 1,
                                state.time_played_seconds, "combo",
                            )
                    else:
                        score = word_score(
                            word_text, time_taken=time_taken, error_count=word_obj.error_count,
                            level=state.level, combo_count=state.combo_count,
                            in_red_zone=is_red, is_bonus_wave=state.bonus_wave_active,
                        )
                    state.score += score

                    # Track max word WPM
                    word_wpm = 0.0
                    if time_taken > 0:
                        word_wpm = (len(word_text) / 5.0) / (time_taken / 60.0)
                        state.max_word_wpm = max(state.max_word_wpm, word_wpm)

                    # Score popup juice (throttled/tiered, §8.1)
                    tier = ("clutch" if is_red else
                            "blazing" if word_wpm >= 80 else
                            "fast" if word_wpm >= 50 else "good")
                    label = f"CLUTCH +{score}" if is_red else f"+{score}"
                    state.effects.add_popup(
                        label, word_obj.x, word_obj.row, state.time_played_seconds, tier,
                    )

                    # Sparkle juice: a golden burst on a 'gold'-armed clear, or a
                    # clutch sparkle when a word is killed inside the red zone.
                    # Purely cosmetic — no score/balance change.
                    if state.golden_next or is_red:
                        state.golden_next = False
                        state.effects.add_sparkle(
                            word_obj.x + len(word_text) / 2.0, word_obj.row,
                            state.time_played_seconds,
                        )

                    # Update combo
                    combo_before = state.combo_count
                    state.combo_count, state.combo_shield, state.combo_typo_window = update_combo(
                        state.combo_count, state.combo_shield, state.combo_typo_window,
                        state.total_keystrokes,
                        clean_chars=len(word_text), word_length=len(word_text),
                        is_bonus_wave=state.bonus_wave_active,
                    )
                    # Combo stinger + callout on every 10-step milestone crossed
                    if state.combo_count // 10 > combo_before // 10:
                        state.effects.add_popup(
                            f"COMBO x{state.combo_count}", word_obj.x, word_obj.row - 1,
                            state.time_played_seconds, "combo",
                        )
                        audio.play_sfx("combo.wav", volume=0.8)

                    # Update peak score rate
                    state.peak_score_rate = update_peak_score_rate(
                        state.score_history, state.time_played_seconds,
                        score, state.bonus_wave_active, state.peak_score_rate,
                    )

    elif result.rejected:
        audio.play_sfx("typo.wav", volume=0.5)
        # Update combo for typo
        state.combo_count, state.combo_shield, state.combo_typo_window = update_combo(
            state.combo_count, state.combo_shield, state.combo_typo_window,
            state.total_keystrokes,
            is_typo=True,
        )


def _observe_secret(state: GameState, key: str, audio: Any) -> None:
    """Feed the raw key into the hidden secret-word detector and arm payoffs.

    Cosmetic only — sets cosmetic flags; never spawns words, scores, or touches
    the matcher. A boundary key (space/enter/etc.) just resets the run.
    """
    state.secret_buffer, effect = feed_secret(state.secret_buffer, key)
    if effect == "frenzy":
        # A school of fins lunges across the surface for a couple of seconds.
        state.fin_frenzy_until = state.time_played_seconds + 2.5
        audio.play_sfx("clutch.wav", volume=0.5)
    elif effect == "goldrush":
        # The next cleared word sparkles golden (no scoring change).
        state.golden_next = True
        audio.play_sfx("combo.wav", volume=0.5)


def _calc_wpm(state: GameState) -> float:
    """Calculate current WPM."""
    if state.time_played_seconds <= 0:
        return 0.0
    minutes = state.time_played_seconds / 60.0
    if minutes <= 0:
        return 0.0
    return (state.correct_characters / 5.0) / minutes


def _calc_accuracy(state: GameState) -> float:
    """Calculate current accuracy percentage."""
    if state.total_keystrokes <= 0:
        return 100.0
    return (state.total_correct_keystrokes / state.total_keystrokes) * 100.0
