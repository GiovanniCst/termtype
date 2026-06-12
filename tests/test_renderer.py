"""Renderer tests via a recording fake screen (no real terminal)."""
from termtype.game.renderer import Renderer, TIER_256, splash_frame
from termtype.game.state import GameState


class FakeScreen:
    A_REVERSE = 0

    def __init__(self, w=110, h=30, colours=256):
        self._w, self._h = w, h
        self.colours = colours
        self.calls = []  # (y, x, text)

    @property
    def dimensions(self):
        return (self._h, self._w)

    def clear(self):
        pass

    def clear_buffer(self, fg, attr, bg, x=0, y=0, w=None, h=None):
        pass

    def print_at(self, text, x, y, colour=7, attr=0, bg=0):
        self.calls.append((y, x, text, colour))

    def refresh(self):
        pass


def _texts(screen):
    return "\n".join(c[2] for c in screen.calls)


def _colours_of(screen, text):
    return [c[3] for c in screen.calls if c[2] == text]


def _renderer(screen):
    r = Renderer(screen, reduced_motion=True)
    r._color_tier = TIER_256
    return r


def test_hn_panel_renders_header_footer_and_revealed_title():
    screen = FakeScreen()
    r = _renderer(screen)
    state = GameState(
        mode="story", story_skin="hn", play_cols=66,
        story_words=["alpha", "beta", "gamma", "delta"],
        sentence_ends={1, 3},                       # title0 ends @1, title1 ends @3
        story_display_lines=["Alpha Beta Headline", "Gamma Delta Headline"],
        story_words_done=2,                          # title0 fully typed, title1 not
    )
    r.render_frame(state, hud_line="HUD")
    out = _texts(screen)
    assert "Hacker News" in out          # orange header wordmark
    assert "guidelines" in out           # footer nav
    assert "Alpha Beta Headline" in out  # revealed (typed) title
    assert "Gamma Delta Headline" not in out  # not yet typed -> hidden


def test_hn_panel_hides_all_titles_before_any_typed():
    screen = FakeScreen()
    r = _renderer(screen)
    state = GameState(
        mode="story", story_skin="hn", play_cols=66,
        story_words=["alpha", "beta"], sentence_ends={1},
        story_display_lines=["Alpha Beta Headline"], story_words_done=0,
    )
    r.render_frame(state, hud_line="HUD")
    out = _texts(screen)
    assert "Hacker News" in out
    assert "Alpha Beta Headline" not in out  # nothing typed yet


def _motion_renderer(screen):
    r = Renderer(screen, reduced_motion=False)  # popups need motion on
    r._color_tier = TIER_256
    r._stars = []                                # drop the random starfield
    return r


def test_score_popup_renders_and_expires():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0)
    st.time_played_seconds = 5.0
    st.effects.add_popup("+50", 10, 8, 5.0, "fast")
    r.render_frame(st, hud_line="HUD")
    assert "+50" in _texts(screen)

    # An old popup (beyond TTL) is cleared and not drawn
    screen2 = FakeScreen()
    r2 = _motion_renderer(screen2)
    st2 = GameState(mode="vocab", water_row=20.0)
    st2.time_played_seconds = 10.0
    st2.effects.add_popup("+99", 10, 8, 5.0, "fast")  # 5s old
    r2.render_frame(st2, hud_line="HUD")
    assert "+99" not in _texts(screen2)


def test_first_game_highlights_first_letter():
    from termtype.game.entities import FallingWord
    # First game: the word's first letter is drawn in the highlight colour (3)
    screen = FakeScreen()
    r = _renderer(screen)
    st = GameState(mode="vocab", water_row=20.0, is_first_game=True)
    st.words.append(FallingWord(text="hello", x=10, row=5, speed=1))
    r.render_frame(st, hud_line="HUD")
    assert 3 in _colours_of(screen, "h")  # leading 'h' highlighted

    # Returning player: no highlight on the first letter
    screen2 = FakeScreen()
    r2 = _renderer(screen2)
    st2 = GameState(mode="vocab", water_row=20.0, is_first_game=False)
    st2.words.append(FallingWord(text="hello", x=10, row=5, speed=1))
    r2.render_frame(st2, hud_line="HUD")
    assert 3 not in _colours_of(screen2, "h")


