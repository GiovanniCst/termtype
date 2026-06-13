#!/usr/bin/env bash
#
# Record a termType demo and render it to an animated GIF for the README.
#
#   ./scripts/record-demo.sh            # record a fresh take, then render
#   ./scripts/record-demo.sh --render   # re-render the GIF from the last .cast
#
# SHOT LIST (~30s, aim for one clean take). Keep each gameplay bit to ~6-8s so
# the GIF stays small. Sequence: title -> menu -> Vocab -> HN -> Story.
#
#   TITLE   1. Let the splash play ~3s    — logo dropping into the water, falling
#                                           words, the patrolling shark fin.
#           2. Press SPACE                — logo plunges in, lands on the menu.
#   MENU    3. Arrow DOWN a couple times  — show the per-item description boxes,
#              then back to the top.         then UP back to Vocab Mode.
#   VOCAB   4. Press  v ,  play ~7s        — clear words briskly; let ONE drift
#                                            into the red zone then clutch-clear
#                                            it (the sparkle). Esc then  q  -> menu.
#   HN      5. Press  s  then  h           — Hacker News; ~2s "Fetching", then type
#              play ~7s                      headlines as the page fills in.
#                                            Esc then  q  -> menu.
#   STORY   6. Press  s , DOWN , ENTER      — pick the first story (Alice); then
#              then  z  (Zen), play ~7s      z  for Zen. Watch the prose ribbon
#                                            assemble. Esc then  q  -> menu.
#   END     7. Press  q                     — quit; the game exits, recording stops.
#
# Tips: don't pause long (idle is trimmed to 2s). A couple of typos are fine —
# they show the typo feedback. For Story, Zen (z) avoids an accidental game-over
# mid-capture. Re-run for another take until it feels right.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

CAST="assets/demo.cast"
GIF="assets/demo.gif"
COLS=100
ROWS=30

mkdir -p assets

for tool in asciinema agg; do
    command -v "$tool" >/dev/null 2>&1 || { echo "Missing '$tool' on PATH." >&2; exit 1; }
done

TERMTYPE="$ROOT/.venv/bin/termtype"
[ -x "$TERMTYPE" ] || TERMTYPE="termtype"

if [ "${1:-}" != "--render" ]; then
    echo "Recording at ${COLS}x${ROWS}. Follow the shot list; quit with Q to stop."
    asciinema rec --overwrite --cols "$COLS" --rows "$ROWS" \
        --idle-time-limit 2 -c "$TERMTYPE" "$CAST"
fi

echo "Rendering ${GIF}..."
agg --font-size 16 --fps-cap 24 --idle-time-limit 2 --last-frame-duration 2 \
    "$CAST" "$GIF"

ls -lh "$GIF"
echo "Done. Preview it, and re-run with --render if you only want to retune the GIF."
