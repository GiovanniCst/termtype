"""Integration tests for the in-game secret-word observer (engine.py)."""
from __future__ import annotations

from termtype.game.engine import _observe_secret
from termtype.game.audio import NullAudio
from termtype.game.state import GameState


def _type(state, text):
    audio = NullAudio()
    for ch in text:
        _observe_secret(state, ch, audio)


def test_secret_shark_arms_fin_frenzy():
    st = GameState(mode="vocab")
    st.time_played_seconds = 10.0
    _type(st, "shark")
    assert st.fin_frenzy_until > st.time_played_seconds   # frenzy armed
    assert st.golden_next is False


def test_secret_gold_arms_golden_next():
    st = GameState(mode="vocab")
    _type(st, "gold")
    assert st.golden_next is True
    assert st.fin_frenzy_until == 0.0


def test_observer_ignores_plain_typing():
    st = GameState(mode="vocab")
    _type(st, "hello")
    assert st.golden_next is False
    assert st.fin_frenzy_until == 0.0


def test_boundary_resets_secret_buffer():
    st = GameState(mode="vocab")
    _observe_secret(st, "s", NullAudio())
    _observe_secret(st, "h", NullAudio())
    _observe_secret(st, "space", NullAudio())     # word boundary
    _observe_secret(st, "a", NullAudio())
    _observe_secret(st, "r", NullAudio())
    _observe_secret(st, "k", NullAudio())
    assert st.fin_frenzy_until == 0.0             # "sh ark" is not "shark"


def test_observer_never_touches_words_or_score():
    st = GameState(mode="vocab")
    st.score = 123
    _type(st, "shark")
    assert st.score == 123                        # cosmetic only
    assert st.words == []
