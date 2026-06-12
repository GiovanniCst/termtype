"""Tests for state.py — GameState and the pure advance() function."""
import pytest
from termtype.game.state import GameState, advance
from termtype.game.entities import FallingWord
from termtype.game import levels


def make_state(**kwargs) -> GameState:
    """Create a GameState with sensible defaults for testing."""
    defaults = dict(
        word_pool=["hello", "world", "test", "python", "code"],
        water_row=20.0,
    )
    defaults.update(kwargs)
    return GameState(**defaults)


def make_word(text: str, row: float = 0.0, speed: float = 1.0, x: float = 10.0) -> FallingWord:
    return FallingWord(text=text, x=x, row=row, speed=speed)


class TestAdvancePaused:
    def test_paused_is_noop(self):
        state = make_state(paused=True)
        state.words.append(make_word("hello", row=5.0, speed=1.0))
        state.score = 42
        state.lives = 3

        result = advance(state, 1.0)

        assert result is state
        assert state.words[0].row == 5.0  # unchanged
        assert state.score == 42
        assert state.lives == 3

    def test_paused_any_dt(self):
        state = make_state(paused=True)
        for dt in [0.0, 0.001, 1.0, 100.0]:
            advance(state, dt)
            assert state.time_played_seconds == 0.0


class TestWordFalling:
    def test_words_fall_by_speed_dt(self):
        state = make_state()
        state.words.append(make_word("hello", row=5.0, speed=2.0))

        advance(state, 0.5)

        assert state.words[0].row == pytest.approx(6.0)  # 5.0 + 2.0*0.5

    def test_float_positions(self):
        state = make_state()
        state.words.append(make_word("hello", row=0.0, speed=1.3))

        advance(state, 0.1)

        assert state.words[0].row == pytest.approx(0.13)

    def test_multiple_words_independent(self):
        state = make_state()
        state.words.append(make_word("a", row=0.0, speed=1.0))
        state.words.append(make_word("b", row=0.0, speed=2.0))

        advance(state, 1.0)

        assert state.words[0].row == pytest.approx(1.0)
        assert state.words[1].row == pytest.approx(2.0)


class TestWaterLineHit:
    def test_word_reaching_water_removes_it(self):
        state = make_state(water_row=10.0, word_pool=["zzz_unique"])
        state.words.append(make_word("hello", row=9.5, speed=1.0))

        advance(state, 1.0)  # moves to 10.5, past water

        # "hello" should be gone (a different word from pool may have spawned)
        texts = [w.text for w in state.words]
        assert "hello" not in texts

    def test_word_reaching_water_costs_life(self):
        state = make_state(water_row=10.0, lives=3)
        state.words.append(make_word("hello", row=9.5, speed=1.0))

        advance(state, 1.0)

        assert state.lives == 2

    def test_word_missed_counter(self):
        state = make_state(water_row=10.0)
        state.words.append(make_word("hello", row=9.5, speed=1.0))

        advance(state, 1.0)

        assert state.words_missed == 1

    def test_combo_resets_on_drown(self):
        state = make_state(water_row=10.0)
        state.combo_count = 15
        state.words.append(make_word("hello", row=9.5, speed=1.0))

        advance(state, 1.0)

        assert state.combo_count == 0

    def test_combo_preserved_during_bonus_wave(self):
        state = make_state(water_row=10.0)
        state.combo_count = 15
        state.bonus_wave_active = True
        state.bonus_wave_timer = 5.0
        state.words.append(make_word("hello", row=9.5, speed=1.0))

        advance(state, 1.0)

        assert state.combo_count == 15  # preserved during bonus wave


class TestSpawnTimer:
    def test_spawn_respects_max_cap(self):
        state = make_state()
        state.level = 1  # max_simultaneous = 3
        # Add 3 words (at cap)
        for _ in range(3):
            state.words.append(make_word("test"))

        # Advance a lot — no more should spawn
        for _ in range(100):
            advance(state, 0.1)

        # Should still be 3 (or fewer if some drowned)
        assert len(state.words) <= levels.max_simultaneous_for_level(1)

    def test_spawn_fills_to_floor(self):
        state = make_state()
        state.level = 1  # floor = 2
        # Start with 0 words
        assert len(state.words) == 0

        # After one advance, should spawn to reach floor
        advance(state, 0.01)
        # The spawn timer logic should trigger a spawn when below floor
        # (spawn_timer starts at 0, and below-floor triggers immediate spawn)
        assert len(state.words) >= 1  # at least one spawned

    def test_spawn_timer_ticks(self):
        state = make_state()
        state.level = 1
        # Fill to max
        for _ in range(3):
            state.words.append(make_word("test"))

        initial_timer = state.spawn_timer
        advance(state, 0.5)

        # Timer should have advanced (even if no spawn happened due to cap)
        assert state.spawn_timer >= initial_timer


class TestTimePlayed:
    def test_time_accumulates(self):
        state = make_state()
        advance(state, 1.0)
        advance(state, 0.5)
        assert state.time_played_seconds == pytest.approx(1.5)

    def test_paused_time_does_not_accumulate(self):
        state = make_state()
        advance(state, 1.0)
        state.paused = True
        advance(state, 1.0)
        assert state.time_played_seconds == pytest.approx(1.0)


