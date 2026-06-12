"""Tests for persistence — SQLite schema, profiles, sessions, stats, scores.

All tests use in-memory SQLite.
"""
import pytest
import sqlite3
from termtype.persistence.db import open_db, SCHEMA_VERSION, NewerDatabaseError
from termtype.persistence.profiles import (
    create_profile, list_profiles, get_profile, rename_profile,
    set_last_active, get_last_active, touch_last_played,
    MAX_NAME_LENGTH,
)
from termtype.persistence.config import load_config, save_config
from termtype.persistence.sessions import (
    save_session, load_session, clear_session, apply_resume_penalty,
)
from termtype.persistence.stats import (
    get_stats, game_over_commit, get_earned_badges,
    get_game_history, get_recent_play_dates,
)
from termtype.persistence.scores import (
    build_leaderboard_key, get_top_scores, get_top_rates,
)


@pytest.fixture
def db():
    """Create an in-memory database for testing."""
    conn = open_db(":memory:")
    yield conn
    conn.close()


# ── Schema ────────────────────────────────────────────────────────────────

class TestSchema:
    def test_tables_created(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {t[0] for t in tables}
        expected = {"profile", "config", "app_state", "session", "stats",
                    "badge", "game_history", "score"}
        assert expected.issubset(table_names)

    def test_schema_version(self, db):
        version = db.execute("PRAGMA user_version").fetchone()[0]
        assert version == SCHEMA_VERSION

    def test_pragmas_set(self, db):
        fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1


# ── Profiles ──────────────────────────────────────────────────────────────

class TestProfiles:
    def test_create_profile(self, db):
        pid = create_profile(db, "Alice")
        assert pid > 0

    def test_create_empty_name_fails(self, db):
        with pytest.raises(ValueError, match="empty"):
            create_profile(db, "")

    def test_create_long_name_fails(self, db):
        with pytest.raises(ValueError, match="too long"):
            create_profile(db, "x" * (MAX_NAME_LENGTH + 1))

    def test_create_duplicate_name_fails(self, db):
        create_profile(db, "Alice")
        with pytest.raises(ValueError, match="already in use"):
            create_profile(db, "alice")  # COLLATE NOCASE

    def test_list_profiles(self, db):
        create_profile(db, "Alice")
        create_profile(db, "Bob")
        profiles = list_profiles(db)
        assert len(profiles) == 2
        assert profiles[0]["display_name"] == "Alice"

    def test_get_profile(self, db):
        pid = create_profile(db, "Alice")
        profile = get_profile(db, pid)
        assert profile is not None
        assert profile["display_name"] == "Alice"

    def test_rename_profile(self, db):
        pid = create_profile(db, "Alice")
        rename_profile(db, pid, "Alicia")
        profile = get_profile(db, pid)
        assert profile["display_name"] == "Alicia"

    def test_rename_duplicate_fails(self, db):
        create_profile(db, "Alice")
        pid2 = create_profile(db, "Bob")
        with pytest.raises(ValueError, match="already in use"):
            rename_profile(db, pid2, "alice")

    def test_last_active(self, db):
        pid = create_profile(db, "Alice")
        set_last_active(db, pid)
        assert get_last_active(db) == pid

    def test_last_active_none_initially(self, db):
        assert get_last_active(db) is None


# ── Config ────────────────────────────────────────────────────────────────

class TestConfig:
    def test_load_defaults(self, db):
        pid = create_profile(db, "Alice")
        config = load_config(db, pid)
        assert config["language"] == "en"
        assert config["sfx_on"] == 1

    def test_save_and_load(self, db):
        pid = create_profile(db, "Alice")
        save_config(db, pid, {"language": "it", "sfx_volume": 0.8})
        config = load_config(db, pid)
        assert config["language"] == "it"
        assert config["sfx_volume"] == pytest.approx(0.8)

    def test_volume_clamp(self, db):
        pid = create_profile(db, "Alice")
        save_config(db, pid, {"sfx_volume": 1.5})
        config = load_config(db, pid)
        assert config["sfx_volume"] == pytest.approx(1.0)

    def test_volume_negative_clamp(self, db):
        pid = create_profile(db, "Alice")
        save_config(db, pid, {"music_volume": -0.5})
        config = load_config(db, pid)
        assert config["music_volume"] == pytest.approx(0.0)

    def test_malformed_volume_fallback(self, db):
        pid = create_profile(db, "Alice")
        save_config(db, pid, {"sfx_volume": "not_a_number"})
        config = load_config(db, pid)
        # Falls back to default
        assert 0.0 <= config["sfx_volume"] <= 1.0


# ── Sessions ──────────────────────────────────────────────────────────────

class TestSessions:
    def test_save_and_load(self, db):
        pid = create_profile(db, "Alice")
        save_session(db, pid, level=5, score=100, lives=2)
        session = load_session(db, pid)
        assert session is not None
        assert session["level"] == 5
        assert session["score"] == 100
        assert session["lives"] == 2

    def test_clear_session(self, db):
        pid = create_profile(db, "Alice")
        save_session(db, pid, level=5)
        clear_session(db, pid)
        assert load_session(db, pid) is None

    def test_load_nonexistent(self, db):
        pid = create_profile(db, "Alice")
        assert load_session(db, pid) is None

    def test_resume_penalty_applied_once(self, db):
        pid = create_profile(db, "Alice")
        save_session(db, pid, score=100)

        # First resume: penalty applied
        new_score, applied = apply_resume_penalty(db, pid, 100)
        assert applied is True
        assert new_score == 90  # -10%

        # Second resume: no re-penalty
        new_score2, applied2 = apply_resume_penalty(db, pid, 90)
        assert applied2 is False
        assert new_score2 == 90

    def test_option_flags_roundtrip(self, db):
        pid = create_profile(db, "Alice")
        flags = {"numbers": True, "accents": False}
        save_session(db, pid, option_flags=flags)
        session = load_session(db, pid)
        assert session["option_flags"]["numbers"] is True

    def test_story_session_roundtrip(self, db):
        pid = create_profile(db, "Alice")
        save_session(
            db, pid, mode="story", story_name="pride_and_prejudice",
            story_position=42, level=3,
        )
        session = load_session(db, pid)
        assert session["mode"] == "story"
        assert session["story_name"] == "pride_and_prejudice"
        assert session["story_position"] == 42


# ── Stats & Game-over commit ─────────────────────────────────────────────

class TestStats:
    def test_initial_stats_zero(self, db):
        pid = create_profile(db, "Alice")
        stats = get_stats(db, pid)
        assert stats["games_played"] == 0
        assert stats["best_score"] == 0

    def test_game_over_commit(self, db):
        pid = create_profile(db, "Alice")
        game_over_commit(
            db, pid,
            score=1000, wpm=40.0, accuracy=0.95, level=5,
            words_typed=50, words_missed=2, correct_chars=200,
            total_keystrokes=210, correct_keystrokes=200,
            seconds_played=300.0, max_combo=15,
            peak_score_rate=8.5, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
        )

        stats = get_stats(db, pid)
        assert stats["games_played"] == 1
        assert stats["best_score"] == 1000
        assert stats["highest_level"] == 5
        assert stats["words_typed"] == 50
        assert stats["best_wpm"] == pytest.approx(40.0)

    def test_game_over_clears_session(self, db):
        pid = create_profile(db, "Alice")
        save_session(db, pid, level=3)
        game_over_commit(
            db, pid,
            score=500, wpm=30.0, accuracy=0.9, level=3,
            words_typed=20, words_missed=1, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
        )
        assert load_session(db, pid) is None

    def test_multiple_games_accumulate(self, db):
        pid = create_profile(db, "Alice")
        for i in range(3):
            game_over_commit(
                db, pid,
                score=100 * (i + 1), wpm=30.0 + i, accuracy=0.9,
                level=3 + i, words_typed=20, words_missed=0,
                correct_chars=80, total_keystrokes=85,
                correct_keystrokes=80, seconds_played=150.0,
                max_combo=5, peak_score_rate=3.0,
                leaderboard_key="vocab_en_none",
                payload_ts=f"2025-01-{15 + i}T12:00:00",
            )

        stats = get_stats(db, pid)
        assert stats["games_played"] == 3
        assert stats["best_score"] == 300
        assert stats["cumulative_score"] == 600

    def test_monotonic_first_last_played(self, db):
        pid = create_profile(db, "Alice")
        game_over_commit(
            db, pid,
            score=100, wpm=30.0, accuracy=0.9, level=3,
            words_typed=20, words_missed=0, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
        )
        game_over_commit(
            db, pid,
            score=200, wpm=35.0, accuracy=0.95, level=5,
            words_typed=30, words_missed=0, correct_chars=120,
            total_keystrokes=125, correct_keystrokes=120,
            seconds_played=200.0, max_combo=10,
            peak_score_rate=5.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-20T12:00:00",
        )

        stats = get_stats(db, pid)
        assert stats["first_played"] == "2025-01-15T12:00:00"
        assert stats["last_played"] == "2025-01-20T12:00:00"

    def test_game_idempotent(self, db):
        """INSERT OR IGNORE makes re-insert a no-op."""
        pid = create_profile(db, "Alice")
        gid = game_over_commit(
            db, pid,
            score=100, wpm=30.0, accuracy=0.9, level=3,
            words_typed=20, words_missed=0, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
            game_id="test-id-1",
        )

        # Re-insert same game_id — should be a no-op
        game_over_commit(
            db, pid,
            score=999, wpm=99.0, accuracy=0.99, level=99,
            words_typed=99, words_missed=99, correct_chars=99,
            total_keystrokes=99, correct_keystrokes=99,
            seconds_played=99.0, max_combo=99,
            peak_score_rate=99.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
            game_id="test-id-1",
        )

        # Stats should reflect the first commit only
        stats = get_stats(db, pid)
        assert stats["games_played"] == 1
        assert stats["best_score"] == 100

    def test_badges_stored(self, db):
        pid = create_profile(db, "Alice")
        game_over_commit(
            db, pid,
            score=100, wpm=30.0, accuracy=0.9, level=10,
            words_typed=20, words_missed=0, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
            new_badges={"level_10"},
        )
        badges = get_earned_badges(db, pid)
        assert "level_10" in badges

    def test_game_history(self, db):
        pid = create_profile(db, "Alice")
        for i in range(3):
            game_over_commit(
                db, pid,
                score=100, wpm=30.0, accuracy=0.9, level=3,
                words_typed=20, words_missed=0, correct_chars=80,
                total_keystrokes=85, correct_keystrokes=80,
                seconds_played=150.0, max_combo=5,
                peak_score_rate=3.0, leaderboard_key="vocab_en_none",
                payload_ts=f"2025-01-{15 + i}T12:00:00",
            )
        history = get_game_history(db, pid)
        assert len(history) == 3

    def test_recent_play_dates(self, db):
        pid = create_profile(db, "Alice")
        for i in range(5):
            game_over_commit(
                db, pid,
                score=100, wpm=30.0, accuracy=0.9, level=3,
                words_typed=20, words_missed=0, correct_chars=80,
                total_keystrokes=85, correct_keystrokes=80,
                seconds_played=150.0, max_combo=5,
                peak_score_rate=3.0, leaderboard_key="vocab_en_none",
                payload_ts=f"2025-01-{15 + i}T12:00:00",
            )
        dates = get_recent_play_dates(db, pid)
        assert len(dates) == 5


# ── Leaderboard ───────────────────────────────────────────────────────────

class TestLeaderboard:
    def test_leaderboard_key_build(self):
        key = build_leaderboard_key("vocab", "en", {"numbers": False, "accents": False})
        assert key == "vocab_en_none"

    def test_leaderboard_key_with_flags(self):
        key = build_leaderboard_key("vocab", "en", {"numbers": True, "accents": False})
        assert key == "vocab_en_numbers"

    def test_leaderboard_key_sorted(self):
        key = build_leaderboard_key("vocab", "en", {"accents": True, "numbers": True})
        assert key == "vocab_en_accents_numbers"

    def test_top_scores(self, db):
        pid = create_profile(db, "Alice")
        for i in range(3):
            game_over_commit(
                db, pid,
                score=100 * (i + 1), wpm=30.0, accuracy=0.9, level=3,
                words_typed=20, words_missed=0, correct_chars=80,
                total_keystrokes=85, correct_keystrokes=80,
                seconds_played=150.0, max_combo=5,
                peak_score_rate=3.0, leaderboard_key="vocab_en_none",
                payload_ts=f"2025-01-{15 + i}T12:00:00",
            )

        top = get_top_scores(db, "vocab_en_none")
        assert len(top) == 3
        assert top[0]["score"] == 300  # highest first
        assert top[1]["score"] == 200
        assert top[2]["score"] == 100

    def test_top_rates(self, db):
        pid = create_profile(db, "Alice")
        for i in range(3):
            game_over_commit(
                db, pid,
                score=100, wpm=30.0, accuracy=0.9, level=3,
                words_typed=20, words_missed=0, correct_chars=80,
                total_keystrokes=85, correct_keystrokes=80,
                seconds_played=150.0, max_combo=5,
                peak_score_rate=3.0 + i, leaderboard_key="vocab_en_none",
                payload_ts=f"2025-01-{15 + i}T12:00:00",
            )

        top = get_top_rates(db, "vocab_en_none")
        assert len(top) == 3
        assert top[0]["peak_score_rate"] == pytest.approx(5.0)

    def test_deterministic_tiebreak(self, db):
        """Same score: first-achieved wins (earlier game_over_ts)."""
        pid = create_profile(db, "Alice")
        game_over_commit(
            db, pid, game_id="gid-1",
            score=100, wpm=30.0, accuracy=0.9, level=3,
            words_typed=20, words_missed=0, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-15T12:00:00",
        )
        game_over_commit(
            db, pid, game_id="gid-2",
            score=100, wpm=30.0, accuracy=0.9, level=3,
            words_typed=20, words_missed=0, correct_chars=80,
            total_keystrokes=85, correct_keystrokes=80,
            seconds_played=150.0, max_combo=5,
            peak_score_rate=3.0, leaderboard_key="vocab_en_none",
            payload_ts="2025-01-16T12:00:00",
        )

        top = get_top_scores(db, "vocab_en_none")
        assert top[0]["game_id"] == "gid-1"  # first-achieved wins


# ── Versioning & Recovery (PLAN §7.6) ─────────────────────────────────────

class TestVersioningRecovery:
    def test_corrupt_db_quarantined_and_recovered(self, tmp_path):
        """A corrupt DB file is quarantined and open_db returns a usable conn."""
        db_path = tmp_path / "termtype.db"
        # Write garbage bytes — not a valid SQLite file.
        db_path.write_bytes(b"this is not a sqlite database, just garbage\x00\xff" * 50)

        conn = open_db(db_path)
        try:
            # A quarantine file now exists alongside the (recreated) DB.
            quarantined = list(tmp_path.glob("termtype.db.corrupt.*"))
            assert len(quarantined) == 1

            # The returned connection is fully usable: schema present, can write.
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert version == SCHEMA_VERSION
            pid = create_profile(conn, "Alice")
            assert pid > 0
        finally:
            conn.close()

    def test_newer_db_version_refused(self, tmp_path):
        """A DB with user_version above SCHEMA_VERSION raises NewerDatabaseError."""
        db_path = tmp_path / "termtype.db"
        conn = open_db(db_path)
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
        conn.close()

        with pytest.raises(NewerDatabaseError, match="newer version"):
            open_db(db_path)

    def test_reopen_idempotent(self, tmp_path):
        """Reopening a normally-created DB is a no-op: version stays put, no error."""
        db_path = tmp_path / "termtype.db"
        conn1 = open_db(db_path)
        assert conn1.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        conn1.close()

        conn2 = open_db(db_path)
        try:
            assert conn2.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        finally:
            conn2.close()


# ── Atomic commit ─────────────────────────────────────────────────────────

class TestAtomicCommit:
    def test_rollback_on_error(self, db):
        """A raise mid-commit should roll back everything."""
        pid = create_profile(db, "Alice")
        save_session(db, pid, level=3, score=100)

        # Use a wrapper to intercept execute calls
        class FailingConn:
            """Wrapper that raises on a specific SQL pattern."""
            def __init__(self, conn):
                self._conn = conn
                self._should_fail = True

            def __getattr__(self, name):
                return getattr(self._conn, name)

            def execute(self, sql, *args):
                if self._should_fail and "INSERT OR IGNORE INTO score" in sql:
                    raise sqlite3.IntegrityError("forced failure")
                return self._conn.execute(sql, *args)

            def commit(self):
                return self._conn.commit()

            def rollback(self):
                return self._conn.rollback()

        failing_db = FailingConn(db)

        with pytest.raises(sqlite3.IntegrityError):
            game_over_commit(
                failing_db, pid,
                score=500, wpm=30.0, accuracy=0.9, level=3,
                words_typed=20, words_missed=0, correct_chars=80,
                total_keystrokes=85, correct_keystrokes=80,
                seconds_played=150.0, max_combo=5,
                peak_score_rate=3.0, leaderboard_key="vocab_en_none",
                payload_ts="2025-01-15T12:00:00",
                game_id="test-rollback",
            )

        # Stats should be unchanged (rollback)
        stats = get_stats(db, pid)
        assert stats["games_played"] == 0

        # Session should still exist
        session = load_session(db, pid)
        assert session is not None
