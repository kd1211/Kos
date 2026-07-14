"""
Minimal phone-OS UI framework.

Everything is drawn into a single PIL "canvas" image every frame, which
gets pushed to the ST7796 panel. Touch is polled from the FT6336U.

Two kinds of touch input are exposed to apps:
  - on_tap(x, y)         -- fires once on finger-down (rising edge), used
                             by buttons/menus.
  - on_touch_move(x, y)  -- fires every frame the finger is held down,
                             used by apps that need continuous drag input
                             (e.g. Paint).
  - on_touch_up()        -- fires once when the finger is lifted.

The OS also owns a simple sleep mode (screen + backlight off) to save
battery on the UPS HAT (C) -- tap anywhere to wake back up.
"""

import os
import bisect
import time
from PIL import Image, ImageDraw, ImageFont

from ui import theme
from ui import sound
from ui._font_coverage import DEJAVU_RANGES

SCREEN_W = 320
SCREEN_H = 480
STATUS_BAR_H = 28

# -- font loading -----------------------------------------------------------
# Two fonts ship with the OS (assets/fonts/) so the UI looks and covers
# Unicode consistently regardless of what's freshly flashed onto the SD
# card, rather than hoping the right system fonts happen to be installed:
#   DejaVuSans.ttf -- all normal text (labels, numbers, punctuation)
#   Symbola.ttf    -- fallback for the emoji/pictograph glyphs used as app
#                     icons (palette, globe, folder, lock, wifi, ...) that
#                     DejaVu doesn't have. Every icon glyph this project
#                     ships with was checked against Symbola at build time
#                     (see ui/_font_coverage.py for how DejaVu's own
#                     coverage was baked in) so this fallback should
#                     essentially never miss for anything in this repo.
_ASSETS_FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")


def _first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


