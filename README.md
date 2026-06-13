<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/title-dark.svg">
    <img src="assets/title.svg" alt="termType" width="560">
  </picture>
</div>

A terminal typing game where words fall like Space Invaders — type them before they
hit the water line, or you drown.

Pure-terminal, no GUI. Built on [asciimatics](https://github.com/peterbrittain/asciimatics).

<p align="center">
  <img src="assets/demo.gif" alt="termType demo — Vocab, Hacker News, and Story modes" width="900">
  <br>
  <sub><em>termType gameplay, accelerated due to time constraints.</em></sub>
</p>

## Features

- **Vocab mode** — endless arcade: type words before they hit the water; waves
  escalate, combos build, lives run out.
- **Story mode** — type public-domain books (English & Italian) in order; resume where
  you left off; Zen or Challenge.
- **Hacker News mode** — type over a live HN front page (or the all-time top posts,
  offline).
- **Progression** — profiles, stats with sparkline charts, leaderboards, badges.
- **Word packs** — English/Italian, plus programming and sci-fi vocab.
- **Retro audio** — CC0 chiptune music and SFX.
- **Cross-platform** — Linux, macOS, Windows; `--ascii` for limited terminals.

## Requirements

- Python **3.11+**
- A terminal (Linux, macOS, or Windows). See *Platform support* below.

## Install

From source (not yet on PyPI). A virtual environment keeps it isolated and puts the
`termtype` command on your PATH:

```bash
git clone https://github.com/GiovanniCst/termtype.git
cd termtype
python3.11 -m venv .venv
source .venv/bin/activate           # on Windows, see "Windows (PowerShell)" below
pip install -e .                    # audio (pygame) is included by default
```

## Run

With the virtual environment active:

```bash
termtype
```

If the venv isn't active, run the entry point directly: `./.venv/bin/termtype`.
Force the no-Unicode renderer if your terminal mangles the visuals:

```bash
termtype --ascii
```

### Windows (PowerShell)

Use a **Windows** Python and a **Windows** venv — a venv created inside WSL won't
run from PowerShell (its interpreter is a Linux binary, and the layout is
`.venv\bin\` instead of `.venv\Scripts\`). Calling the venv executables by full
path avoids the unsigned-script (execution-policy) error you'd otherwise hit on
`Activate.ps1`:

```powershell
git clone https://github.com/GiovanniCst/termtype.git
cd termtype
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .   # audio (pygame) included
.\.venv\Scripts\termtype.exe
```

To activate the venv instead (shorter `termtype` / `pip` commands), allow scripts
for the current session first — this reverts when you close the window:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

> **Audio tip:** under WSL the sound is routed through a remoting bridge that can
> crackle under load; running natively on Windows (above) uses the Windows audio
> stack directly and avoids it.

**Display notes (Windows):**

- Use **Windows Terminal** with a box-drawing font like Cascadia Mono. UTF-8 is enabled
  automatically; if glyphs still show as boxes, run `termtype --ascii`.
- The Windows console is capped at **8 colours**, so some 256-colour touches differ —
  notably the Hacker News page (white/yellow instead of cream/orange). For the full
  palette, run under WSL or on Linux/macOS.

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

Run on real hardware on **Linux / WSL**, **native Windows** (see *Windows (PowerShell)*
above for setup and display notes), and **macOS**. If something looks off on your setup,
please open an issue with your OS, terminal, and Python version (and a screenshot).

## Development

```bash
pip install -e ".[dev]"
pytest
```

The game logic is split into pure, render-free modules (state, scoring, word
matching, levels, persistence) that are unit-tested without a terminal, separate from
the asciimatics rendering layer.

## Privacy

termType keeps to itself, and you can verify every word of this in the source:

- **Your data never leaves your machine.** Profiles, scores, stats, and settings are
  stored in a local SQLite database (`~/.termtype/termtype.db`). Nothing is uploaded,
  synced, or shared.
- **No telemetry of any kind** — no analytics, crash reporting, ads, accounts, logins,
  or update checks. The game never "phones home."
- **One network feature, only on demand.** *Hacker News* mode fetches the current
  top-story **titles** from the public Hacker News API (`hacker-news.firebaseio.com`)
  over HTTPS, and only while you are in that mode. The requests are plain GETs with a
  generic `User-Agent: termType (typing game)` — no personal data is sent — and the
  fetched titles are held in memory, never written to disk. Offline, it falls back to a
  built-in list and makes no connection at all.
- **Everything else works fully offline.**

The only networking code in the whole project is
[`src/termtype/game/hn.py`](src/termtype/game/hn.py) — read it for yourself.

## Credits & licensing

termType was **ideated and orchestrated by Giovanni J. Costantini** and **coded by
autonomous AI agents** — Opus, Kimi, and Fable — working under his direction. The same
disclosure appears in the game's own credits.

In-game credits (author, website, and these attributions) are available from the
**Credits** entry on the main menu.

- **Code** — © 2026 Giovanni J. Costantini, released under the MIT License (see
  [LICENSE](LICENSE)).
- **Story texts** — public-domain works (e.g. *Pride and Prejudice*, *Alice in
  Wonderland*, *Pinocchio*), included as plain prose.
- **Audio** — CC0 / public-domain assets; see
  [`src/termtype/data/audio/CREDITS.md`](src/termtype/data/audio/CREDITS.md) for the
  per-file manifest with checksums.

The MIT License covers the project's own source code; the bundled texts and audio are
in the public domain / CC0 as noted above.

## A note from the author

termType is a solo project by **Giovanni J. Costantini** — more about my work at
[costantini.pw](https://costantini.pw).

I'm open to **CTO and senior engineering-leadership roles**, in software-product
companies or corporate engineering organisations. If that sounds like a fit, I'd be
glad to talk.