def test_levelup_banner_renders():
    screen = FakeScreen()
    r = _renderer(screen)
    st = GameState(mode="vocab", water_row=20.0)
    st.time_played_seconds = 5.0
    st.effects.level_up = (5.0, 4)
    r.render_frame(st, hud_line="HUD")
    assert "LEVEL 4" in _texts(screen)


# ── splash / sparkle juice ────────────────────────────────────────────────


def test_splash_frame_expands_then_expires():
    assert splash_frame(0.0)                       # something at age 0
    early = splash_frame(0.05)
    late = splash_frame(0.4)
    assert len(late) > len(early)                  # burst widens with age
    assert splash_frame(0.5) == []                 # expired at TTL
    assert splash_frame(-1.0) == []                # negative age = nothing


def test_splash_frame_symmetric_around_origin():
    offs = sorted(off for off, _ in splash_frame(0.3))
    assert offs == sorted(-o for o in offs)        # mirror-symmetric


def test_drown_splash_renders_glyphs():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0)
    st.time_played_seconds = 5.0
    st.effects.add_splash(30.0, 20.0, 5.0)         # fresh splash this frame
    r.render_frame(st, hud_line="HUD")
    # Splash droplets ('*') drawn just above the water line in cyan (6)
    assert any(c[2] == "*" and c[3] == 6 for c in screen.calls)


def test_reduced_motion_suppresses_splash():
    screen = FakeScreen()
    r = _renderer(screen)                          # reduced_motion=True
    st = GameState(mode="vocab", water_row=20.0)
    st.time_played_seconds = 5.0
    st.effects.add_splash(30.0, 20.0, 5.0)
    r.render_frame(st, hud_line="HUD")
    assert all(c[2] != "*" for c in screen.calls)


def test_sparkle_renders_for_secret_clear():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0)
    st.time_played_seconds = 5.0
    st.effects.add_sparkle(30.0, 8.0, 5.0)
    r.render_frame(st, hud_line="HUD")
    # A golden twinkle glyph drawn in colour 6 somewhere on the field
    assert any(c[3] == 6 and c[2] in "✦✧*+x" for c in screen.calls)


def test_fin_frenzy_draws_a_school():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0, play_cols=80)
    st.time_played_seconds = 5.0
    st.fin_frenzy_until = 7.0                       # frenzy active now
    r.render_frame(st, hud_line="HUD")
    fins = [c for c in screen.calls if c[2] == "▲"]
    assert len(fins) >= 5                           # a school, not a lone fin


def test_shark_cameo_renders_when_active():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0, play_cols=80)
    st.time_played_seconds = 5.0
    r._cameo_start = 5.0          # leap mid-flight
    r._cameo_dir = 1
    # Mid-arc sample
    st.time_played_seconds = 5.0 + r._CAMEO_DUR / 2
    r.render_frame(st, hud_line="HUD")
    glyphs = "".join(c[2] for c in screen.calls)
    assert "=" in glyphs and ">" in glyphs        # ASCII shark body drawn


def test_shark_cameo_clears_after_duration():
    screen = FakeScreen()
    r = _motion_renderer(screen)
    st = GameState(mode="vocab", water_row=20.0, play_cols=80)
    r._cameo_start = 1.0
    st.time_played_seconds = 1.0 + r._CAMEO_DUR + 0.1   # past the end
    r.render_frame(st, hud_line="HUD")
    assert r._cameo_start is None                  # leap finished, state cleared


def test_shark_cameo_suppressed_under_reduced_motion():
    screen = FakeScreen()
    r = _renderer(screen)                          # reduced_motion=True
    st = GameState(mode="vocab", water_row=20.0, play_cols=80)
    r._cameo_start = 5.0
    st.time_played_seconds = 5.3
    r.render_frame(st, hud_line="HUD")
    assert "=^" not in "".join(c[2] for c in screen.calls)


def test_story_ribbon_shows_progress():
    screen = FakeScreen()
    r = _renderer(screen)
    state = GameState(
        mode="story", story_words=["alpha", "beta", "gamma"],
        sentence_ends={2}, story_words_done=2,
    )
    r.render_frame(state, hud_line="HUD")
    out = _texts(screen)
    assert "[2/3]" in out                # progress counter
    assert "alpha beta" in out           # assembled-so-far ribbon