_PRIMARY_FONT_PATH = _first_existing([
    os.path.join(_ASSETS_FONT_DIR, "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
])
_SYMBOL_FONT_PATH = _first_existing([
    os.path.join(_ASSETS_FONT_DIR, "Symbola.ttf"),
    "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
    "/usr/share/fonts/truetype/symbola/Symbola.ttf",
])

_DEJAVU_STARTS = [lo for lo, hi in DEJAVU_RANGES]


def _primary_covers(cp):
    """O(log n) range lookup -- no fontTools needed at runtime, since
    DejaVu's coverage was precomputed offline into ui/_font_coverage.py."""
    i = bisect.bisect_right(_DEJAVU_STARTS, cp) - 1
    if i < 0:
        return False
    lo, hi = DEJAVU_RANGES[i]
    return lo <= cp <= hi


_font_file_cache = {}


def _font_at(path, size):
    key = (path, size)
    if key not in _font_file_cache:
        try:
            _font_file_cache[key] = ImageFont.truetype(path, size) if path else None
        except Exception:
            _font_file_cache[key] = None
    return _font_file_cache[key]


def load_font(size):
    f = _font_at(_PRIMARY_FONT_PATH, size)
    if f is not None:
        return f
    return ImageFont.load_default()


def _symbol_font(size):
    return _font_at(_SYMBOL_FONT_PATH, size)


# -- transparent per-character font fallback for every draw.text() call -----
# Rather than touching the ~15 apps that call draw.text() directly, patch
# the one shared entry point (PIL's ImageDraw.text) so any string mixing
# ordinary text with an unsupported symbol -- e.g. Settings' menu rows
# ("\U0001F5BC  Wallpaper"), or the lock screen's "\U0001F512 Enter PIN"
# -- renders correctly everywhere, automatically, with no per-app changes.
_orig_text = ImageDraw.ImageDraw.text
_orig_textlength = ImageDraw.ImageDraw.textlength
_SUPPORTED_ANCHORS = ("mm", "lm", "rm")


def _text_with_fallback(self, xy, text, fill=None, font=None, anchor=None, **kwargs):
    text = str(text)
    if (font is None or not hasattr(font, "size") or anchor not in _SUPPORTED_ANCHORS
            or "\n" in text or _SYMBOL_FONT_PATH is None
            or all(_primary_covers(ord(ch)) for ch in text)):
        return _orig_text(self, xy, text, fill=fill, font=font, anchor=anchor, **kwargs)

    size = font.size
    sym_font = _symbol_font(size) or font

    runs = []
    cur_font, cur_text = font, ""
    for ch in text:
        chosen = font if _primary_covers(ord(ch)) else sym_font
        if chosen is cur_font:
            cur_text += ch
        else:
            if cur_text:
                runs.append((cur_font, cur_text))
            cur_font, cur_text = chosen, ch
    if cur_text:
        runs.append((cur_font, cur_text))

    total_w = sum(_orig_textlength(self, t, font=f) for f, t in runs)
    if anchor[0] == "m":
        cursor = xy[0] - total_w / 2
    elif anchor[0] == "r":
        cursor = xy[0] - total_w
    else:
        cursor = xy[0]

    for f, t in runs:
        _orig_text(self, (cursor, xy[1]), t, fill=fill, font=f, anchor="lm", **kwargs)
        cursor += _orig_textlength(self, t, font=f)


ImageDraw.ImageDraw.text = _text_with_fallback

# These four are seeded from whatever theme was saved on disk at import
# time, and stay around as sane static defaults for any app/screen that
# imports them directly (e.g. `from ui.framework import ACCENT`). Anything
# drawn *inside this module* (status bar, Button, Keyboard, lock screen)
# instead re-reads ui.theme live on every frame, so it repaints instantly
# when the user changes the theme in Settings -- no restart needed.
BG_COLOR = theme.bg_color()
FG_COLOR = theme.fg_color()
ACCENT = theme.accent_color()
CARD_COLOR = theme.card_color()

_UNSET = object()  # sentinel so Button/Keyboard can tell "use live theme"
                    # apart from "an app explicitly passed a color"


FONT_SM = load_font(14)
FONT_MD = load_font(18)
FONT_LG = load_font(28)
FONT_XL = load_font(40)


class Button:
    """A tappable rectangular region with a label."""

    def __init__(self, x, y, w, h, label, on_tap, icon=None,
                 bg=_UNSET, fg=_UNSET, font=FONT_MD):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.label = label
        self.on_tap = on_tap
        self.icon = icon
        self.bg = bg
        self.fg = fg
        self.font = font

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def draw(self, draw):
        bg = theme.card_color() if self.bg is _UNSET else self.bg
        fg = theme.fg_color() if self.fg is _UNSET else self.fg
        draw.rounded_rectangle(
            [self.x, self.y, self.x + self.w, self.y + self.h],
            radius=14, fill=bg)
        if self.icon:
            draw.text((self.x + self.w // 2, self.y + self.h // 2 - 14),
                       self.icon, font=FONT_XL, fill=fg, anchor="mm")
            draw.text((self.x + self.w // 2, self.y + self.h - 16),
                       self.label, font=FONT_SM, fill=fg, anchor="mm")
        else:
            draw.text((self.x + self.w // 2, self.y + self.h // 2),
                       self.label, font=self.font, fill=fg, anchor="mm")


class Keyboard:
    """A compact on-screen QWERTY keyboard for apps that need typed text
    (Notes, Browser's URL bar, etc).

    Usage from an app:
        self.keyboard = Keyboard(4, SCREEN_H - 190, SCREEN_W - 8, 184)
        ...
        def on_tap(self, x, y):
            if self.keyboard.on_tap(x, y, self._on_key):
                return True
            return super().on_tap(x, y)

        def _on_key(self, val):
            if val == "BACKSPACE":
                self.draft = self.draft[:-1]
            elif val == "ENTER":
                self._submit()
            else:
                self.draft += val   # val is a literal character, incl. " "

    `on_key` is called with a single typed character, or one of the special
    tokens "BACKSPACE"/"ENTER" (space is passed through as a literal " " for
    convenience, so most apps can just do `self.draft += val`).
    """

    ROWS_LOWER = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    ROWS_UPPER = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
    ROWS_SYMS = ["1234567890", "-/:;()$&@\"", ".,?!'#%*+="]

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.shift = False
        self.symbols = False
        self._keys = []
        self._layout()

    def _rows(self):
        if self.symbols:
            return self.ROWS_SYMS
        return self.ROWS_UPPER if self.shift else self.ROWS_LOWER

    def _layout(self):
        self._keys = []
        rows = self._rows()
        pad = 3
        row_h = self.h // 4

        for r, row in enumerate(rows):
            n = len(row)
            key_w = (self.w - pad * (n + 1)) // n
            used = key_w * n + pad * (n - 1)
            offset = (self.w - used) // 2
            ry = self.y + r * row_h
            for i, ch in enumerate(row):
                kx = self.x + offset + i * (key_w + pad)
                self._keys.append((kx, ry, key_w, row_h - pad, ch))

        # bottom row: symbols/letters toggle, shift, space, backspace, enter
        by = self.y + 3 * row_h
        bw_small = int(self.w * 0.16)
        bw_space = self.w - bw_small * 4 - pad * 5
        x0 = self.x
        self._keys.append((x0, by, bw_small, row_h - pad,
                            "ABC" if self.symbols else "SYM"))
        x0 += bw_small + pad
        self._keys.append((x0, by, bw_small, row_h - pad, "SHIFT"))
        x0 += bw_small + pad
        self._keys.append((x0, by, bw_space, row_h - pad, "SPACE"))
        x0 += bw_space + pad
        self._keys.append((x0, by, bw_small, row_h - pad, "BACKSPACE"))
        x0 += bw_small + pad
        self._keys.append((x0, by, bw_small, row_h - pad, "ENTER"))

    def on_tap(self, px, py, on_key):
        """Returns True (and fires on_key) if the tap landed on a key."""
        for (kx, ky, kw, kh, val) in self._keys:
            if kx <= px <= kx + kw and ky <= py <= ky + kh:
                if val == "SHIFT":
                    self.shift = not self.shift
                    self._layout()
                elif val in ("SYM", "ABC"):
                    self.symbols = not self.symbols
                    self.shift = False
                    self._layout()
                elif val == "SPACE":
                    on_key(" ")
                elif val in ("BACKSPACE", "ENTER"):
                    on_key(val)
                else:
                    on_key(val)
                    if self.shift and not self.symbols:
                        # auto-unshift after one letter, like a phone keyboard
                        self.shift = False
                        self._layout()
                return True
        return False

    def draw(self, draw):
        draw.rectangle([self.x - 4, self.y - 4, self.x + self.w + 4, self.y + self.h + 4],
                        fill=(10, 10, 14))
        labels = {"BACKSPACE": "\u232B", "ENTER": "\u23CE", "SPACE": "",
                  "SHIFT": "\u21E7", "SYM": "123", "ABC": "ABC"}
        card, accent, fg = theme.card_color(), theme.accent_color(), theme.fg_color()
        for (kx, ky, kw, kh, val) in self._keys:
            bg = accent if (val == "SHIFT" and self.shift) else card
            draw.rounded_rectangle([kx, ky, kx + kw, ky + kh], radius=6, fill=bg)
            draw.text((kx + kw // 2, ky + kh // 2), labels.get(val, val),
                       font=FONT_SM, fill=fg, anchor="mm")


class ScrollArea:
    """Finger-drag vertical scrolling for a fixed on-screen region.

    An app owns one of these per scrollable list. Feed it touch
    coordinates from the app's on_tap/on_touch_move/on_touch_up; read
    `.offset` when laying out content each frame (subtract it from each
    row's natural y position). Because a single on_tap already fires on
    finger-down, apps that mix scrolling with tappable rows should defer
    the row's action until on_touch_up, and only fire it if `was_drag()`
    is False -- otherwise a scroll gesture that starts on a row would
    also trigger that row.
    """

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.content_h = h
        self.offset = 0
        self._drag_start_y = None
        self._drag_start_offset = 0
        self._moved = False

    def set_content_height(self, content_h):
        self.content_h = content_h
        self.offset = max(0, min(self.offset, self.max_offset()))

    def max_offset(self):
        return max(0, self.content_h - self.h)

    def contains(self, x, y):
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h

    def begin_drag(self, y):
        self._drag_start_y = y
        self._drag_start_offset = self.offset
        self._moved = False

    def drag_to(self, y):
        if self._drag_start_y is None:
            self.begin_drag(y)
            return
        dy = y - self._drag_start_y
        if abs(dy) > 4:
            self._moved = True
        self.offset = max(0, min(self.max_offset(), self._drag_start_offset - dy))

    def end_drag(self):
        self._drag_start_y = None

    def was_drag(self):
        """True if the drag that just ended moved enough to not count as a tap."""
        return self._moved

    def draw_scrollbar(self, draw, color):
        """A thin indicator on the right edge, only drawn if there's more
        content than fits -- a visual hint that the list scrolls."""
        max_off = self.max_offset()
        if max_off <= 0:
            return
        track_h = self.h
        thumb_h = max(24, int(track_h * self.h / self.content_h))
        thumb_y = self.y + int((track_h - thumb_h) * (self.offset / max_off))
        bx = self.x + self.w - 4
        draw.rounded_rectangle([bx, thumb_y, bx + 3, thumb_y + thumb_h], radius=2, fill=color)


class App:
    """Base class every app screen implements."""

    name = "App"
    icon = "?"

    # Most screens are static and only need to redraw in response to a
    # touch (the run loop below skips rendering otherwise, to keep the
    # SPI bus and CPU free while idle). Apps that animate on their own
    # timer -- games with continuous motion, the emulator while a ROM is
    # actually running -- set this True (either as a flat `self.wants_animation
    # = True` in on_open, or as a @property for state-dependent cases
    # like EmulatorApp) so the OS keeps rendering them every frame
    # regardless of touch state.
    wants_animation = False

    def __init__(self, os_ref):
        self.os = os_ref
        self.buttons = []

    def on_open(self):
        pass

    def on_close(self):
        pass

    def draw(self, draw, canvas):
        pass

    def on_tap(self, x, y):
        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True
        return False

    def on_touch_move(self, x, y):
        """Called every frame while the finger is held down. Override for drag input."""
        pass

    def on_touch_up(self):
        """Called once when the finger is lifted."""
        pass


def build_grid(names, get_icon, on_select, top=None, cols=3, bottom_pad=10):
    """
    Lay out `names` as an auto-scaling grid of icon buttons that always
    fits the screen, however many items there are (used by Home and by
    folders). Returns a list of Button objects.
    """
    import math

    if top is None:
        top = STATUS_BAR_H + 44
    margin = 10
    rows = max(1, math.ceil(len(names) / cols))

    available_w = SCREEN_W - margin * (cols + 1)
    available_h = SCREEN_H - top - bottom_pad - margin * (rows + 1)
    cell = max(48, min(available_w // cols, available_h // rows))

    grid_w = cell * cols + margin * (cols - 1)
    x_offset = (SCREEN_W - grid_w) // 2
    font = FONT_SM if cell < 80 else None

    buttons = []
    for i, name in enumerate(names):
        row, col = divmod(i, cols)
        x = x_offset + col * (cell + margin)
        y = top + row * (cell + margin)
        btn = Button(x, y, cell, cell, name, (lambda n=name: on_select(n)),
                     icon=get_icon(name))
        if font:
            btn.font = font
        buttons.append(btn)
    return buttons


class PhoneOS:
    """Owns the frame loop: render -> push to LCD -> poll touch -> dispatch."""

    def __init__(self, lcd, touch, battery):
        self.lcd = lcd
        self.touch = touch
        self.battery = battery
        self.apps = {}
        self.current_app = None
        self._last_touch_state = False
        self._battery_cache = {"voltage": 0, "percent": 100, "charging": False}
        self._battery_last_read = 0
        self.sleeping = False
        self._prev_brightness = theme.get("brightness")
        self._last_activity = time.time()

        # -- PIN lock screen state (enforced here so every app benefits,
        # not just ones that remember to check theme.get("pin_enabled")) --
        self.locked = False
        self._lock_draft = ""
        self._lock_error = None
        self._lock_keys = self._build_lock_keys()

        try:
            self.lcd.set_backlight(self._prev_brightness)
        except Exception:
            pass

        # reused every frame instead of allocating a fresh Image each
        # time -- every app already fully repaints whatever region it
        # owns (that's how this immediate-mode renderer has always
        # worked), so render() just needs to blank the whole canvas to
        # the theme background first, same guarantee a fresh Image.new()
        # gave for free, without paying the allocation cost every frame
        self._canvas = Image.new("RGB", (SCREEN_W, SCREEN_H), theme.bg_color())

    def register_app(self, app_cls):
        self.apps[app_cls.name] = app_cls(self)

    def open_app(self, name):
        if self.current_app:
            self.current_app.on_close()
        self.current_app = self.apps[name]
        self.current_app.on_open()

    def go_home(self):
        self.open_app("Home")

    # -- power / sleep -----------------------------------------------
    def enter_sleep(self, current_brightness=90):
        self._prev_brightness = current_brightness
        self.sleeping = True
        try:
            self.lcd.set_backlight(0)
        except Exception:
            pass

    def wake(self):
        self.sleeping = False
        try:
            self.lcd.set_backlight(self._prev_brightness)
        except Exception:
            pass
        if theme.get("pin_enabled") and theme.get("pin_code"):
            self.locked = True
            self._lock_draft = ""
            self._lock_error = None

    # -- PIN lock screen -------------------------------------------------
    def _build_lock_keys(self):
        labels = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "\u232B"]
        cols = 3
        bw, bh = 80, 56
        gap = 14
        grid_w = cols * bw + (cols - 1) * gap
        x0 = (SCREEN_W - grid_w) // 2
        y0 = STATUS_BAR_H + 190
        keys = []
        for i, lab in enumerate(labels):
            r, c = divmod(i, cols)
            x = x0 + c * (bw + gap)
            y = y0 + r * (bh + gap)
            keys.append((x, y, bw, bh, lab))
        return keys

    def _lock_on_tap(self, x, y):
        for (kx, ky, kw, kh, lab) in self._lock_keys:
            if kx <= x <= kx + kw and ky <= y <= ky + kh:
                if lab == "C":
                    self._lock_draft = ""
                    self._lock_error = None
                elif lab == "\u232B":
                    self._lock_draft = self._lock_draft[:-1]
                elif len(self._lock_draft) < 4:
                    self._lock_draft += lab
                    if len(self._lock_draft) == 4:
                        if self._lock_draft == theme.get("pin_code"):
                            self.locked = False
                            self._lock_draft = ""
                            self._lock_error = None
                        else:
                            self._lock_error = "Incorrect PIN"
                            self._lock_draft = ""
                return

    def _draw_lock_screen(self, draw):
        fg = theme.fg_color()
        draw.rectangle([0, STATUS_BAR_H, SCREEN_W, SCREEN_H], fill=theme.bg_color())
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 50), "\U0001F512 Enter PIN", font=FONT_LG,
                   fill=fg, anchor="mm")

        n = len(self._lock_draft)
        dot_gap = 34
        x0 = SCREEN_W // 2 - dot_gap * 3 // 2
        cy = STATUS_BAR_H + 110
        for i in range(4):
            cx = x0 + i * dot_gap
            filled = i < n
            color = theme.accent_color() if filled else theme.card_color()
            draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=color, outline=fg)

        if self._lock_error:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 145), self._lock_error, font=FONT_SM,
                       fill=(230, 90, 90), anchor="mm")

        for (kx, ky, kw, kh, lab) in self._lock_keys:
            draw.rounded_rectangle([kx, ky, kx + kw, ky + kh], radius=10, fill=theme.card_color())
            draw.text((kx + kw // 2, ky + kh // 2), lab, font=FONT_LG, fill=fg, anchor="mm")

    # -- battery -------------------------------------------------------
    def _read_battery(self):
        now = time.time()
        if now - self._battery_last_read > 2.0:
            try:
                self._battery_cache = self.battery.read_all()
            except Exception:
                pass
            self._battery_last_read = now
        return self._battery_cache

    def _draw_status_bar(self, draw):
        fg = theme.fg_color()
        draw.rectangle([0, 0, SCREEN_W, STATUS_BAR_H], fill=(10, 10, 14))
        fmt = "%H:%M" if theme.get("clock_24h") else "%I:%M %p"
        clock_str = time.strftime(fmt)
        if not theme.get("clock_24h") and clock_str.startswith("0"):
            clock_str = clock_str[1:]  # drop leading zero on 12h hour
        draw.text((10, STATUS_BAR_H // 2), clock_str, font=FONT_SM,
                   fill=fg, anchor="lm")

        # a small speaker glyph shows when sound is muted, for at-a-glance state
        if not theme.get("sound_enabled"):
            draw.text((SCREEN_W // 2, STATUS_BAR_H // 2), "\U0001F507",
                       font=FONT_SM, fill=fg, anchor="mm")

        # a small DEV tag shows when Developer Mode is on in Settings, so
        # it's obvious at a glance that debug behavior may be active
        if theme.get("developer_mode"):
            draw.text((SCREEN_W // 2 + 24, STATUS_BAR_H // 2), "DEV",
                       font=FONT_SM, fill=(255, 180, 60), anchor="mm")

        batt = self._read_battery()
        pct = batt.get("percent", 100)
        charging = batt.get("charging", False)
        label = f"{pct}%{' +' if charging else ''}"
        draw.text((SCREEN_W - 10, STATUS_BAR_H // 2), label, font=FONT_SM,
                   fill=fg, anchor="rm")

        # simple battery glyph
        bx, by, bw, bh = SCREEN_W - 60, 8, 26, 12
        draw.rectangle([bx, by, bx + bw, by + bh], outline=fg)
        draw.rectangle([bx + bw, by + 3, bx + bw + 3, by + bh - 3], fill=fg)
        fill_w = int((bw - 2) * pct / 100)
        color = (80, 220, 120) if pct > 20 else (230, 90, 90)
        draw.rectangle([bx + 1, by + 1, bx + 1 + fill_w, by + bh - 1], fill=color)

    def render(self):
        if self.sleeping:
            draw = ImageDraw.Draw(self._canvas)
            draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=(0, 0, 0))
            self.lcd.display(self._canvas)
            return
        draw = ImageDraw.Draw(self._canvas)
        draw.rectangle([0, 0, SCREEN_W, SCREEN_H], fill=theme.bg_color())
        self._draw_status_bar(draw)
        if self.locked:
            self._draw_lock_screen(draw)
        elif self.current_app:
            self.current_app.draw(draw, self._canvas)
        self.lcd.display(self._canvas)

    def poll_touch_raw(self):
        """Returns the current touch point every frame, or None.

        If the user has run the Calibrate Touch app, a saved affine
        correction (scale + offset per axis) is applied here so every
        app benefits from it without touching the driver itself.
        """
        point = self.touch.read_point()
        if point is None:
            return None
        cal = theme.get("touch_cal")
        if not cal:
            return point
        x, y = point
        x = cal["ax"] * x + cal["bx"]
        y = cal["ay"] * y + cal["by"]
        x = max(0, min(SCREEN_W - 1, int(round(x))))
        y = max(0, min(SCREEN_H - 1, int(round(y))))
        return (x, y)

    # Target refresh while something's actually happening (touch held,
    # a touch event just fired, or the current app animates on its own
    # clock). Idle screens redraw far less often -- IDLE_REDRAW_INTERVAL
    # is only there to keep the status bar clock/battery%% from looking
    # frozen, not to chase a frame rate nothing is watching. Together
    # these matter more for "smoothness" than the render code itself:
    # every idle frame skipped is SPI bus time and CPU handed straight
    # back to the very next touch poll, and the sleep after an active
    # frame only fills whatever time *wasn't* already spent rendering,
    # instead of unconditionally tacking 50ms onto every single frame
    # the way this loop used to.
    ACTIVE_FRAME_INTERVAL = 1 / 30
    IDLE_POLL_INTERVAL = 0.05
    IDLE_REDRAW_INTERVAL = 1.0

    def run(self):
        self.go_home()
        if theme.get("pin_enabled") and theme.get("pin_code"):
            self.locked = True
        last_render = 0.0
        try:
            while True:
                frame_start = time.time()
                raw = self.poll_touch_raw()

                if self.sleeping:
                    # any touch wakes the display; swallow that touch
                    if raw:
                        self.wake()
                        self._last_activity = time.time()
                        last_render = 0.0
                    self.render()
                    time.sleep(self.IDLE_POLL_INTERVAL)
                    continue

                was_down = self._last_touch_state
                now_down = bool(raw)
                touch_edge = now_down != was_down

                if now_down and not was_down:
                    self._last_activity = time.time()
                    sound.click()
                    if self.locked:
                        self._lock_on_tap(*raw)
                    elif self.current_app:
                        self.current_app.on_tap(*raw)
                elif now_down and was_down:
                    self._last_activity = time.time()
                    if not self.locked and self.current_app:
                        self.current_app.on_touch_move(*raw)
                elif was_down and not now_down:
                    if not self.locked and self.current_app:
                        self.current_app.on_touch_up()

                self._last_touch_state = now_down

                # auto-sleep after N idle seconds (0 = disabled), a
                # battery-life feature configurable in Settings
                timeout = theme.get("sleep_timeout")
                if timeout and time.time() - self._last_activity > timeout:
                    self.enter_sleep(theme.get("brightness"))
                    last_render = 0.0
                    continue

                animating = bool(self.current_app and
                                 getattr(self.current_app, "wants_animation", False))
                active = now_down or touch_edge or animating

                now = time.time()
                if active or (now - last_render) >= self.IDLE_REDRAW_INTERVAL:
                    self.render()
                    last_render = now

                if active:
                    elapsed = time.time() - frame_start
                    time.sleep(max(0.0, self.ACTIVE_FRAME_INTERVAL - elapsed))
                else:
                    # cheap poll while nothing's happening -- still
                    # responsive (next touch-down is felt within ~50ms)
                    # without paying render/SPI cost for frames no one
                    # asked for
                    time.sleep(self.IDLE_POLL_INTERVAL)
        except KeyboardInterrupt:
            pass
        finally:
            self.lcd.close()