class TestBonusWave:
    def test_bonus_wave_triggers_at_level_5(self):
        state = make_state()
        state.level = 5
        advance(state, 0.01)
        assert state.bonus_wave_active is True
        assert state.bonus_wave_timer > 0

    def test_bonus_wave_expires(self):
        state = make_state()
        state.level = 5
        advance(state, 0.01)
        assert state.bonus_wave_active is True

        # Advance past duration
        advance(state, levels.BONUS_WAVE_DURATION + 1.0)
        assert state.bonus_wave_active is False

    def test_no_bonus_wave_at_level_3(self):
        state = make_state()
        state.level = 3
        advance(state, 1.0)
        assert state.bonus_wave_active is False


class TestPlateauDetection:
    def test_reached_plateau_at_level_15(self):
        state = make_state()
        state.level = 15
        advance(state, 0.01)
        assert state.reached_plateau is True

    def test_not_reached_below_plateau(self):
        state = make_state()
        state.level = 14
        advance(state, 1.0)
        assert state.reached_plateau is False


class TestPlateauSurge:
    def test_surge_escalates_depth_every_n_words(self):
        state = make_state()
        state.level = levels.PLATEAU_LEVEL
        state.words_typed = levels.PLATEAU_SURGE_EVERY
        advance(state, 0.01)
        assert state.plateau_depth == 1
        # no further surge until another PLATEAU_SURGE_EVERY words
        advance(state, 0.01)
        assert state.plateau_depth == 1
        state.words_typed = levels.PLATEAU_SURGE_EVERY * 2
        advance(state, 0.01)
        assert state.plateau_depth == 2

    def test_no_surge_before_plateau(self):
        state = make_state()
        state.level = 5
        state.words_typed = 100
        advance(state, 0.01)
        assert state.plateau_depth == 0


class TestOpeningHook:
    def test_first_vocab_word_is_short(self):
        state = make_state()  # pool includes 4-char "test"/"code"
        advance(state, 0.01)
        assert state.first_spawn_done is True
        assert state.words
        assert 3 <= len(state.words[0].text) <= 4

    def test_opening_word_falls_slower(self):
        state = make_state()
        state.rng.seed(1)
        advance(state, 0.01)
        opening_speed = state.words[0].speed
        smin, _ = levels.speed_range_for_level(1)
        assert opening_speed < smin  # 0.6x the band minimum


class TestStorySpawn:
    def _story_state(self, words):
        return GameState(
            mode="story", word_pool=words, story_words=words,
            water_row=20.0,
        )

    def test_spawns_in_reading_order(self):
        state = self._story_state(["alpha", "bravo", "charlie", "delta"])
        spawned = []
        # Advance until a few words have spawned (cap is 3 at level 1)
        for _ in range(50):
            before = state.story_position
            advance(state, 0.2)
            if state.story_position > before:
                spawned.append(state.words[-1].text)
            if state.story_position >= 3:
                break
        # Words must appear in text order, never random
        assert spawned == ["alpha", "bravo", "charlie"]

    def test_position_never_exceeds_length(self):
        state = self._story_state(["one", "two"])
        for _ in range(100):
            advance(state, 0.5)
            state.words.clear()  # simulate the player clearing every word
        assert state.story_position == 2

    def test_completes_when_text_exhausted_and_cleared(self):
        state = self._story_state(["aa", "bb"])
        # Spawn everything, then clear the screen
        for _ in range(20):
            advance(state, 0.5)
            state.words.clear()
        advance(state, 0.1)
        assert state.story_completed is True

    def test_not_complete_while_words_remain(self):
        state = self._story_state(["aa", "bb"])
        for _ in range(20):
            advance(state, 0.1)  # words pile up, none cleared
        # All spawned but still on screen — not complete yet
        assert state.story_completed is False

    def test_empty_story_does_not_falsely_complete(self):
        state = self._story_state([])
        advance(state, 0.1)
        assert state.story_completed is False

    def test_vocab_mode_never_completes(self):
        state = make_state()  # vocab mode
        for _ in range(20):
            advance(state, 0.5)
            state.words.clear()
        assert state.story_completed is False


class TestZenMode:
    def _zen_state(self):
        return GameState(
            mode="story", zen=True, word_pool=["aa", "bb"], story_words=["aa", "bb"],
            water_row=10.0, lives=3,
        )

    def test_drowned_word_costs_no_life(self):
        state = self._zen_state()
        state.combo_count = 8
        state.words.append(make_word("aa", row=9.9, speed=1.0))
        advance(state, 1.0)  # word crosses the water line
        assert state.lives == 3              # no life lost in Zen
        assert state.words_missed == 0
        assert state.combo_count == 0        # but the combo breaks
        assert state.story_words_done == 1   # auto-completes into the prose

    def test_challenge_drowned_word_costs_life(self):
        state = self._zen_state()
        state.zen = False
        state.words.append(make_word("aa", row=9.9, speed=1.0))
        advance(state, 1.0)
        assert state.lives == 2
        assert state.story_words_done == 0
