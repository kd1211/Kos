"""
Shared wallpaper rendering: turns the choice saved in ui.theme ("None", a
built-in gradient name, or "Custom Photo" + a path) into a ready-to-paste
PIL Image sized for the screen. Used by Home (and available to any other
screen, like the lock screen, that wants the same background).

Results are cached by (choice, path, size) so a photo wallpaper isn't
re-decoded and re-cropped on every single frame -- only when the choice
or screen size actually changes.
"""

import os
from PIL import Image

from ui import theme

GRADIENTS = {
    "Sunset Gradient": ((255, 150, 90), (35, 20, 55)),
    "Ocean Gradient": ((60, 140, 220), (10, 20, 40)),
    "Aurora Gradient": ((70, 220, 160), (20, 20, 60)),
    "Grape Gradient": ((170, 110, 255), (20, 14, 30)),
}
WALLPAPER_CHOICES = ["None"] + list(GRADIENTS.keys()) + ["Custom Photo"]

_cache = {"key": None, "image": None}


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _build_gradient(top, bottom, w, h):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        color = _lerp(top, bottom, y / max(1, h - 1))
        for x in range(w):
            px[x, y] = color
    return img


def _fit_crop(src, w, h):
    """Scale src up just enough to cover w x h, then center-crop."""
    src_ratio = src.width / src.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h = h
        new_w = max(w, int(h * src_ratio))
    else:
        new_w = w
        new_h = max(h, int(w / src_ratio))
    src = src.resize((new_w, new_h))
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return src.crop((left, top, left + w, top + h))


def get_wallpaper(w, h):
    """Returns a PIL Image (w x h) for the current wallpaper choice, or
    None if wallpaper is off (caller should just fill the theme bg color)."""
    choice = theme.get("wallpaper")
    if not choice or choice == "None":
        return None

    path = theme.get("wallpaper_path") if choice == "Custom Photo" else None
    key = (choice, path, w, h)
    if _cache["key"] == key:
        return _cache["image"]

    image = None
    if choice in GRADIENTS:
        top, bottom = GRADIENTS[choice]
        image = _build_gradient(top, bottom, w, h)
    elif choice == "Custom Photo" and path and os.path.exists(path):
        try:
            image = _fit_crop(Image.open(path).convert("RGB"), w, h)
        except Exception:
            image = None

    _cache["key"] = key
    _cache["image"] = image
    return image
