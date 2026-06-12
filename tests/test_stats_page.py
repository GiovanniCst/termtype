"""Tests for the Stats page rendering helpers (recording screen)."""
from termtype.game import menus


class Rec:
    def __init__(self, h=24, w=72):
        self._h, self._w = h, w
        self.texts = []

    @property
    def dimensions(self):
        return (self._h, self._w)

    def clear(self):
        pass

    def print_at(self, text, x, y, colour=7, attr=0, bg=0):
        self.texts.append(str(text))

    def refresh(self):
        pass


def _all(rec):
    return "\n".join(rec.texts)


STATS = {
    "games_played": 12, "best_score": 18230, "cumulative_score": 91200,
    "best_wpm": 72, "best_accuracy": 97, "highest_level": 9, "max_combo": 34,
    "words_typed": 540, "words_missed": 21, "total_seconds_played": 1440,
    "total_correct_chars": 4200,
}


def test_summary_block_shows_key_metrics():
    rec = Rec()
    menus._render_stats_summary(rec, STATS, {"level_10", "combo_25"}, 72)
    out = _all(rec)
    assert "Best 18,230" in out
    assert "Highest level 9" in out
    assert "level_10" in out          # earned badges listed


def test_graph_renders_a_sparkline():
    rec = Rec()
    menus._graph(rec, "WPM", [10, 20, 30, 40, 50], 8, 72, ascii_mode=False)
    out = _all(rec)
    assert "WPM" in out
    assert any(c in out for c in "▁▂▃▄▅▆▇█")


def test_sparse_table_under_five_games():
    rec = Rec()
    series = [{"played_at": "2026-06-01T10:00", "score": 100, "wpm": 30, "accuracy": 90, "level": 2}]
    menus._render_stats_sparse(rec, series, 72, 24)
    out = _all(rec)
    assert "Played" in out
    assert "2026-06-01" in out
    assert "unlock trend graphs" in out
