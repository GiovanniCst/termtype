"""Tests for progression.py — badges and unlocks."""
import pytest
from termtype.game.progression import (
    BADGES, UNLOCKS, BADGE_IDS, UNLOCK_IDS,
    GamePayload, evaluate_badges, available_unlocks, _check_streak_7,
)


class TestBadgeDefinitions:
    def test_all_badges_have_ids(self):
        for b in BADGES:
            assert b.id
            assert b.id in BADGE_IDS

    def test_badge_ids_unique(self):
        ids = [b.id for b in BADGES]
        assert len(ids) == len(set(ids))


class TestUnlockDefinitions:
    def test_all_unlocks_have_ids(self):
        for u in UNLOCKS:
            assert u.id
            assert u.id in UNLOCK_IDS

    def test_unlock_requirements_reference_valid(self):
        """Every unlock requirement references an existing badge id or stat field."""
        stat_fields = {"words_typed", "games_played", "cumulative_score"}
        for u in UNLOCKS:
            assert u.requirement in BADGE_IDS or u.requirement in stat_fields, \
                f"Unlock {u.id} has unknown requirement: {u.requirement}"


class TestEvaluateBadges:
    def test_level_10(self):
        payload = GamePayload(highest_level=10)
        new = evaluate_badges(payload, {}, set(), [])
        assert "level_10" in new

    def test_level_9_no_badge(self):
        payload = GamePayload(highest_level=9)
        new = evaluate_badges(payload, {}, set(), [])
        assert "level_10" not in new

    def test_plateau(self):
        payload = GamePayload(reached_plateau=True)
        new = evaluate_badges(payload, {}, set(), [])
        assert "plateau" in new

    def test_combo_25(self):
        payload = GamePayload(max_combo=25)
        new = evaluate_badges(payload, {}, set(), [])
        assert "combo_25" in new

    def test_combo_24_no_badge(self):
        payload = GamePayload(max_combo=24)
        new = evaluate_badges(payload, {}, set(), [])
        assert "combo_25" not in new

    def test_combo_50(self):
        payload = GamePayload(max_combo=50)
        new = evaluate_badges(payload, {}, set(), [])
        assert "combo_50" in new

    def test_word_100wpm(self):
        payload = GamePayload(max_word_wpm=100.0)
        new = evaluate_badges(payload, {}, set(), [])
        assert "word_100wpm" in new

    def test_word_99wpm_no_badge(self):
        payload = GamePayload(max_word_wpm=99.9)
        new = evaluate_badges(payload, {}, set(), [])
        assert "word_100wpm" not in new

    def test_wave_clean(self):
        payload = GamePayload(waves_clean=1)
        new = evaluate_badges(payload, {}, set(), [])
        assert "wave_clean" in new

    def test_wave_perfect(self):
        payload = GamePayload(waves_perfect=1)
        new = evaluate_badges(payload, {}, set(), [])
        assert "wave_perfect" in new

    def test_story_done(self):
        payload = GamePayload(story_completed=True)
        new = evaluate_badges(payload, {}, set(), [])
        assert "story_done" in new

    def test_already_earned_not_re_awarded(self):
        payload = GamePayload(highest_level=10)
        earned = {"level_10"}
        new = evaluate_badges(payload, {}, earned, [])
        assert "level_10" not in new


class TestStreak7:
    def test_7_consecutive_days(self):
        dates = [f"2025-01-{i:02d}" for i in range(1, 8)]
        assert _check_streak_7(dates) is True

    def test_6_days_not_enough(self):
        dates = [f"2025-01-{i:02d}" for i in range(1, 7)]
        assert _check_streak_7(dates) is False

    def test_gapped_dates(self):
        dates = ["2025-01-01", "2025-01-02", "2025-01-04"]  # gap at 3rd
        assert _check_streak_7(dates) is False

    def test_full_iso_dates(self):
        dates = [f"2025-01-{i:02d}T12:00:00" for i in range(1, 8)]
        assert _check_streak_7(dates) is True

    def test_duplicate_dates(self):
        dates = [f"2025-01-{i:02d}" for i in range(1, 8)]
        dates.append("2025-01-01")  # duplicate
        assert _check_streak_7(dates) is True


class TestAvailableUnlocks:
    def test_badge_gated_unlock(self):
        """title_retro requires streak_7 badge."""
        stats = {}
        badges = {"streak_7"}
        unlocks = available_unlocks(stats, badges)
        assert unlocks["title_retro"] is True

    def test_badge_gated_unlock_not_earned(self):
        stats = {}
        badges = set()
        unlocks = available_unlocks(stats, badges)
        assert unlocks["title_retro"] is False

    def test_stat_gated_unlock(self):
        """theme_nebula requires 1000 words_typed."""
        stats = {"words_typed": 1000}
        badges = set()
        unlocks = available_unlocks(stats, badges)
        assert unlocks["theme_nebula"] is True

    def test_stat_gated_unlock_below(self):
        stats = {"words_typed": 999}
        badges = set()
        unlocks = available_unlocks(stats, badges)
        assert unlocks["theme_nebula"] is False

    def test_all_unlocks_derived(self):
        """Every unlock has a derivation result."""
        stats = {"words_typed": 99999}
        badges = BADGE_IDS.copy()
        unlocks = available_unlocks(stats, badges)
        assert len(unlocks) == len(UNLOCKS)
        assert all(uid in unlocks for uid in UNLOCK_IDS)
