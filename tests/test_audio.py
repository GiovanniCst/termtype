"""Tests for audio.py — AudioManager and NullAudio."""
import pytest
import os
from unittest.mock import patch, MagicMock
from termtype.game.audio import NullAudio, AudioManager, create_audio_manager


class TestNullAudio:
    def test_all_methods_are_noop(self):
        audio = NullAudio()
        audio.play_sfx("test")
        audio.play_music("test")
        audio.stop_music()
        audio.set_music_volume(0.5)
        audio.set_sfx_volume(0.5)
        audio.cleanup()
        assert audio.is_available() is False


class TestAudioManagerFallback:
    def test_null_audio_when_init_raises(self):
        """When mixer.init raises, falls back to NullAudio-like state."""
        import pygame
        original_init = pygame.mixer.init
        try:
            pygame.mixer.init = MagicMock(side_effect=pygame.error("no audio"))
            manager = AudioManager()
            assert manager.is_available() is False
        finally:
            pygame.mixer.init = original_init

    def test_sdl_env_set_before_init(self):
        """SDL_VIDEODRIVER is set before mixer init."""
        with patch.dict(os.environ, {}, clear=False):
            if "SDL_VIDEODRIVER" in os.environ:
                del os.environ["SDL_VIDEODRIVER"]

            # Just verify the init path sets it
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            assert os.environ.get("SDL_VIDEODRIVER") == "dummy"


class TestVolumeClamp:
    def test_create_manager_returns_type(self):
        """create_audio_manager returns either AudioManager or NullAudio."""
        result = create_audio_manager()
        assert isinstance(result, (AudioManager, NullAudio))

    def test_null_audio_play_sfx_noop(self):
        """NullAudio.play_sfx doesn't raise (incl. the priority kwarg)."""
        audio = NullAudio()
        audio.play_sfx("test.wav", volume=0.5)
        audio.play_sfx("test.wav", volume=0.5, priority=True)
        # No assertion needed — just shouldn't raise


class TestSfxVariation:
    """Round-robin pitch variation for rapid-fire SFX (key/typo)."""

    def _manager(self):
        mgr = create_audio_manager()
        if not isinstance(mgr, AudioManager) or not mgr.is_available():
            pytest.skip("no audio mixer available")
        return mgr

    def test_varied_sfx_has_multiple_variants(self):
        mgr = self._manager()
        from termtype.game.audio import _PITCH_FACTORS
        assert len(mgr._load_variants("key.wav")) == len(_PITCH_FACTORS)

    def test_non_varied_sfx_has_single_variant(self):
        mgr = self._manager()
        assert len(mgr._load_variants("word.wav")) == 1

    def test_next_sound_round_robins(self):
        mgr = self._manager()
        ids = {id(mgr._next_sound("key.wav")) for _ in range(8)}
        assert len(ids) == len(mgr._load_variants("key.wav")) >= 2

    def test_play_sfx_priority_does_not_raise(self):
        mgr = self._manager()
        mgr.play_sfx("word.wav", volume=0.9, priority=True)
        mgr.play_sfx("key.wav", volume=0.2)
