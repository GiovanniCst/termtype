"""Entry point for the termtype console script.

PLAN §2.4, §3.1, §5, §7, §8.5, §8.7. Ties everything together.

The whole app runs inside ONE Screen.wrapper as a phase state machine —
no terminal teardown/reinit between menus, so transitions are instant.
ResizeScreenError unwinds to the re-entry loop below with all state
(including a mid-run GameState) preserved on the App object.
"""
from __future__ import annotations

import json
import locale
import sys
import time
from datetime import datetime
from typing import Any

from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError

from termtype.persistence.db import open_db
from termtype.persistence.profiles import (
    create_profile, list_profiles, get_profile,
    set_last_active, get_last_active,
)
from termtype.persistence.config import load_config, save_config
from termtype.persistence.sessions import (
    save_session, load_session, apply_resume_penalty,
)
from termtype.persistence.stats import (
    game_over_commit, get_stats, get_earned_badges, get_recent_play_dates,
    get_game_history,
)
from termtype.persistence.scores import build_leaderboard_key
from termtype.game.state import GameState
from termtype.game.engine import play_session
from termtype.game.wordsource import (
    build_word_pool, build_story_pool, build_live_pool, list_stories, load_lang,
)
from termtype.game import hn
from termtype.game.audio import create_audio_manager
from termtype.game.title import title_splash, credits_screen
from termtype.game.progression import GamePayload, evaluate_badges
from termtype.game import levels
from termtype.game.menus import (
    profile_select_screen, main_menu_screen, game_over_screen,
    settings_screen, story_select_screen, options_screen, story_difficulty_screen,
    stats_page_screen, HN_MODE, _centered_print, _poll,
)


