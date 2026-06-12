"""Tests for input_handler._translate_key — key_code -> token mapping.

Regression guard for ROADBLOCK_1: Enter arrives as a *positive* key_code
(10/13), so it must be matched before the printable `chr()` branch,
otherwise it leaks through as the raw character '\n' and no menu/name-input
ever sees the "enter" token.
"""
import pytest
from termtype.game.input_handler import _translate_key


class TestControlKeysAsPositiveCodes:
    """Terminals deliver these as positive ASCII codes — they must NOT be
    swallowed by the printable-character branch."""

    @pytest.mark.parametrize("code", [10, 13])
    def test_enter(self, code):
        assert _translate_key(code) == "enter"

    @pytest.mark.parametrize("code", [0x08, 0x7f])
    def test_backspace(self, code):
        assert _translate_key(code) == "backspace"

    def test_esc(self):
        assert _translate_key(27) == "esc"

    def test_space(self):
        assert _translate_key(32) == "space"


class TestSpecialKeysAsNegativeCodes:
    def test_back(self):
        assert _translate_key(-300) == "backspace"

    def test_escape(self):
        assert _translate_key(-1) == "esc"

    @pytest.mark.parametrize("code,token", [
        (-204, "up"), (-206, "down"), (-203, "left"), (-205, "right"),
    ])
    def test_arrows(self, code, token):
        assert _translate_key(code) == token


class TestPrintable:
    def test_ascii_letter(self):
        assert _translate_key(ord("J")) == "J"

    def test_accented_nfc(self):
        assert _translate_key(ord("é")) == "é"


class TestIgnored:
    @pytest.mark.parametrize("code", [0, 9, -999])
    def test_returns_none(self, code):
        # NUL, Tab, and unknown special keys produce no token.
        assert _translate_key(code) is None
