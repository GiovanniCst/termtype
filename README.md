# TermType

A terminal typing game where words fall like Space Invaders — type them before they
hit the water line, or you drown.

Pure-terminal, no GUI. Built on [asciimatics](https://github.com/peterbrittain/asciimatics).

## Features

- **Arcade mode** — escalating waves, combos, lives, a danger "red zone" near the
  water line, and plateau surges that ramp the pressure the longer you survive.
- **Story mode** — type your way through public-domain books (English & Italian) in
  reading order, with a "typed so far" ribbon and resume-where-you-left-off. Pick Zen
  (relaxed) or Challenge difficulty.
- **Hacker News mode** — type over a live-rendered fake HN front page.
- **Progression** — profiles, a local stats page with sparkline charts, leaderboards,
  and unlockable badges.
- **Word packs** — general English/Italian plus programming and sci-fi vocab.
- **Retro audio** — CC0 chiptune music and SFX (optional; the game runs silently
  without the audio extra).
- **Degrades gracefully** — `--ascii` for terminals without Unicode/color.

## Requirements

- Python **3.11+**
- A terminal (Linux, macOS, or Windows). See *Platform support* below.

## Install

From source (not yet on PyPI):

```bash
git clone <repo-url> termtype
cd termtype
pip install -e ".[audio]"      # drop [audio] to skip the sound dependency
```

## Run

```bash
termtype
```

Force the no-Unicode renderer if your terminal mangles the visuals:

```bash
termtype --ascii
```

## Controls

**In a game**

| Key | Action |
|---|---|
| *(type letters)* | Lock onto and clear a falling word |
| `Backspace` | Fix a typo in the current word |
| `Backspace` ×2 | Abandon the current word |
| `Esc` | Pause |
| `R` | Retry · `S` Save & quit · `Q` Quit to menu |

**In menus** — `↑`/`↓` (or `j`/`k`) move, `Enter` selects, `Space` toggles options,
`Esc` goes back, `Q` quits. `Esc` is never destructive.

## Platform support

Developed and tested on **Linux / WSL**. The code is cross-platform and *should* run
on macOS and native Windows, but those haven't been exercised on real hardware yet —
**testers on macOS especially welcome.** If you try it, please open an issue with your
OS, terminal, and Python version (and a screenshot if something looks off).

## Development

```bash
pip install -e ".[dev,audio]"
pytest
```

The game logic is split into pure, render-free modules (state, scoring, word
matching, levels, persistence) that are unit-tested without a terminal, separate from
the asciimatics rendering layer.

## Credits & licensing

- **Code** — released under the MIT License (see [LICENSE](LICENSE)).
- **Story texts** — public-domain works (e.g. *Pride and Prejudice*, *Alice in
  Wonderland*, *Pinocchio*), included as plain prose.
- **Audio** — CC0 / public-domain assets; see
  [`src/termtype/data/audio/CREDITS.md`](src/termtype/data/audio/CREDITS.md) for the
  per-file manifest with checksums.

The MIT License covers the project's own source code; the bundled texts and audio are
in the public domain / CC0 as noted above.
