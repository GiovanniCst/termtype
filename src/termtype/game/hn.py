"""Hacker News headlines for the HN story sub-mode.

Live titles are fetched fresh each run and never written to disk. When HN is
unreachable (offline), the game offers a baked-in list of the most-upvoted
submissions of all time as a fallback. No asciimatics, no game state — just
returns strings.
"""
from __future__ import annotations

import json
import random
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
_UA = {"User-Agent": "termType (typing game)"}

# Most-upvoted HN submissions of all time (Algolia, points-ranked), used as the
# offline fallback. Curly quotes normalised to ASCII for clean typing.
_ALL_TIME_TOP = (
    "Stephen Hawking has died",
    "A Message to Our Customers",
    "OpenAI's board has fired Sam Altman",
    "Backdoor in upstream xz/liblzma leading to SSH server compromise",
    "CrowdStrike Update: Windows Bluescreen and Boot Loops",
    "Steve Jobs has passed away",
    "Bram Moolenaar has died",
    "Mechanical Watch",
    "YouTube-dl has received a DMCA takedown from RIAA",
    "Reflecting on one very, very strange year at Uber",
    "GPT-4",
    "Replit used legal threats to kill my open-source project",
    "How I cut GTA Online loading times by 70%",
    "Bye, Amazon",
    "Kevin Mitnick has died",
    "Sora: Creating video from text",
    "Google Search Is Dying",
    "Every Google result now looks like an ad",
    "Show HN: This up votes itself",
    "Ghostty is leaving GitHub",
    "A search engine that favors text-heavy sites",
    "Apollo will close down on June 30th",
    "My First Impressions of Web3",
    "F.C.C. Repeals Net Neutrality Rules",
    'Bing: "I will not harm you unless you harm me first"',
    "Switch from Chrome to Firefox",
    "Ask HN: I'm a software engineer going blind, how should I prepare?",
    "Cloudflare Reverse Proxies Are Dumping Uninitialized Memory",
    '"Click to subscribe, call to cancel" is illegal, FTC says',
    "FDIC Takes over Silicon Valley Bank",
    "UK votes to leave EU",
    "Tim Cook Speaks Up",
)


def all_time_top_titles(limit: int = 20) -> list[str]:
    """Return a random sample of the baked-in all-time top titles, in rank
    order, so each offline run differs while still showing the greatest hits."""
    n = max(1, min(limit, len(_ALL_TIME_TOP)))
    picks = sorted(random.sample(range(len(_ALL_TIME_TOP)), n))
    return [_ALL_TIME_TOP[i] for i in picks]


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
