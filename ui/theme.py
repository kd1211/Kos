"""
Central, persisted OS settings: color theme, brightness, sleep timeout,
sound/volume, and clock format. Everything lives in one small JSON file
so every app/screen can read the same live values instead of each
inventing its own storage.

Usage:
    from ui import theme
    theme.get("volume")
    theme.set("volume", 80)          # also saves to disk immediately
    theme.accent_color()             # current theme's accent RGB tuple
"""

import json
import os

SETTINGS_PATH = os.path.expanduser("~/.pios_settings.json")

# Each preset is a full palette so switching themes recolors the whole OS:
# background, cards/buttons, foreground text, and the accent color used
# for highlights, progress bars, and primary text.
PRESETS = {
    "Midnight Blue": {"bg": (18, 18, 24), "card": (32, 32, 40),
                       "fg": (235, 235, 240), "accent": (68, 140, 255)},
    "Charcoal":       {"bg": (20, 20, 20), "card": (38, 38, 38),
                       "fg": (240, 240, 240), "accent": (230, 230, 230)},
    "Forest":         {"bg": (14, 22, 18), "card": (26, 40, 32),
                       "fg": (230, 240, 230), "accent": (80, 200, 120)},
    "Sunset":         {"bg": (28, 16, 20), "card": (46, 27, 32),
                       "fg": (245, 235, 230), "accent": (255, 140, 90)},
    "Grape":          {"bg": (22, 16, 30), "card": (40, 29, 50),
                       "fg": (235, 230, 245), "accent": (170, 110, 255)},
    "AMOLED Black":   {"bg": (0, 0, 0), "card": (26, 26, 26),
                       "fg": (230, 230, 230), "accent": (255, 60, 90)},
}
PRESET_NAMES = list(PRESETS.keys())

_defaults = {
    "theme": "Midnight Blue",
    "brightness": 90,
    "sleep_timeout": 0,       # seconds of inactivity before auto-sleep; 0 = never
    "volume": 70,             # 0-100, master volume for music + tones
    "sound_enabled": True,    # master sound on/off
    "click_sound": True,      # UI tap feedback tone
    "clock_24h": True,        # 24h vs 12h clock everywhere

    "wifi_enabled": True,          # unused since Wi-Fi is now controlled for
    "bluetooth_enabled": False,    # real via ui/net_control -- kept only so an
                                    # existing ~/.pios_settings.json still loads

    "pin_enabled": False,         # Settings > Security
    "pin_code": "",               # 4-digit PIN, stored in the clear locally
                                   # (this is a hobby device, not a vault)

    "developer_mode": False,      # Settings > Developer mode

    "wallpaper": "None",          # Settings > Wallpaper: "None" or a preset
                                   # gradient name, or "Custom Photo"
    "wallpaper_path": "",         # used when wallpaper == "Custom Photo"

    "device_name": "PiOS Device",  # Settings > About > Rename This Device

    # touch calibration, written by the Calibrate Touch app. None = raw
    # driver coordinates are used as-is (the default/factory state).
    "touch_cal": None,
}

_state = dict(_defaults)


def load():
    global _state
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        merged = dict(_defaults)
        merged.update({k: v for k, v in data.items() if k in _defaults})
        _state = merged
    except Exception:
        _state = dict(_defaults)
    return _state


def save():
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(_state, f)
    except Exception:
        pass


def get(key):
    return _state.get(key, _defaults.get(key))


def set(key, value):
    _state[key] = value
    save()


def reset():
    global _state
    _state = dict(_defaults)
    save()


def current_palette():
    return PRESETS.get(_state.get("theme"), PRESETS["Midnight Blue"])


def bg_color():
    return current_palette()["bg"]


def card_color():
    return current_palette()["card"]


def fg_color():
    return current_palette()["fg"]


def accent_color():
    return current_palette()["accent"]


def next_theme():
    """Cycle to the next preset (used by a single 'Theme' button)."""
    names = PRESET_NAMES
    i = names.index(_state.get("theme", names[0])) if _state.get("theme") in names else -1
    new_name = names[(i + 1) % len(names)]
    set("theme", new_name)
    return new_name


load()
