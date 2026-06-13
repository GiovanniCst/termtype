"""Combo crescendo callouts and the combo-break ('shatter') beat."""
from __future__ import annotations

from termtype.game.engine import _process_input, _combo_shatter
from termtype.game.scoring import combo_callout
from termtype.game.state import GameState
from termtype.game.entities import FallingWord
from termtype.game import levels


class RecAudio:
    """Audio stub that records SFX names (accepts the priority kwarg)."""
    def __init__(self):
        self.sfx = []

    def play_sfx(self, name, volume=1.0, priority=False):
        self.sfx.append(name)


def test_combo_callout_escalates():
    assert combo_callout(10) == "COMBO x10"
    assert "FIRE" in combo_callout(20)
    assert "UNSTOPPABLE" in combo_callout(30)
    assert "GODLIKE" in combo_callout(40)


def test_combo_shatter_sets_break_and_plays_sound():
    st = GameState()
    st.time_played_seconds = 5.0
    au = RecAudio()
    _combo_shatter(st, au, play_sound=True)
    assert st.effects.combo_break == 5.0
    assert "life_lost.wav" in au.sfx


def test_combo_shatter_can_skip_sound():
    st = GameState()
    au = RecAudio()
    _combo_shatter(st, au, play_sound=False)
    assert st.effects.combo_break is not None
    assert au.sfx == []


def _locked_state(combo):
    st = GameState(mode="vocab", water_row=20.0)
    st.words = [FallingWord(text="apple", x=5, row=5.0, speed=1.0)]
    st.combo_count = combo
    return st


def test_typo_cascade_shatters_big_combo():
    # 24 stays below the x25 shield grant, so the 3rd typo truly resets to 0
    # (decays 24 → 23 → 11 → 0; combo_before at the reset is 11 ≥ shatter min).
    st = _locked_state(24)
    au = RecAudio()
    _process_input(st, "a", False, False, au)          # lock 'apple' (combo intact)
    for _ in range(3):
        _process_input(st, "x", False, False, au)      # three mistypes → full reset
    assert st.combo_count == 0
    assert st.effects.combo_break is not None


def test_typo_cascade_no_shatter_for_small_combo():
    st = _locked_state(6)                                # below COMBO_SHATTER_MIN
    au = RecAudio()
    _process_input(st, "a", False, False, au)
    for _ in range(3):
        _process_input(st, "x", False, False, au)
    assert st.combo_count == 0
    assert st.effects.combo_break is None
    assert levels.COMBO_SHATTER_MIN == 10
