"""Full-screen menus and navigation.

PLAN §8.1, §8.3, §8.4, §8.5, §8.7. Manual-smoke verified.
"""
from __future__ import annotations

import sys
import textwrap
import time
from typing import Any, Callable

from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError

from .input_handler import drain_events
from .wordsource import load_lang, t
from .progression import available_unlocks
from .charts import sparkline, bar_chart
from .renderer import Renderer
from .title import header_logo, dim_colour
from .eggs import konami_progress
from . import levels

# Bright palette for the hidden Konami header-flash easter egg.
_RAINBOW = (1, 3, 2, 6, 4, 5)


def _poll(screen: Screen) -> list[str]:
    """Drain events, unwinding to the wrapper re-entry loop on resize."""
    if screen.has_resized():
        raise ResizeScreenError("resized", None)
    return drain_events(screen)


def _sfx(audio: Any, name: str, volume: float = 0.7) -> None:
    """Play a menu SFX if an audio manager was provided."""
    if audio is not None:
        audio.play_sfx(name, volume=volume)


def _draw_header(screen: Screen, w: int, subtitle: str | None = None,
                 rainbow_tick: int | None = None) -> int:
    """Draw the figlet TERMTYPE header (+ optional subtitle) at the top.

    Shared chrome for the splash landing, profile select, and the main menu.
    `rainbow_tick` (when set) cycles the logo through a bright palette — used by
    the hidden Konami easter egg. Returns the first free row below the header.
    """
    logo = header_logo(w)
    block_w = max((len(ln) for ln in logo), default=0)
    x = max(0, (w - block_w) // 2)
    for i, line in enumerate(logo):
        if rainbow_tick is None:
            colour = 6
        else:
            colour = _RAINBOW[(i + rainbow_tick) % len(_RAINBOW)]
        try:
            screen.print_at(line, x, i, colour=colour, attr=1)
        except Exception:
            pass
    next_row = len(logo)
    if subtitle:
        _centered_print(screen, subtitle, next_row, w, colour=dim_colour(screen))
        next_row += 1
    return next_row


def profile_select_screen(
    screen: Screen,
    profiles: list[dict[str, Any]],
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> tuple[str, int | None]:
    """Profile select under the shared figlet header. Returns (action, id)."""
    subtitle = t("profile_select", lang, "Select Profile")

    if not profiles:
        h, w = screen.dimensions
        screen.clear_buffer(7, 0, 0)
        top = _draw_header(screen, w, subtitle=subtitle)
        _centered_print(screen, "No profiles. Press N to create one.",
                        max(top + 2, h // 2), w, colour=7)
        _centered_print(screen, "[N] New Profile  [Esc] Back", h - 1, w, colour=7)
        screen.refresh()
        while True:
            for key in _poll(screen):
                if key in ("n", "N"):
                    return "create", None
                if key == "esc":
                    return "back", None
            time.sleep(0.05)

    selected = 0
    while True:
        h, w = screen.dimensions
        screen.clear_buffer(7, 0, 0)
        list_top = _draw_header(screen, w, subtitle=subtitle) + 1
        for i, profile in enumerate(profiles):
            marker = ">" if i == selected else " "
            name = profile["display_name"]
            screen.print_at(f"{marker} {name}", 2, list_top + i,
                            colour=7 if i == selected else 8)
        _centered_print(screen, "[N] New  [Enter] Select  [Esc] Back", h - 1, w, colour=7)
        screen.refresh()

        for key in _poll(screen):
            if key == "up" or key == "k":
                selected = max(0, selected - 1)
                _sfx(audio, "menu_move.wav")
            elif key == "down" or key == "j":
                selected = min(len(profiles) - 1, selected + 1)
                _sfx(audio, "menu_move.wav")
            elif key == "enter":
                _sfx(audio, "menu_select.wav")
                return "select", profiles[selected]["id"]
            elif key in ("n", "N"):
                _sfx(audio, "menu_select.wav")
                return "create", None
            elif key == "esc":
                return "back", None
        time.sleep(0.05)


def main_menu_screen(
    screen: Screen,
    profile_name: str,
    lang: dict[str, str],
    has_session: bool = False,
    ascii_mode: bool = False,
    audio: Any = None,
) -> str:
    """Main menu: figlet header + per-option descriptions. Returns action.

    Dedicated renderer (not list_menu) so the logo that lands from the splash
    stays as the header and items build in beneath it. Esc means quit.
    """
    items: list[tuple] = []
    if has_session:
        items.append(("continue", t("continue_hint", lang, "Continue"), "c",
                      t("desc_continue", lang, "Resume your saved run.")))
    items.extend([
        ("vocab", "Vocab Mode", "v", t("desc_vocab", lang, "Endless falling words.")),
        ("story", "Story Mode", "s", t("desc_story", lang, "Type a classic novel.")),
        ("stats", t("menu_stats", lang, "Stats"), None, t("desc_stats", lang, "Your stats.")),
        ("settings", t("menu_settings", lang, "Settings"), None,
         t("desc_settings", lang, "Options.")),
        ("switch", "Switch Profile", None, t("desc_switch", lang, "Change profile.")),
        ("credits", t("menu_credits", lang, "Credits"), None,
         t("desc_credits", lang, "Credits and license.")),
        ("quit", t("menu_quit", lang, "Quit"), "q", t("desc_quit", lang, "Exit.")),
    ])
    norm = _norm_items(items)
    footer = ("↑↓ move   ⏎ select   Esc quit" if not ascii_mode
              else "Up/Down move   Enter select   Esc quit")
    selected = 0
    konami: list[str] = []       # rolling buffer for the hidden code
    rainbow_until = 0.0          # monotonic time the header rainbow-flash ends

    while True:
        h, w = screen.dimensions
        if h < 24 or w < 80:
            _render_resize_prompt(screen); _poll(screen); time.sleep(0.05); continue

        now = time.monotonic()
        tick = int(now * 8) if now < rainbow_until else None
        screen.clear_buffer(7, 0, 0)
        top = _draw_header(screen, w, subtitle=profile_name, rainbow_tick=tick) + 1
        for i, (_, label, hot, _desc) in enumerate(norm):
            marker = "> " if i == selected else "  "
            hint = f" ({hot})" if hot else ""
            _centered_print(screen, f"{marker}{label}{hint}", top + i, w,
                            colour=6 if i == selected else 7,
                            attr=1 if i == selected else 0)
        desc = norm[selected][3]
        box_y = top + len(norm) + 1
        if desc and box_y + 4 <= h - 1:
            _description_box(screen, desc, box_y, w, ascii_mode)
        _centered_print(screen, footer, h - 1, w, colour=7)
        screen.refresh()

        for key in _poll(screen):
            k = key.lower() if len(key) == 1 else key
            # Hidden Konami code rainbow-flashes the header (cosmetic only).
            if konami_progress(konami, k):
                rainbow_until = time.monotonic() + 2.0
                _sfx(audio, "level_up.wav", volume=0.5)
            if key in ("up", "k"):
                selected = (selected - 1) % len(norm); _sfx(audio, "menu_move.wav")
            elif key in ("down", "j"):
                selected = (selected + 1) % len(norm); _sfx(audio, "menu_move.wav")
            elif key == "enter":
                _sfx(audio, "menu_select.wav"); return norm[selected][0]
            elif key == "esc":
                return "quit"  # Esc at the top menu means quit
            else:
                for value, _, hot, _d in norm:
                    if hot and k == hot.lower():
                        _sfx(audio, "menu_select.wav"); return value
        time.sleep(0.05)


def _prettify_story(name: str) -> str:
    """Turn a story filename stem into a display title."""
    return name.replace("_", " ").title()


def _render_resize_prompt(screen: Screen) -> None:
    """Centered below-minimum prompt (PLAN §8.3 hard render floor)."""
    h, w = screen.dimensions
    screen.clear()
    prompt = "Terminal too small. Please resize to at least 80x24."
    try:
        screen.print_at(prompt[:max(0, w)], max(0, (w - len(prompt)) // 2), max(0, h // 2))
        screen.refresh()
    except Exception:
        pass


def _norm_items(items: list[tuple]) -> list[tuple]:
    """Normalize menu items to uniform (value, label, hotkey, description)."""
    return [
        (it[0], it[1],
         it[2] if len(it) > 2 else None,
         it[3] if len(it) > 3 else None)
        for it in items
    ]


def _wrap_desc(text: str, width: int) -> list[str]:
    """Wrap a description to at most 2 lines, ellipsizing any overflow."""
    if not text or width < 4:
        return []
    return textwrap.wrap(text, width, max_lines=2, placeholder="...")[:2]


def _description_box(screen: Screen, text: str, y: int, w: int, ascii_mode: bool) -> None:
    """Draw a small framed description box centered at row y (4 rows tall)."""
    if not text:
        return
    box_w = min(46, w - 4)
    if box_w < 8:
        return
    content_w = box_w - 4
    lines = _wrap_desc(text, content_w)
    if not lines:
        return
    while len(lines) < 2:
        lines.append("")

    x = max(0, (w - box_w) // 2)
    if ascii_mode:
        tl = tr = bl = br = "+"; hz, vt = "-", "|"
    else:
        tl, tr, bl, br, hz, vt = "┌", "┐", "└", "┘", "─", "│"
    try:
        screen.print_at(tl + hz * (box_w - 2) + tr, x, y, colour=dim_colour(screen))
        for i, line in enumerate(lines):
            screen.print_at(vt + " " + line.ljust(content_w) + " " + vt,
                            x, y + 1 + i, colour=7)
        screen.print_at(bl + hz * (box_w - 2) + br, x, y + 3, colour=dim_colour(screen))
    except Exception:
        pass


def list_menu(
    screen: Screen,
    title: str,
    items: list[tuple],
    *,
    ascii_mode: bool = False,
    audio: Any = None,
    min_h: int = 24,
    min_w: int = 80,
    footer: str | None = None,
) -> Any:
    """Generic vertical list menu — the shared navigation surface.

    items: (value, label[, hotkey[, description]]). Navigate with Up/Down or
    j/k, select with Enter or a label's hotkey. Esc returns None. A highlighted
    item with a description shows it in a box below the list (when it fits).
    Renders the below-minimum resize prompt instead of clipping.
    """
    norm = _norm_items(items)
    if footer is None:
        arrows = "Up/Down" if ascii_mode else "↑↓"
        enter = "Enter" if ascii_mode else "⏎"
        footer = f"{arrows} move   {enter} select   Esc back"
    selected = 0

    while True:
        h, w = screen.dimensions
        if h < min_h or w < min_w:
            _render_resize_prompt(screen)
            _poll(screen)
            time.sleep(0.05)
            continue

        screen.clear_buffer(7, 0, 0)
        _centered_print(screen, title, 1, w, colour=6)
        top = max(3, h // 2 - len(norm) // 2)
        for i, (_, label, hot, _desc) in enumerate(norm):
            marker = "> " if i == selected else "  "
            hint = f" ({hot})" if hot else ""
            _centered_print(screen, f"{marker}{label}{hint}", top + i, w,
                            colour=6 if i == selected else 7,
                            attr=1 if i == selected else 0)
        desc = norm[selected][3]
        box_y = top + len(norm) + 1
        if desc and box_y + 4 <= h - 1:
            _description_box(screen, desc, box_y, w, ascii_mode)
        _centered_print(screen, footer, h - 1, w, colour=7)
        screen.refresh()

        for key in _poll(screen):
            k = key.lower() if len(key) == 1 else key
            if key in ("up", "k"):
                selected = (selected - 1) % len(norm)
                _sfx(audio, "menu_move.wav")
            elif key in ("down", "j"):
                selected = (selected + 1) % len(norm)
                _sfx(audio, "menu_move.wav")
            elif key == "enter":
                _sfx(audio, "menu_select.wav")
                return norm[selected][0]
            elif key == "esc":
                return None
            else:
                for value, _, hot, _d in norm:
                    if hot and k == hot.lower():
                        _sfx(audio, "menu_select.wav")
                        return value
        time.sleep(0.05)


def _vals(rows: list[dict], key: str) -> list[float]:
    """Pull a numeric series from history rows (oldest→newest), None→0."""
    return [float(r.get(key) or 0) for r in rows]


def _graph(screen: Screen, label: str, data: list[float], row: int, w: int, ascii_mode: bool) -> None:
    """Render a labelled one-row chart left-aligned with a 1-col margin."""
    _try_print(screen, label, 2, row, colour=7)
    chart = sparkline(data, max(1, w - 4), ascii_mode=ascii_mode)
    _try_print(screen, chart, 2, row + 1, colour=6)


def _try_print(screen: Screen, text: str, x: int, y: int, colour: int = 7) -> None:
    try:
        screen.print_at(text, x, y, colour=colour)
    except Exception:
        pass


def stats_page_screen(
    screen: Screen,
    stats: dict,
    history: list[dict],
    earned_badges: set,
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> None:
    """Full Stats page (PLAN §8.4): summary + 4 trend graphs with pagination,
    a sparse table under 5 games, and the below-minimum resize prompt."""
    games = stats.get("games_played", 0)
    series = list(reversed(history))  # history is newest-first; charts go oldest→newest
    page = 0

    while True:
        h, w = screen.dimensions
        if h < 15 or w < 80:
            _render_resize_prompt(screen); _poll(screen); time.sleep(0.05); continue

        screen.clear()
        _centered_print(screen, "Stats", 0, w, colour=6)

        if games < 5:
            _render_stats_sparse(screen, series, w, h)
            footer = "Esc back"
        elif page == 0:
            _render_stats_summary(screen, stats, earned_badges, w)
            _graph(screen, "WPM (last games)", _vals(series, "wpm"), 8, w, ascii_mode)
            _graph(screen, "Accuracy % (last games)", _vals(series, "accuracy"), 11, w, ascii_mode)
            footer = "→ next   Esc back   (page 1/2)"
        else:
            _graph(screen, "Score per game", _vals(series, "score"), 3, w, ascii_mode)
            _graph(screen, "Highest level per game", _vals(series, "level"), 6, w, ascii_mode)
            footer = "← prev   Esc back   (page 2/2)"

        _centered_print(screen, footer, h - 1, w, colour=7)
        screen.refresh()

        for key in _poll(screen):
            if key == "esc":
                return
            if games >= 5:
                if key in ("right", "l", "n", "enter") and page == 0:
                    page = 1; _sfx(audio, "menu_move.wav")
                elif key in ("left", "h", "p") and page == 1:
                    page = 0; _sfx(audio, "menu_move.wav")
        time.sleep(0.05)


def _render_stats_summary(screen: Screen, stats: dict, earned_badges: set, w: int) -> None:
    """~6-row lifetime summary block."""
    secs = stats.get("total_seconds_played", 0) or 0
    chars = stats.get("total_correct_chars", 0) or 0
    avg_wpm = (chars / 5.0) / (secs / 60.0) if secs > 0 else 0.0
    lines = [
        f"Games {stats.get('games_played', 0)}    "
        f"Best {stats.get('best_score', 0):,}    Cumulative {stats.get('cumulative_score', 0):,}",
        f"WPM best {stats.get('best_wpm', 0):.0f} / avg {avg_wpm:.0f}    "
        f"Accuracy best {stats.get('best_accuracy', 0):.0f}%",
        f"Highest level {stats.get('highest_level', 0)}    Max combo {stats.get('max_combo', 0)}",
        f"Words typed {stats.get('words_typed', 0)}  /  missed {stats.get('words_missed', 0)}    "
        f"Time {secs / 60:.0f} min",
        f"Badges: {', '.join(sorted(earned_badges)) if earned_badges else '—'}",
    ]
    for i, line in enumerate(lines):
        _try_print(screen, line, 2, 2 + i, colour=7)


def _render_stats_sparse(screen: Screen, series: list[dict], w: int, h: int) -> None:
    """Compact per-game table shown under 5 games (PLAN §8.4)."""
    _try_print(screen, "Played      Score      WPM   Acc   Lvl", 2, 2, colour=7)
    row = 3
    for r in reversed(series):  # newest first in the table
        if row >= h - 2:
            break
        played = str(r.get("played_at", ""))[:10]
        line = (f"{played:<10}  {int(r.get('score') or 0):>8,}  "
                f"{float(r.get('wpm') or 0):>4.0f}  {float(r.get('accuracy') or 0):>3.0f}%  "
                f"{int(r.get('level') or 0):>3}")
        _try_print(screen, line, 2, row, colour=7)
        row += 1
    _try_print(screen, "Play 5 games to unlock trend graphs.", 2, min(h - 2, row + 1), colour=7)


def options_screen(
    screen: Screen,
    config: dict,
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> dict | None:
    """Pre-game difficulty modifiers (PLAN §3.2). Toggle Numbers/Accents/
    Punctuation, then Start. Returns the option_flags dict, or None on Back."""
    flags = {
        "numbers": bool(config.get("difficulty_numbers", 0)),
        "accents": bool(config.get("difficulty_accents", 0)),
        "punctuation": bool(config.get("difficulty_punctuation", 0)),
    }
    rows = ["numbers", "accents", "punctuation"]
    labels = {"numbers": "Numbers", "accents": "Accents (à è é)", "punctuation": "Punctuation"}
    hotkeys = {"n": "numbers", "a": "accents", "p": "punctuation"}
    desc_keys = {"numbers": "desc_opt_numbers", "accents": "desc_opt_accents",
                 "punctuation": "desc_opt_punctuation"}
    selected = 0

    def on(v):
        if ascii_mode:
            return "[on] " if v else "[off]"
        return "[x]" if v else "[ ]"

    while True:
        h, w = screen.dimensions
        if h < 24 or w < 80:
            _render_resize_prompt(screen); _poll(screen); time.sleep(0.05); continue
        screen.clear_buffer(7, 0, 0)
        _centered_print(screen, "Game Options", 1, w, colour=6)
        top = max(3, h // 2 - len(rows) // 2)
        for i, key in enumerate(rows):
            mark = "> " if i == selected else "  "
            line = f"{mark}{on(flags[key])} {labels[key]}"
            _centered_print(screen, line, top + i, w,
                            colour=6 if i == selected else 7, attr=1 if i == selected else 0)
        box_y = top + len(rows) + 1
        desc = t(desc_keys[rows[selected]], lang, "")
        if desc and box_y + 4 <= h - 1:
            _description_box(screen, desc, box_y, w, ascii_mode)
        legend = ("↑↓ move   Space toggle   ⏎ Start   Esc back" if not ascii_mode
                  else "Up/Down move   Space toggle   Enter Start   Esc back")
        _centered_print(screen, legend, h - 1, w, colour=7)
        screen.refresh()

        for key in _poll(screen):
            k = key.lower() if len(key) == 1 else key
            if key in ("up", "k"):
                selected = (selected - 1) % len(rows); _sfx(audio, "menu_move.wav")
            elif key in ("down", "j"):
                selected = (selected + 1) % len(rows); _sfx(audio, "menu_move.wav")
            elif key == "esc":
                return None
            elif key == "enter":           # Enter starts the game from anywhere
                _sfx(audio, "menu_select.wav")
                return flags
            elif key == "space":           # Space toggles the selected modifier
                flags[rows[selected]] = not flags[rows[selected]]
                _sfx(audio, "menu_move.wav")
            elif k in hotkeys:             # n/a/p toggle their modifier directly
                flags[hotkeys[k]] = not flags[hotkeys[k]]
                _sfx(audio, "menu_move.wav")
        time.sleep(0.05)


# Sentinel returned by story_select_screen when the live HN sub-mode is chosen.
HN_MODE = "__hn__"


def story_difficulty_screen(
    screen: Screen,
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> str | None:
    """Pick the story sub-mode. Returns 'challenge', 'zen', or None on Back."""
    items = [
        ("challenge", "Challenge  (lives on — recommended)", "c",
         t("desc_story_challenge", lang, "Lives on — miss too many words and the run ends.")),
        ("zen", "Zen  (no fail; drowned words auto-complete)", "z",
         t("desc_story_zen", lang, "No fail: drowned words complete themselves.")),
    ]
    return list_menu(screen, "Story Difficulty", items, ascii_mode=ascii_mode, audio=audio)


def story_select_screen(
    screen: Screen,
    stories: list[str],
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> str | None:
    """Pick a story (or the live HN sub-mode). Returns the story name,
    HN_MODE, or None if cancelled."""
    hn_desc = t("desc_hn", lang, "Type today's top Hacker News headlines, fetched live.")
    story_desc = t("desc_story_generic", lang, "A public-domain classic, typed in reading order.")
    items: list[tuple] = [(HN_MODE, "Hacker News  (live top stories)", "h", hn_desc)]
    for name in stories:
        items.append((name, _prettify_story(name), None, story_desc))
    return list_menu(screen, "Choose a Story", items,
                     ascii_mode=ascii_mode, audio=audio)


def pause_screen(
    screen: Screen,
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
) -> str:
    """Pause screen with controls legend. Returns action."""
    h, w = screen.dimensions
    screen.clear()

    _centered_print(screen, t("pause_title", lang, "Paused"), h // 2 - 3, w, colour=6)

    controls = [
        "Type first letter to lock onto a word",
        "Backspace: fix typo  |  Double-Backspace: abandon",
        "Esc: pause  |  R: retry",
    ]
    y = h // 2 - 1
    for line in controls:
        _centered_print(screen, line, y, w, colour=7)
        y += 1

    _centered_print(screen, "[Esc] Resume   [Q] Quit to Menu", h - 1, w, colour=7)
    screen.refresh()

    while True:
        keys = _poll(screen)
        for key in keys:
            if key in ("esc", "r", "R"):
                return "resume"
            if key in ("q", "Q"):
                return "quit"
        time.sleep(0.05)


def game_over_screen(
    screen: Screen,
    score: int,
    best_score: int,
    wpm: float,
    accuracy: float,
    level: int,
    lang: dict[str, str],
    ascii_mode: bool = False,
    audio: Any = None,
    story_fluency: int | None = None,
) -> str:
    """Game over / chapter-complete screen. R-to-retry is live immediately."""
    h, w = screen.dimensions
    screen.clear()

    if story_fluency is not None:
        _centered_print(screen, "Chapter Complete!", 1, w, colour=6)
        _centered_print(screen, f"Fluency {story_fluency}  (WPM x accuracy x pace)", 6, w, colour=6)
    else:
        _centered_print(screen, t("game_over", lang, "Game Over"), 1, w, colour=1)

    # Best run comparison
    diff = best_score - score
    if diff > 0:
        _centered_print(screen, f"Score: {score:,}  ({diff:,} from best)", 3, w, colour=7)
    else:
        _centered_print(screen, f"Score: {score:,}  NEW BEST!", 3, w, colour=6)

    stats_lines = [
        f"Level: {level}  WPM: {wpm:.0f}  Accuracy: {accuracy:.0f}%",
    ]
    y = 5
    for line in stats_lines:
        _centered_print(screen, line, y, w, colour=7)
        y += 1

    _centered_print(screen, "[R] Retry   [S] Save & Quit   [Q] Quit to Menu", h - 1, w, colour=7)
    screen.refresh()

    while True:
        keys = _poll(screen)
        for key in keys:
            if key in ("r", "R"):
                _sfx(audio, "menu_select.wav")
                return "retry"
            if key in ("s", "S"):
                _sfx(audio, "menu_select.wav")
                return "save"
            if key in ("q", "Q", "esc"):
                return "quit"
        time.sleep(0.05)


def settings_screen(
    screen: Screen,
    config: dict[str, Any],
    lang: dict[str, str],
    earned_badges: set[str],
    lifetime_stats: dict[str, Any],
    audio_available: bool = True,
    ascii_mode: bool = False,
    audio: Any = None,
) -> dict[str, Any]:
    """Settings screen. Returns updated config."""
    h, w = screen.dimensions
    selected = 0

    # Build settings rows
    unlocks = available_unlocks(lifetime_stats, earned_badges)

    settings_rows = [
        ("language", f"Language: {config.get('language', 'en')}"),
        ("music", f"Music: {'ON' if config.get('music_on') else 'OFF'}"),
        ("sfx", f"SFX: {'ON' if config.get('sfx_on', 1) else 'OFF'}"),
        ("reduced_motion", f"Reduced Motion: {'ON' if config.get('reduced_motion') else 'OFF'}"),
    ]

    # Add unlock rows
    for uid, available in unlocks.items():
        status = "UNLOCKED" if available else "locked"
        settings_rows.append((uid, f"{uid}: {status}"))

    while True:
        # Rebuild rows each iteration so toggles are reflected
        settings_rows = [
            ("language", f"Language: {config.get('language', 'en')}"),
            ("music", f"Music: {'ON' if config.get('music_on') else 'OFF'}"),
            ("sfx", f"SFX: {'ON' if config.get('sfx_on', 1) else 'OFF'}"),
            ("reduced_motion", f"Reduced Motion: {'ON' if config.get('reduced_motion') else 'OFF'}"),
        ]
        for uid, available in unlocks.items():
            status = "UNLOCKED" if available else "locked"
            settings_rows.append((uid, f"{uid}: {status}"))

        screen.clear()
        _centered_print(screen, t("settings_title", lang, "Settings"), 1, w, colour=6)

        if not audio_available:
            _centered_print(screen, "Audio unavailable on this system", 3, w, colour=dim_colour(screen))

        y = 4
        for i, (key, label) in enumerate(settings_rows):
            marker = ">" if i == selected else " "
            colour = 7 if i == selected else 8
            screen.print_at(f"{marker} {label}", 2, y, colour=colour)
            y += 1

        _centered_print(screen, "[↑↓] Move  [Enter] Toggle  [Esc] Back", h - 1, w, colour=7)
        screen.refresh()

        keys = _poll(screen)
        for key in keys:
            if key == "up" or key == "k":
                selected = max(0, selected - 1)
                _sfx(audio, "menu_move.wav")
            elif key == "down" or key == "j":
                selected = min(len(settings_rows) - 1, selected + 1)
                _sfx(audio, "menu_move.wav")
            elif key == "enter":
                _sfx(audio, "menu_select.wav")
                row_key = settings_rows[selected][0]
                if row_key == "language":
                    config["language"] = "it" if config.get("language") == "en" else "en"
                elif row_key == "music":
                    config["music_on"] = 0 if config.get("music_on") else 1
                elif row_key == "sfx":
                    config["sfx_on"] = 0 if config.get("sfx_on", 1) else 1
                elif row_key == "reduced_motion":
                    config["reduced_motion"] = 0 if config.get("reduced_motion") else 1
            elif key == "esc":
                return config
        time.sleep(0.05)


def _centered_print(screen: Screen, text: str, y: int, w: int, colour: int = 7, attr: int = 0) -> None:
    """Print text centered on the screen."""
    x = max(0, (w - len(text)) // 2)
    try:
        screen.print_at(text, x, y, colour=colour, attr=attr)
    except Exception:
        pass
