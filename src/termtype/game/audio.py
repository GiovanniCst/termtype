"""Optional audio manager — streamed music loop and pooled SFX.

PLAN §8.5, §8.6, §8.7. Graceful degradation to NullAudio.
"""
from __future__ import annotations

import contextlib
import os
from typing import Any

# Mixer buffer in frames. 512 underruns on high-latency backends (notably
# PulseAudio/PipeWire under WSL), which is heard as crackle/"clipping"; 1024
# (~23 ms at 44.1 kHz) is gap-free there while keeping keystroke SFX snappy.
_MIXER_FREQUENCY = 44100
_MIXER_BUFFER = 1024

# SFX that fire in rapid bursts — replaying one identical sample produces the
# "machine gun" artifact, so we round-robin a few subtle pitch variants.
_VARIED_SFX = frozenset({"key.wav", "typo.wav"})
_PITCH_FACTORS = (1.0, 1.06, 0.94, 1.11)


class NullAudio:
    """No-op audio manager when pygame is unavailable."""

    def play_sfx(self, name: str, volume: float = 1.0, priority: bool = False) -> None:
        pass

    def play_music(self, name: str, volume: float = 1.0, loop: bool = True) -> None:
        pass

    def stop_music(self) -> None:
        pass

    def set_music_volume(self, volume: float) -> None:
        pass

    def set_sfx_volume(self, volume: float) -> None:
        pass

    def set_enabled(self, music_on: bool, sfx_on: bool) -> None:
        pass

    def is_available(self) -> bool:
        return False

    def cleanup(self) -> None:
        pass


