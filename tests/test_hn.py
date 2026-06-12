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
