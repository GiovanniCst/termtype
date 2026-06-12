"""Live Hacker News headline fetch for the HN story sub-mode.

Network-only and ephemeral: titles are fetched fresh each run and never
written to disk. No asciimatics, no game state — just returns strings.
"""
from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
_UA = {"User-Agent": "termType (typing game)"}


def _get_json(url: str, timeout: float):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _title(item_id: int, timeout: float) -> str | None:
    try:
        data = _get_json(_ITEM_URL.format(item_id), timeout)
    except Exception:
        return None
    if not data:
        return None
    title = data.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else None


def fetch_top_titles(limit: int = 20, timeout: float = 6.0) -> list[str]:
    """Return up to `limit` current HN top-story titles, in rank order.

    Raises on failure to reach the top-stories list; tolerates individual
    item misses. Returned list may be shorter than `limit`.
    """
    ids = _get_json(_TOP_URL, timeout)[:limit]
    with ThreadPoolExecutor(max_workers=8) as pool:
        titles = list(pool.map(lambda i: _title(i, timeout), ids))
    return [t for t in titles if t]
