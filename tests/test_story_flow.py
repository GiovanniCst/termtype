"""Story-mode in-order 'flow' bonus and reading-order frontier detection."""
from __future__ import annotations

from termtype.game.engine import _process_input
from termtype.game.audio import NullAudio
from termtype.game.state import GameState, advance
from termtype.game.entities import FallingWord
from termtype.game.scoring import in_order_bonus
from termtype.game import levels


def _story_state(words):
    """A story GameState with the given words already on screen in FIFO order."""
    st = GameState(mode="story")
    st.water_row = 20.0
    st.story_words = list(words)
    st.story_position = len(words)  # everything already spawned → no respawn
    for i, text in enumerate(words):
        st.words.append(FallingWord(text=text, x=5 + i, row=5.0 - i,
                                    speed=1.0, spawn_time=0.0))
    return st


def _type(st, text):
    audio = NullAudio()
    for ch in text:
        _process_input(st, ch, False, False, audio)


def test_in_order_bonus_values():
    assert in_order_bonus(0) == 0
    assert in_order_bonus(1) == levels.STORY_IN_ORDER_BONUS
    assert in_order_bonus(levels.STORY_FLOW_CAP + 3) == (
        levels.STORY_IN_ORDER_BONUS * levels.STORY_FLOW_CAP
    )


def test_clearing_frontier_builds_flow():
    st = _story_state(["alpha", "beta", "gamma"])
    _type(st, "alpha")
    assert st.story_flow == 1
    assert st.max_story_flow == 1
    assert st.score > 0


def test_skipping_ahead_resets_flow():
    st = _story_state(["aaa", "bbb", "ccc"])
    _type(st, "aaa")          # frontier → flow 1
    assert st.story_flow == 1
    _type(st, "ccc")          # skipped bbb → out of order
    assert st.story_flow == 0


def test_in_order_clear_scores_more_than_out_of_order():
    # Same word, same timing — the only difference is the in-order bonus.
    in_st = _story_state(["same", "other"])
    _type(in_st, "same")      # frontier (index 0)
    out_st = _story_state(["other", "same"])
    _type(out_st, "same")     # index 1 → not the frontier
    assert in_st.story_flow == 1 and out_st.story_flow == 0
    assert in_st.score > out_st.score
    assert in_st.score - out_st.score == in_order_bonus(1)


def test_drown_resets_flow():
    st = _story_state(["aaa", "bbb"])
    _type(st, "aaa")
    assert st.story_flow == 1
    st.words[0].row = st.water_row + 1.0   # bbb is now at the surface
    advance(st, 0.05)                      # → it drowns
    assert st.story_flow == 0
