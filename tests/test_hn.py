"""Tests for the live HN fetch (network mocked)."""
from termtype.game import hn


def test_fetch_top_titles_orders_and_drops_empty(monkeypatch):
    def fake_get_json(url, timeout):
        if "topstories" in url:
            return [10, 20, 30, 40]
        if url.endswith("/10.json"):
            return {"title": "First story"}
        if url.endswith("/20.json"):
            return {"title": "   "}          # blank -> dropped
        if url.endswith("/30.json"):
            return {}                          # no title -> dropped
        if url.endswith("/40.json"):
            return {"title": "Fourth story"}
        return None

    monkeypatch.setattr(hn, "_get_json", fake_get_json)
    titles = hn.fetch_top_titles(limit=4, timeout=1.0)
    assert titles == ["First story", "Fourth story"]  # rank order kept, blanks gone


def test_fetch_top_titles_tolerates_item_errors(monkeypatch):
    def fake_get_json(url, timeout):
        if "topstories" in url:
            return [1, 2]
        if url.endswith("/1.json"):
            raise OSError("boom")              # one item fails -> skipped
        return {"title": "Survivor"}

    monkeypatch.setattr(hn, "_get_json", fake_get_json)
    assert hn.fetch_top_titles(limit=2, timeout=1.0) == ["Survivor"]


def test_all_time_top_titles_sample_is_distinct_and_in_pool():
    titles = hn.all_time_top_titles(20)
    assert len(titles) == 20
    assert len(set(titles)) == 20                       # no repeats in a run
    assert all(t in hn._ALL_TIME_TOP for t in titles)   # only baked-in titles


def test_all_time_top_titles_preserves_rank_order():
    titles = hn.all_time_top_titles(10)
    ranks = [hn._ALL_TIME_TOP.index(t) for t in titles]
    assert ranks == sorted(ranks)                       # most-popular-first order


def test_all_time_top_titles_clamps_limit():
    assert len(hn.all_time_top_titles(9999)) == len(hn._ALL_TIME_TOP)  # capped at pool
    assert len(hn.all_time_top_titles(0)) == 1                         # floored at 1


def test_all_time_top_titles_are_non_empty_strings():
    assert all(isinstance(t, str) and t.strip() for t in hn._ALL_TIME_TOP)


class _FakeScreen:
    @property
    def dimensions(self):
        return (24, 80)

    def clear(self):
        pass

    def refresh(self):
        pass

    def print_at(self, *a, **k):
        pass


def test_confirm_maps_keys(monkeypatch):
    from termtype import main

    for key, expected in [("y", True), ("enter", True), ("n", False), ("esc", False), ("q", False)]:
        monkeypatch.setattr(main, "_poll", lambda screen, _k=key: [_k])
        assert main._confirm(_FakeScreen(), "line1", "line2") is expected