def _enable_windows_utf8() -> None:
    """Switch the Windows console to UTF-8 so box-drawing and arrows render.

    Windows reports a legacy code page (e.g. cp1252) by default, which would
    drop the game into ASCII mode even though modern terminals (Windows
    Terminal, Win10+ conhost) handle UTF-8 fine. No-op off Windows; harmless if
    the console rejects the switch (we still fall back to ASCII via detection).
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _clamp_colour(c: Any, palette: int) -> Any:
    """Map a colour index the terminal can't display to white.

    Out-of-palette indices are the failure mode, not a value to preserve: the
    Windows console exposes only 0-7 and KeyErrors at refresh() on anything
    higher, and white is always legible. Gray/bright-black (8) included.
    """
    return c if c is None or c < palette else 7


def _install_colour_guard(screen: Screen) -> None:
    """Clamp every print_at colour to the screen's palette.

    A belt-and-suspenders boundary: rather than auditing dozens of call sites
    for stray high colour indices (8 = gray, 244/202 = 256-palette HN chrome),
    fix it once where pixels meet the terminal. No-op on full 256-colour
    terminals, so the dev box is unaffected. Re-installed per screen (resize
    rebuilds it), which is why it lives at the top of App.run.
    """
    palette = getattr(screen, "colours", 256) or 256
    if palette >= 256:
        return
    original = screen.print_at

    def guarded(text, x, y, colour=7, attr=0, bg=0, **kwargs):
        return original(text, x, y, colour=_clamp_colour(colour, palette),
                        attr=attr, bg=_clamp_colour(bg, palette), **kwargs)

    screen.print_at = guarded


def main() -> int:
    """Main entry point."""
    # Try UTF-8 first (esp. Windows), then detect whether the console can take
    # it. --ascii forces the ASCII glyph set regardless.
    _enable_windows_utf8()
    ascii_mode = "--ascii" in sys.argv
    if not ascii_mode and sys.platform != "win32":
        # On Windows asciimatics draws via the wide console API, so Unicode
        # renders regardless of the (legacy cp1252) code page — default to it.
        # Elsewhere a non-UTF-8 locale means the terminal really can't show the
        # glyphs, so fall back to ASCII. Either way --ascii forces ASCII.
        encoding = (getattr(sys.stdout, "encoding", "")
                    or locale.getpreferredencoding() or "").lower()
        if "utf" not in encoding:
            ascii_mode = True

    conn = open_db()
    app = App(conn, ascii_mode)

    try:
        while True:
            try:
                Screen.wrapper(app.run, unicode_aware=True)
                break
            except ResizeScreenError:
                continue  # rebuild the screen, resume the current phase
    finally:
        app.audio.cleanup()
        conn.close()

    return 0


class App:
    """Top-level phase state machine. Survives Screen rebuilds on resize."""

    def __init__(self, conn: Any, ascii_mode: bool):
        self.conn = conn
        self.ascii_mode = ascii_mode
        self.audio = create_audio_manager()
        self.lang = load_lang("en")
        self.phase = "title"
        self.profile_id: int | None = None
        self.profile: dict[str, Any] | None = None
        self.config: dict[str, Any] = {}
        # In-progress game, kept here so a resize mid-run resumes seamlessly
        self.game_state: GameState | None = None
        self.game_committed = False
        self.current_story: str | None = None  # active story file (story mode)

    def run(self, screen: Screen) -> None:
        """Run phases until quit. Re-entered with phase intact after resize."""
        _install_colour_guard(screen)
        while True:
            if self.phase == "title":
                self._phase_title(screen)
            elif self.phase == "profile":
                self._phase_profile(screen)
            elif self.phase == "menu":
                self._phase_menu(screen)
            elif self.phase == "game":
                self._phase_game(screen)
            elif self.phase == "game_over":
                self._phase_game_over(screen)
            else:  # "quit"
                self.audio.stop_music()
                return

    # ── Title splash ─────────────────────────────────────────────────────

    def _phase_title(self, screen: Screen) -> None:
        """Arcade attract splash, shown once at launch before the profile flow.

        Music honors the last-active profile's saved preference; a first-ever
        run (no profile) stays silent so the splash never pre-empts the
        first-run music opt-in (consent-before-sound).
        """
        last_id = get_last_active(self.conn)
        profile = get_profile(self.conn, last_id) if last_id else None
        reduced_motion = False
        if profile:
            cfg = load_config(self.conn, last_id)
            self.audio.set_enabled(bool(cfg.get("music_on")), bool(cfg.get("sfx_on", 1)))
            self.audio.set_music_volume(cfg.get("music_volume", 0.5))
            self.audio.set_sfx_volume(cfg.get("sfx_volume", 0.7))
            reduced_motion = bool(cfg.get("reduced_motion", 0))
            self.lang = load_lang(cfg.get("language", "en"))  # localize the prompt
            self.audio.play_music(self._mood_track("title"))

        title_splash(
            screen, self.audio, self.lang,
            ascii_mode=self.ascii_mode, reduced_motion=reduced_motion,
        )
        self.phase = "profile"

    # ── Profile ──────────────────────────────────────────────────────────

    def _phase_profile(self, screen: Screen) -> None:
        last_id = get_last_active(self.conn)
        if last_id and get_profile(self.conn, last_id):
            self._activate_profile(screen, last_id)
            return

        pid = self._select_profile(screen)
        if pid is None:
            self.phase = "quit"
            return
        self._activate_profile(screen, pid)

    def _select_profile(self, screen: Screen) -> int | None:
        """Profile select / create flow. Returns profile id or None (back)."""
        profiles = list_profiles(self.conn)
        while True:
            action, pid = profile_select_screen(
                screen, profiles, self.lang, audio=self.audio,
            )
            if action == "select" and pid is not None:
                set_last_active(self.conn, pid)
                return pid
            elif action == "create":
                name = _input_name(screen, self.lang)
                if name:
                    try:
                        pid = create_profile(self.conn, name)
                        set_last_active(self.conn, pid)
                        return pid
                    except ValueError:
                        _flash_message(screen, "Name already taken", self.lang)
            elif action == "back":
                return None
            profiles = list_profiles(self.conn)

    def _activate_profile(self, screen: Screen, pid: int) -> None:
        self.profile_id = pid
        self.config = load_config(self.conn, pid)
        self.profile = get_profile(self.conn, pid)
        self.lang = load_lang(self.config.get("language", "en"))
        self._maybe_prompt_music(screen)
        self._apply_audio_config()
        self.phase = "menu"

    def _maybe_prompt_music(self, screen: Screen) -> None:
        """First-run one-tap music opt-in (PLAN §8.5)."""
        if not self.audio.is_available():
            return
        try:
            extra = json.loads(self.config.get("json_extra") or "{}")
        except Exception:
            extra = {}
        if extra.get("music_prompted"):
            return

        h, w = screen.dimensions
        screen.clear()
        _centered_print(screen, "Music?  [Y]es / [N]o", h // 2, w, colour=6)
        screen.refresh()
        choice = None
        while choice is None:
            for key in _poll(screen):
                if key in ("y", "Y", "enter"):
                    choice = 1
                elif key in ("n", "N", "esc"):
                    choice = 0
            time.sleep(0.05)

        self.config["music_on"] = choice
        extra["music_prompted"] = 1
        self.config["json_extra"] = json.dumps(extra)
        save_config(self.conn, self.profile_id, self.config)

    def _apply_audio_config(self) -> None:
        self.audio.set_enabled(
            bool(self.config.get("music_on")),
            bool(self.config.get("sfx_on", 1)),
        )
        self.audio.set_music_volume(self.config.get("music_volume", 0.5))
        self.audio.set_sfx_volume(self.config.get("sfx_volume", 0.7))

    # ── Main menu ────────────────────────────────────────────────────────

    def _phase_menu(self, screen: Screen) -> None:
        self.audio.play_music(self._mood_track("title"))
        has_session = load_session(self.conn, self.profile_id) is not None
        action = main_menu_screen(
            screen, self.profile["display_name"], self.lang,
            has_session, self.ascii_mode, audio=self.audio,
        )

        if action == "quit":
            self.phase = "quit"
        elif action == "continue":
            if self._build_resumed_game():
                self.phase = "game"
        elif action == "vocab":
            flags = options_screen(
                screen, self.config, self.lang,
                ascii_mode=self.ascii_mode, audio=self.audio,
            )
            if flags is not None and self._build_new_game(flags):
                self.phase = "game"
        elif action == "story":
            if self._build_story_game(screen):
                self.phase = "game"
        elif action == "credits":
            credits_screen(
                screen, self.lang, ascii_mode=self.ascii_mode, audio=self.audio,
            )
        elif action == "stats":
            stats_page_screen(
                screen,
                get_stats(self.conn, self.profile_id),
                get_game_history(self.conn, self.profile_id),
                get_earned_badges(self.conn, self.profile_id),
                self.lang, ascii_mode=self.ascii_mode, audio=self.audio,
            )
        elif action == "settings":
            self.config = settings_screen(
                screen, self.config, self.lang,
                get_earned_badges(self.conn, self.profile_id),
                get_stats(self.conn, self.profile_id),
                audio_available=self.audio.is_available(),
                ascii_mode=self.ascii_mode,
                audio=self.audio,
            )
            save_config(self.conn, self.profile_id, self.config)
            self.lang = load_lang(self.config.get("language", "en"))
            self._apply_audio_config()
        elif action == "switch":
            pid = self._select_profile(screen)
            if pid is not None:
                self._activate_profile(screen, pid)

    # ── Game ─────────────────────────────────────────────────────────────

    def _build_new_game(self, option_flags: dict | None = None) -> bool:
        language = self.config.get("language", "en")
        if option_flags is None:
            option_flags = self._option_flags()
        try:
            enabled_packs = json.loads(self.config.get("enabled_packs", "[]"))
        except Exception:
            enabled_packs = []
        word_pool = build_word_pool(language, option_flags, enabled_packs)
        if not word_pool:
            return False

        state = GameState(
            word_pool=word_pool, mode="vocab",
            language=language, option_flags=option_flags,
        )
        # Returning profile starts at best-level - 2; first-ever game gets the
        # onboarding first-letter highlight (§2.3).
        stats = get_stats(self.conn, self.profile_id)
        state.is_first_game = stats.get("games_played", 0) == 0
        best_level = stats.get("highest_level", 0)
        if best_level > 2:
            state.level = max(1, best_level - 2)

        self.game_state = state
        self.game_committed = False
        return True

    def _option_flags(self) -> dict[str, bool]:
        return {
            "numbers": bool(self.config.get("difficulty_numbers", 0)),
            "accents": bool(self.config.get("difficulty_accents", 0)),
            "punctuation": bool(self.config.get("difficulty_punctuation", 0)),
        }

    def _build_story_game(self, screen: Screen) -> bool:
        language = self.config.get("language", "en")
        stories = list_stories(language)
        if not stories and language != "en":
            language, stories = "en", list_stories("en")

        choice = story_select_screen(
            screen, stories, self.lang, ascii_mode=self.ascii_mode, audio=self.audio,
        )
        if choice is None:
            return False
        if choice == HN_MODE:
            return self._build_hn_game(screen)

        diff = story_difficulty_screen(
            screen, self.lang, ascii_mode=self.ascii_mode, audio=self.audio,
        )
        if diff is None:
            return False

        option_flags = self._option_flags()
        # Stories are read faithfully: keep accents/numbers so Italian prose
        # isn't gutted; punctuation still follows the difficulty toggle.
        words, sentence_ends, stops = build_story_pool(
            language, choice,
            accents=True, punctuation=option_flags["punctuation"], numbers=True,
        )
        if not words:
            _flash_message(screen, "That story has no playable words.", self.lang)
            return False

        state = GameState(
            word_pool=words, mode="story", zen=(diff == "zen"),
            language=language, option_flags=option_flags,
            story_words=words, sentence_ends=set(sentence_ends), stopwords=stops,
        )
        state.is_first_game = get_stats(self.conn, self.profile_id).get("games_played", 0) == 0
        self.current_story = choice
        self.game_state = state
        self.game_committed = False
        return True

    def _build_hn_game(self, screen: Screen) -> bool:
        """Live Hacker News sub-mode: fetch the current top titles and type
        them as the story assembles a fake HN front page. Never persisted."""
        h, w = screen.dimensions
        screen.clear()
        _centered_print(screen, "Fetching Hacker News...", h // 2, w, colour=6)
        screen.refresh()

        try:
            titles = hn.fetch_top_titles(limit=20, timeout=6.0)
        except Exception:
            titles = []
        if len(titles) < 3:
            # Offline / HN unreachable: offer the baked-in all-time greats.
            if not _confirm(
                screen,
                "Hmm, I can't reach Hacker News right now.",
                "Type the most upvoted HN submissions of all time instead?",
            ):
                return False
            titles = hn.all_time_top_titles(20)

        option_flags = self._option_flags()
        words, sentence_ends, stops = build_live_pool(
            titles, language="en", punctuation=option_flags["punctuation"],
        )
        if not words:
            _flash_message(screen, "No typeable headlines right now.", self.lang)
            return False

        state = GameState(
            word_pool=words, mode="story",
            language="en", option_flags=option_flags,
            story_words=words, sentence_ends=set(sentence_ends), stopwords=stops,
            story_skin="hn", story_display_lines=titles,
        )
        state.is_first_game = get_stats(self.conn, self.profile_id).get("games_played", 0) == 0
        self.current_story = None  # HN runs change every fetch — not resumable
        self.game_state = state
        self.game_committed = False
        return True

    def _build_resumed_game(self) -> bool:
        session = load_session(self.conn, self.profile_id)
        if session is None:
            return False

        language = session.get("language", self.config.get("language", "en"))
        option_flags = session.get("option_flags", {})
        mode = session.get("mode", "vocab")

        if mode == "story":
            story_name = session.get("story_name")
            stories = list_stories(language)
            if not story_name or story_name not in stories:
                return False  # story no longer available — can't resume
            words, sentence_ends, stops = build_story_pool(
                language, story_name,
                accents=True,
                punctuation=option_flags.get("punctuation", False),
                numbers=True,
            )
            position = min(session.get("story_position", 0), len(words))
            state = GameState(
                word_pool=words, mode="story",
                language=language, option_flags=option_flags,
                story_words=words, sentence_ends=set(sentence_ends), stopwords=stops,
                story_position=position, story_words_done=position,
                level=session.get("level", 1),
                score=session.get("score", 0),
                lives=session.get("lives", levels.DEFAULT_LIVES),
            )
            self.current_story = story_name
        else:
            word_pool = build_word_pool(language, option_flags)
            if not word_pool:
                return False
            state = GameState(
                word_pool=word_pool, mode="vocab",
                language=language, option_flags=option_flags,
                level=session.get("level", 1),
                score=session.get("score", 0),
                lives=session.get("lives", levels.DEFAULT_LIVES),
            )

        state.score, _ = apply_resume_penalty(self.conn, self.profile_id, state.score)
        state.combo_count = 0  # Reset combo on resume

        self.game_state = state
        self.game_committed = False
        return True

    def _phase_game(self, screen: Screen) -> None:
        state = self.game_state
        # Game track intensity follows the difficulty band
        track = "level1" if state.level < 7 else ("level2" if state.level < 15 else "level3")
        self.audio.play_music(self._mood_track(track))

        play_session(
            screen, state,
            hard_lock=bool(self.config.get("hard_lock", 0)),
            no_backspace=bool(self.config.get("no_backspace", 0)),
            ascii_mode=self.ascii_mode,
            reduced_motion=bool(self.config.get("reduced_motion", 0)),
            audio=self.audio,
        )

        # Session over (lives exhausted or quit-to-menu) — commit once
        self.audio.stop_music()
        self.audio.play_sfx("game_over.wav")
        if not self.game_committed:
            _commit_game_over(self.conn, self.profile_id, state)
            self.game_committed = True
        self.phase = "game_over"

    def _phase_game_over(self, screen: Screen) -> None:
        state = self.game_state
        stats = get_stats(self.conn, self.profile_id)
        wpm = 0.0
        if state.time_played_seconds > 0:
            wpm = (state.correct_characters / 5.0) / (state.time_played_seconds / 60.0)
        accuracy = 100.0
        if state.total_keystrokes > 0:
            accuracy = (state.total_correct_keystrokes / state.total_keystrokes) * 100.0

        story_fluency = state.chapter_fluency if (state.mode == "story" and state.story_completed) else None
        action = game_over_screen(
            screen, state.score, stats.get("best_score", 0),
            wpm, accuracy, state.level, self.lang, self.ascii_mode,
            audio=self.audio, story_fluency=story_fluency,
        )
        if action == "retry":
            rebuilt = (self._build_story_game(screen) if state.mode == "story"
                       else self._build_new_game(state.option_flags))
            self.phase = "game" if rebuilt else "menu"
        elif action == "save":
            save_session(
                self.conn, self.profile_id, level=state.level, score=state.score,
                lives=state.lives, mode=state.mode, language=state.language,
                option_flags=state.option_flags,
                story_position=state.story_position,
                story_name=self.current_story if state.mode == "story" else None,
            )
            self.phase = "menu"
        else:  # "quit"
            self.phase = "menu"

    def _mood_track(self, name: str) -> str:
        mood = self.config.get("music_mood", "retro") or "retro"
        return f"{mood}/{name}.ogg"


# ── Screen helpers (run on the shared persistent Screen) ─────────────────


def _input_name(screen: Screen, lang: dict[str, str]) -> str | None:
    """Simple name input on screen."""
    h, w = screen.dimensions
    name = ""
    while True:
        screen.clear()
        screen.print_at(f"Enter name: {name}_", 2, h // 2, colour=7)
        screen.refresh()

        for key in _poll(screen):
            if key == "enter" and name.strip():
                return name.strip()
            elif key == "esc":
                return None
            elif key == "backspace":
                name = name[:-1]
            elif len(key) == 1 and len(name) < 32:
                name += key
        time.sleep(0.05)


def _confirm(screen: Screen, line1: str, line2: str) -> bool:
    """Yes/No prompt. Y or Enter confirms; N, Esc or Q declines."""
    h, w = screen.dimensions
    screen.clear()
    _centered_print(screen, line1, h // 2 - 1, w, colour=6)
    _centered_print(screen, line2, h // 2, w, colour=6)
    _centered_print(screen, "[Y] Yes      [N] No", h // 2 + 2, w, colour=7)
    screen.refresh()
    while True:
        for key in _poll(screen):
            k = key.lower() if isinstance(key, str) else key
            if k in ("y", "enter"):
                return True
            if k in ("n", "esc", "q"):
                return False
        time.sleep(0.05)


def _flash_message(screen: Screen, message: str, lang: dict[str, str]) -> None:
    """Show a brief dismiss-on-any-key message."""
    h, w = screen.dimensions
    screen.clear()
    _centered_print(screen, message, h // 2, w, colour=1)
    _centered_print(screen, "Press any key...", h // 2 + 2, w, colour=7)
    screen.refresh()
    while True:
        if _poll(screen):
            return
        time.sleep(0.05)


def _commit_game_over(conn: Any, profile_id: int, state: GameState) -> None:
    """Commit the game-over to the database."""
    leaderboard_key = build_leaderboard_key(state.mode, state.language, state.option_flags)
    payload_ts = datetime.now().isoformat()

    # WPM and accuracy
    wpm = 0.0
    if state.time_played_seconds > 0:
        minutes = state.time_played_seconds / 60.0
        wpm = (state.correct_characters / 5.0) / minutes if minutes > 0 else 0.0

    accuracy = 100.0
    if state.total_keystrokes > 0:
        accuracy = (state.total_correct_keystrokes / state.total_keystrokes) * 100.0

    # Evaluate badges
    stats = get_stats(conn, profile_id)
    earned = get_earned_badges(conn, profile_id)
    recent_dates = get_recent_play_dates(conn, profile_id)

    payload = GamePayload(
        highest_level=state.level,
        max_combo=state.combo_count,
        max_word_wpm=state.max_word_wpm,
        reached_plateau=state.reached_plateau,
        story_completed=state.story_completed,
    )
    new_badges = evaluate_badges(payload, stats, earned, recent_dates)

    game_over_commit(
        conn, profile_id,
        score=state.score,
        wpm=wpm,
        accuracy=accuracy,
        level=state.level,
        words_typed=state.words_typed,
        words_missed=state.words_missed,
        correct_chars=state.correct_characters,
        total_keystrokes=state.total_keystrokes,
        correct_keystrokes=state.total_correct_keystrokes,
        seconds_played=state.time_played_seconds,
        max_combo=state.combo_count,
        peak_score_rate=state.peak_score_rate,
        leaderboard_key=leaderboard_key,
        payload_ts=payload_ts,
        new_badges=new_badges,
    )


if __name__ == "__main__":
    raise SystemExit(main())
