"""Tests for levels.py — difficulty model and tunable constants."""
import pytest
from termtype.game import levels


class TestLevelMultiplier:
    def test_level_1(self):
        assert levels.level_multiplier(1) == 1.0

    def test_level_5(self):
        # 1.0 + 4 * 0.1 = 1.4
        assert levels.level_multiplier(5) == pytest.approx(1.4)

    def test_level_15_saturation(self):
        # 1.0 + 14 * 0.1 = 2.4
        assert levels.level_multiplier(15) == pytest.approx(levels.LEVEL_MULT_CAP)

    def test_level_20_still_saturated(self):
        assert levels.level_multiplier(20) == pytest.approx(levels.LEVEL_MULT_CAP)

    def test_monotonic_until_cap(self):
        prev = 0.0
        for lvl in range(1, 16):
            val = levels.level_multiplier(lvl)
            assert val > prev
            prev = val


class TestBands:
    def test_level_1_band(self):
        lo, hi, speed, max_sim, complexity = levels.band_for_level(1)
        assert lo == 1 and hi == 3
        assert speed == (0.8, 1.5)
        assert max_sim == 3
        assert complexity == "short"

    def test_level_4_band(self):
        _, _, _, max_sim, complexity = levels.band_for_level(4)
        assert max_sim == 4
        assert complexity == "medium"

    def test_level_7_band(self):
        _, _, speed, _, complexity = levels.band_for_level(7)
        assert speed == (1.5, 2.2)
        assert complexity == "complex"

    def test_level_10_band(self):
        _, _, speed, max_sim, _ = levels.band_for_level(10)
        assert speed == (2.2, 3.0)
        assert max_sim == 5

    def test_plateau_band(self):
        _, hi, speed, max_sim, _ = levels.band_for_level(15)
        assert hi == 99  # open-ended
        assert speed == (3.0, 3.0)
        assert max_sim == 5

    def test_level_99_still_plateau(self):
        lo, hi, _, _, _ = levels.band_for_level(99)
        assert lo == 15


class TestExpectedTime:
    def test_5_char_word(self):
        # max(0.50, (5-1)*0.50) = max(0.50, 2.0) = 2.0
        assert levels.expected_time("hello") == pytest.approx(2.0)

    def test_1_char_word(self):
        # max(0.50, 0) = 0.50
        assert levels.expected_time("a") == pytest.approx(levels.BASE_FLOOR)

    def test_2_char_word(self):
        # max(0.50, 0.50) = 0.50
        assert levels.expected_time("ab") == pytest.approx(0.50)

    def test_10_char_word(self):
        # max(0.50, 4.5) = 4.5
        assert levels.expected_time("abcdefghij") == pytest.approx(4.5)


class TestRedZone:
    def test_in_red_zone(self):
        assert levels.is_red_zone(18.0, 20.0) is True  # 2 rows away

    def test_not_in_red_zone(self):
        assert levels.is_red_zone(10.0, 20.0) is False

    def test_exactly_at_water(self):
        assert levels.is_red_zone(20.0, 20.0) is True

    def test_at_red_zone_boundary(self):
        # RED_ZONE_ROWS = 3, water at 20: row 17 is exactly at boundary
        assert levels.is_red_zone(17.0, 20.0) is True
        assert levels.is_red_zone(16.9, 20.0) is False


class TestBonusWave:
    def test_level_5_is_bonus(self):
        assert levels.is_bonus_wave(5) is True

    def test_level_10_is_bonus(self):
        assert levels.is_bonus_wave(10) is True

    def test_level_1_is_not_bonus(self):
        assert levels.is_bonus_wave(1) is False

    def test_level_3_is_not_bonus(self):
        assert levels.is_bonus_wave(3) is False

    def test_level_0_is_not_bonus(self):
        assert levels.is_bonus_wave(0) is False


class TestPlateauSurge:
    def test_depth_0(self):
        speed_mult, spawn_mult = levels.plateau_surge_params(0)
        assert speed_mult == pytest.approx(1.0)
        assert spawn_mult == pytest.approx(1.0)

    def test_depth_1(self):
        speed_mult, spawn_mult = levels.plateau_surge_params(1)
        assert speed_mult == pytest.approx(1.05)
        assert spawn_mult == pytest.approx(1.025)

    def test_escalating(self):
        s0, _ = levels.plateau_surge_params(0)
        s1, _ = levels.plateau_surge_params(1)
        s2, _ = levels.plateau_surge_params(2)
        assert s0 < s1 < s2


class TestTunableConstants:
    """Verify constants match PLAN defaults."""

    def test_per_char_seconds(self):
        assert levels.per_char_seconds == 0.50

    def test_base_floor(self):
        assert levels.BASE_FLOOR == 0.50

    def test_danger_flat(self):
        assert levels.DANGER_FLAT == 10

    def test_acc_per_error(self):
        assert levels.ACC_PER_ERROR == 0.85

    def test_combo_chars_per_step(self):
        assert levels.COMBO_CHARS_PER_STEP == 5

    def test_bonus_wave_mult(self):
        assert levels.BONUS_WAVE_MULT == 2.0

    def test_danger_flat_bound(self):
        """DANGER_FLAT <= 0.5 * base_value of shortest scoring word (2-char = 20)."""
        shortest_base = 2 * 10  # 2-char word, each char = 10
        assert levels.DANGER_FLAT <= 0.5 * shortest_base
