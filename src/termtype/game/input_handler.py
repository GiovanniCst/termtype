"""Thin asciimatics Event adapter — drains events, emits plain chars/keys.

PLAN §2.3, §6.2. Converts KeyboardEvent.key_code to plain chars + tokens.
"""
from __future__ import annotations

import unicodedata
from typing import Iterator

from asciimatics.event import KeyboardEvent
from asciimatics.screen import Screen


def drain_events(screen: Screen) -> list[str]:
    """Drain all pending input events and return a list of key tokens.

    Each token is either a single printable character (NFC-normalized)
    or a named token: 'backspace', 'esc', 'enter', 'space', 'resize'.
    """
    keys = []
    while True:
        ev = screen.get_event()
        if ev is None:
            break
        if isinstance(ev, KeyboardEvent):
            key = _translate_key(ev.key_code)
            if key:
                keys.append(key)
    return keys


def _translate_key(key_code: int) -> str | None:
    """Translate a KeyboardEvent.key_code to a token.

    PLAN §6.2. Named/control keys MUST be matched before the printable
    branch: terminals deliver Enter as a positive code (10/13), Backspace
    as 8/127, Esc as 27, Space as 32 — all positive — so a naive
    `key_code > 0 -> chr()` swallows them as raw characters. (asciimatics
    has no Screen.KEY_ENTER constant; Enter only ever arrives as 10/13.)
    """
    if key_code == 0:
        return None  # NUL / IME composition

    # Named keys delivered as positive ASCII control codes
    if key_code in (10, 13):
        return "enter"
    if key_code in (0x08, 0x7f):
        return "backspace"
    if key_code == 27:
        return "esc"
    if key_code == 32:
        return "space"

    # Named keys delivered as negative asciimatics constants
    if key_code < 0:
        if key_code == Screen.KEY_BACK:
            return "backspace"
        if key_code == Screen.KEY_ESCAPE:
            return "esc"
        if key_code == Screen.KEY_UP:
            return "up"
        if key_code == Screen.KEY_DOWN:
            return "down"
        if key_code == Screen.KEY_LEFT:
            return "left"
        if key_code == Screen.KEY_RIGHT:
            return "right"
        return None  # unknown special key

    # Printable character (positive, non-control)
    if key_code < 32:
        return None  # other control chars (Tab, etc.)
    try:
        char = chr(key_code)
        return unicodedata.normalize("NFC", char)
    except (ValueError, OverflowError):
        return None
