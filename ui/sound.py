"""
Central sound manager for PiOS: short UI feedback tones, alarm/timer
beeps, and background music playback for the Music app.

Built on pygame's mixer only (no video/display init, so it stays light).
`numpy` -- already a PiOS dependency for the LCD framebuffer -- is reused
to synthesize tones on the fly, so no audio asset files are needed for
clicks/beeps.

Every function fails silently if pygame or an audio device isn't
available, so units with nothing wired to the audio jack keep working
exactly as before; sound is a bonus, never a requirement.
"""

import time
import numpy as np

from ui import theme

_pg = None
_ready = False
_click_snd = None
_beep_cache = {}


def _ensure_init():
    global _pg, _ready
    if _pg is not None:
        return _ready
    try:
        import pygame
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=256)
        _pg = pygame
        _ready = True
    except Exception:
        _pg = False
        _ready = False
    return _ready


def _tone_array(freq, ms, vol):
    sr = 22050
    n = max(1, int(sr * ms / 1000))
    t = np.linspace(0, ms / 1000.0, n, endpoint=False)
    wave = np.sin(2 * np.pi * freq * t)
    # short fade in/out so tones don't click/pop
    fade = max(1, n // 12)
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    samples = (wave * env * vol * 32767).astype(np.int16)
    return samples


def _volume_scalar():
    if not theme.get("sound_enabled"):
        return 0.0
    return max(0, min(100, theme.get("volume"))) / 100.0


def click():
    """Short UI tap-feedback tone. Cheap enough to call on every tap."""
    global _click_snd
    if not theme.get("sound_enabled") or not theme.get("click_sound"):
        return
    if not _ensure_init():
        return
    try:
        if _click_snd is None:
            _click_snd = _pg.sndarray.make_sound(_tone_array(1400, 25, 0.5))
        _click_snd.set_volume(_volume_scalar())
        _click_snd.play()
    except Exception:
        pass


def beep(freq=880, ms=180):
    """A single tone -- used for alarms, timers, game/app feedback."""
    if not theme.get("sound_enabled"):
        return
    if not _ensure_init():
        return
    try:
        key = (freq, ms)
        snd = _beep_cache.get(key)
        if snd is None:
            snd = _pg.sndarray.make_sound(_tone_array(freq, ms, 0.6))
            _beep_cache[key] = snd
        snd.set_volume(_volume_scalar())
        snd.play()
    except Exception:
        pass


def chime():
    """A friendlier two-note chime for alarms going off / notifications."""
    beep(880, 140)
    time.sleep(0.05)
    beep(1175, 200)


def play_music(path, loop=False):
    """Starts streaming an audio file (mp3/ogg/wav) via the music channel.
    Returns True if playback started."""
    if not _ensure_init():
        return False
    try:
        _pg.mixer.music.load(path)
        _pg.mixer.music.set_volume(_volume_scalar())
        _pg.mixer.music.play(-1 if loop else 0)
        return True
    except Exception:
        return False


def pause_music():
    if _ensure_init():
        try:
            _pg.mixer.music.pause()
        except Exception:
            pass


def resume_music():
    if _ensure_init():
        try:
            _pg.mixer.music.unpause()
        except Exception:
            pass


def stop_music():
    if _ensure_init():
        try:
            _pg.mixer.music.stop()
        except Exception:
            pass


def is_music_playing():
    if not _ensure_init():
        return False
    try:
        return _pg.mixer.music.get_busy()
    except Exception:
        return False


def refresh_volume():
    """Call after the volume setting changes so an already-playing track
    picks up the new level immediately."""
    if _ensure_init():
        try:
            _pg.mixer.music.set_volume(_volume_scalar())
        except Exception:
            pass