class AudioManager:
    """Audio manager using pygame.mixer.

    Lazy-imports pygame to avoid terminal side effects at module import.
    SFX are cached Sound objects on a small channel pool; music streams
    via pygame.mixer.music (no full decode in RAM). Falls back to
    NullAudio if init fails.
    """

    def __init__(self, data_root: Any = None):
        self._available = False
        self._mixer = None
        self._sfx_cache: dict[str, Any] = {}
        self._sfx_variants: dict[str, list] = {}   # name -> round-robin Sound list
        self._variant_idx: dict[str, int] = {}     # name -> next variant index
        self._sfx_channels: list[Any] = []
        self._music_volume = 0.5
        self._sfx_volume = 0.7
        self._music_on = True
        self._sfx_on = True
        self._current_track: str | None = None
        # as_file context for the streaming track — held open while playing (PLAN §8.6)
        self._music_ctx = contextlib.ExitStack()

        if data_root is None:
            import importlib.resources
            data_root = importlib.resources.files("termtype") / "data"
        self._data_root = data_root

        self._init_audio()

    def _init_audio(self) -> None:
        """Attempt to initialize pygame mixer."""
        # Set SDL env vars before importing pygame (PLAN §8.7)
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        # WSLg's RDP audio transport crackles when SFX start with SDL's default
        # Pulse latency; the mix itself is clean (verified via RDPSink.monitor).
        # 60 ms target latency is the documented fix; setdefault keeps it
        # user-overridable.
        os.environ.setdefault("PULSE_LATENCY_MSEC", "60")

        try:
            import pygame
            import pygame.mixer
        except ImportError:
            return

        for retry_env in (None, "dummy"):
            if retry_env:
                os.environ["SDL_AUDIODRIVER"] = retry_env
            try:
                pygame.mixer.init(frequency=_MIXER_FREQUENCY, buffer=_MIXER_BUFFER)
                self._mixer = pygame.mixer
                self._available = True
                self._sfx_channels = [pygame.mixer.Channel(i) for i in range(4)]
                return
            except (pygame.error, OSError):
                continue

    def play_sfx(self, name: str, volume: float = 1.0, priority: bool = False) -> None:
        """Play a sound effect (filename under data/audio/sfx/).

        priority=True marks reward/feedback cues (word clear, combo, level-up…)
        that must not be dropped during a burst of keystroke clicks: they may
        use every channel and steal channel 0 if needed, while non-priority
        clicks avoid channel 0 so that headroom stays free.
        """
        if not self._available or not self._sfx_on:
            return

        sound = self._next_sound(name)
        if sound is None:
            return

        vol = _clamp_volume(volume * self._sfx_volume)

        # Clicks/menus skip channel 0, leaving it as headroom for reward cues.
        search = self._sfx_channels if priority else self._sfx_channels[1:]
        for ch in search:
            if not ch.get_busy():
                ch.set_volume(vol)
                ch.play(sound)
                return

        # A priority cue with no free channel steals channel 0 rather than drop.
        if priority and self._sfx_channels:
            ch = self._sfx_channels[0]
            ch.set_volume(vol)
            ch.play(sound)

    def play_music(self, name: str, volume: float = 1.0, loop: bool = True) -> None:
        """Stream background music (path under data/audio/music/, e.g. 'retro/title.ogg').

        Restarting the already-playing track is a no-op so menu hops don't
        reset the loop.
        """
        if not self._available or not self._music_on:
            return
        if name == self._current_track and self._mixer.music.get_busy():
            return

        try:
            import importlib.resources
            track = self._data_root / "audio" / "music" / name
            self._music_ctx.close()  # release previous track's temp file, if any
            path = self._music_ctx.enter_context(importlib.resources.as_file(track))
            self._mixer.music.load(str(path))
            self._mixer.music.set_volume(_clamp_volume(volume * self._music_volume))
            self._mixer.music.play(loops=-1 if loop else 0)
            self._current_track = name
        except Exception:
            self._current_track = None

    def stop_music(self) -> None:
        if self._available:
            try:
                self._mixer.music.stop()
                self._mixer.music.unload()
            except Exception:
                pass
            self._music_ctx.close()
            self._current_track = None

    def set_music_volume(self, volume: float) -> None:
        self._music_volume = _clamp_volume(volume)
        if self._available:
            try:
                self._mixer.music.set_volume(self._music_volume)
            except Exception:
                pass

    def set_sfx_volume(self, volume: float) -> None:
        self._sfx_volume = _clamp_volume(volume)

    def set_enabled(self, music_on: bool, sfx_on: bool) -> None:
        """Apply config toggles; turning music off stops the current track."""
        self._sfx_on = sfx_on
        if self._music_on and not music_on:
            self.stop_music()
        self._music_on = music_on

    def is_available(self) -> bool:
        return self._available

    def cleanup(self) -> None:
        if self._available and self._mixer:
            self.stop_music()
            try:
                self._mixer.quit()
            except Exception:
                pass

    def _get_sfx(self, name: str) -> Any:
        """Load and cache a sound effect."""
        if name in self._sfx_cache:
            return self._sfx_cache[name]

        try:
            import importlib.resources
            sfx_path = self._data_root / "audio" / "sfx" / name
            with importlib.resources.as_file(sfx_path) as p:
                sound = self._mixer.Sound(str(p))
                self._sfx_cache[name] = sound
                return sound
        except Exception:
            self._sfx_cache[name] = None  # don't retry a missing file every keystroke
            return None

    def _next_sound(self, name: str) -> Any:
        """Return the Sound to play, round-robining pitch variants for _VARIED_SFX."""
        variants = self._sfx_variants.get(name)
        if variants is None:
            variants = self._load_variants(name)
            self._sfx_variants[name] = variants
        if not variants:
            return None
        i = self._variant_idx.get(name, 0)
        self._variant_idx[name] = (i + 1) % len(variants)
        return variants[i]

    def _load_variants(self, name: str) -> list:
        """Build the variant list for a sound: base plus pitch copies if varied."""
        base = self._get_sfx(name)
        if base is None:
            return []
        if name not in _VARIED_SFX:
            return [base]
        variants = [base]
        for factor in _PITCH_FACTORS[1:]:
            shifted = self._pitch_shift(base, factor)
            if shifted is not None:
                variants.append(shifted)
        return variants

    def _pitch_shift(self, sound: Any, factor: float) -> Any:
        """Nearest-neighbour resample to shift pitch — dependency-free.

        Fewer output frames → higher pitch (and slightly shorter). Returns a new
        Sound, or None if the raw format isn't 16-bit (caller keeps the base).
        """
        try:
            from array import array
            info = self._mixer.get_init()  # (frequency, format, channels)
            if not info:
                return None
            _, fmt, channels = info
            if abs(fmt) != 16 or channels < 1:
                return None
            typecode = "h" if fmt < 0 else "H"
            samples = array(typecode)
            samples.frombytes(sound.get_raw())
            frames = len(samples) // channels
            if frames < 2:
                return None
            out_frames = max(1, int(frames / factor))
            out = array(typecode, bytes(out_frames * channels * 2))
            for i in range(out_frames):
                src = int(i * factor)
                if src >= frames:
                    src = frames - 1
                sb, ob = src * channels, i * channels
                for c in range(channels):
                    out[ob + c] = samples[sb + c]
            return self._mixer.Sound(buffer=out.tobytes())
        except Exception:
            return None


def _clamp_volume(value: float) -> float:
    return max(0.0, min(1.0, value))


def create_audio_manager(data_root: Any = None) -> AudioManager | NullAudio:
    """Factory that returns a real AudioManager or NullAudio fallback."""
    try:
        manager = AudioManager(data_root)
    except Exception:
        return NullAudio()
    if manager.is_available():
        return manager
    return NullAudio()
