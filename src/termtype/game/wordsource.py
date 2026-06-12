"""Word and story loading, option filtering, ordered-spawn selection.

Pure logic + packaged-content loading via importlib.resources.
No terminal, no asciimatics.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Iterator

from . import levels


def _data_root():
    """Return the data/ Traversable from the installed package."""
    import importlib.resources
    return importlib.resources.files("termtype") / "data"


def load_lang(language: str) -> dict[str, str]:
    """Load a language JSON file and return a dict of UI strings."""
    root = _data_root()
    lang_file = root / "lang" / f"{language}.json"
    text = lang_file.read_text(encoding="utf-8")
    return json.loads(text)


def t(key: str, lang: dict[str, str], default: str = "") -> str:
    """Look up a UI string by key."""
    return lang.get(key, default)


def load_vocab(
    language: str,
    *,
    accents: bool = False,
    punctuation: bool = False,
    numbers: bool = False,
) -> list[str]:
    """Load and filter vocabulary for the given language and options.

    Filters:
    - Single-char entries removed (MIN_COMBO_WORD_LEN)
    - Accented words removed if accents=False
    - Words with punctuation removed if punctuation=False
    - Numeric strings removed if numbers=False
    - NFC-normalized
    """
    root = _data_root()
    filename = f"{'italiano' if language == 'it' else 'english'}.txt"
    vocab_file = root / "vocab" / filename
    text = vocab_file.read_text(encoding="utf-8")

    words = []
    for line in text.strip().splitlines():
        word = line.strip()
        if not word:
            continue

        # NFC normalize
        word = unicodedata.normalize("NFC", word)

        # Filter single-char
        if len(word) < levels.MIN_COMBO_WORD_LEN:
            continue

        # Filter by options
        if not accents and _has_accent(word):
            continue
        if not punctuation and _has_punctuation(word):
            continue
        if not numbers and word.isdigit():
            continue

        words.append(word)

    return words


def load_stops(language: str) -> set[str]:
    """Load the stopword list for the given language."""
    root = _data_root()
    filename = f"stopwords_{'it' if language == 'it' else 'en'}.txt"
    stops_file = root / "vocab" / filename
    text = stops_file.read_text(encoding="utf-8")
    return {unicodedata.normalize("NFC", w.strip()) for w in text.strip().splitlines() if w.strip()}


def load_packs(
    enabled_packs: list[str],
    *,
    accents: bool = False,
    punctuation: bool = False,
    numbers: bool = False,
) -> list[str]:
    """Load enabled word packs and return filtered words."""
    root = _data_root()
    words = []
    for pack_name in enabled_packs:
        pack_file = root / "vocab" / "packs" / f"{pack_name}.txt"
        try:
            text = pack_file.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        for line in text.strip().splitlines():
            word = unicodedata.normalize("NFC", line.strip())
            if not word or len(word) < levels.MIN_COMBO_WORD_LEN:
                continue
            if not accents and _has_accent(word):
                continue
            if not punctuation and _has_punctuation(word):
                continue
            if not numbers and word.isdigit():
                continue
            words.append(word)
    return words


def build_word_pool(
    language: str,
    option_flags: dict[str, bool],
    enabled_packs: list[str] | None = None,
) -> list[str]:
    """Build the full word pool from vocab + packs, biased to gentle-band median ≥5.

    Returns a list suitable for random.choice in the spawner.
    """
    accents = option_flags.get("accents", False)
    punctuation = option_flags.get("punctuation", False)
    numbers = option_flags.get("numbers", False)

    words = load_vocab(language, accents=accents, punctuation=punctuation, numbers=numbers)

    if enabled_packs:
        words.extend(load_packs(enabled_packs, accents=accents, punctuation=punctuation, numbers=numbers))

    return words if words else ["fallback"]


def list_stories(language: str) -> list[str]:
    """Return the available story names (filenames without .txt) for a language."""
    root = _data_root()
    story_dir = root / "stories" / language
    names = []
    try:
        for entry in story_dir.iterdir():
            name = entry.name
            if name.endswith(".txt"):
                names.append(name[:-4])
    except (FileNotFoundError, OSError, NotADirectoryError):
        return []
    return sorted(names)


# Map typographic punctuation to typeable ASCII (curly quotes → straight;
# guillemets / dashes / ellipsis → space so they fall out as separators).
_PUNCT_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "«": " ", "»": " ", "‹": " ", "›": " ",
    "—": " ", "–": " ", "‒": " ", "…": " ",
})


def _split_sentences(text: str) -> list[str]:
    """Split raw prose into sentences (paragraph-aware, on .!? + whitespace)."""
    sentences: list[str] = []
    for paragraph in text.strip().split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            sentence = sentence.strip()
            if sentence:
                sentences.append(sentence)
    return sentences


def _pool_from_sentences(
    sentences: list[str],
    *,
    accents: bool,
    punctuation: bool,
    numbers: bool,
) -> tuple[list[str], list[int]]:
    """Turn a list of sentence strings into (ordered_words, sentence_ends).

    Words are kept in reading order. Surrounding punctuation is stripped unless
    punctuation is enabled, so the typed word matches the narrative token.
    sentence_ends holds the index of the last word of each sentence.
    """
    words: list[str] = []
    sentence_ends: list[int] = []
    for sentence in sentences:
        sentence = sentence.translate(_PUNCT_MAP)
        added = False
        for token in sentence.split():
            word = unicodedata.normalize("NFC", token)
            if not punctuation:
                # Strip surrounding punctuation; keep internal (e.g. dall'intrepido)
                word = word.strip("!?.,;:\"'()[]{}*-")
            if len(word) < levels.MIN_COMBO_WORD_LEN:
                continue
            if not accents and _has_accent(word):
                continue
            if not numbers and word.isdigit():
                continue
            words.append(word)
            added = True
        if added:
            sentence_ends.append(len(words) - 1)
    return words, sentence_ends


def build_story_pool(
    language: str,
    story_name: str,
    *,
    accents: bool = False,
    punctuation: bool = False,
    numbers: bool = False,
) -> tuple[list[str], list[int], set[str]]:
    """Load a story file and return (ordered_words, sentence_ends, stopwords)."""
    root = _data_root()
    story_file = root / "stories" / language / f"{story_name}.txt"
    text = story_file.read_text(encoding="utf-8")
    stops = load_stops(language)
    words, sentence_ends = _pool_from_sentences(
        _split_sentences(text),
        accents=accents, punctuation=punctuation, numbers=numbers,
    )
    return words, sentence_ends, stops


def build_live_pool(
    sentences: list[str],
    language: str = "en",
    *,
    accents: bool = True,
    punctuation: bool = False,
    numbers: bool = True,
) -> tuple[list[str], list[int], set[str]]:
    """Build a story pool from in-memory text (e.g. live HN titles).

    Each list item is treated as one sentence. Accents/numbers default on so
    real-world headlines aren't gutted; never reads or writes any file.
    """
    stops = load_stops(language)
    cleaned = [s.strip() for s in sentences if s and s.strip()]
    words, sentence_ends = _pool_from_sentences(
        cleaned,
        accents=accents, punctuation=punctuation, numbers=numbers,
    )
    return words, sentence_ends, stops


def _has_accent(word: str) -> bool:
    """Check if a word contains accented characters."""
    accented = set("àèéìòùÀÈÉÌÒÙ")
    return any(c in accented for c in word)


def _has_punctuation(word: str) -> bool:
    """Check if a word contains punctuation characters."""
    punct = set("!?.,;:'\"-()")
    return any(c in punct for c in word)
