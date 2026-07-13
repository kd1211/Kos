"""
Home -- the launcher. Quality-of-life additions over the old single-grid
Home screen:

  Pages     -- apps are grouped into pages of icons; swipe left/right to
               switch. Layout (which app is on which page, in what order)
               is persisted to ~/.pios_home_layout.json.
  Wallpaper -- an optional background (gradient or a photo from Pictures),
               picked in Settings > Wallpaper, rendered behind the icons.
  Moving    -- tap "Edit" to enter edit mode, then drag an icon to
               reorder it, or drag it to the left/right screen edge to
               carry it onto the adjacent page (dragging off the last
               page's right edge creates a new page for it).
  App info  -- in edit mode, tapping (not dragging) an icon opens a small
               sheet with Open / Uninstall (for anything installed via
               the App Store or a .phoneapp file) / Cancel.

A single on_tap already fires on finger-down, before we know if this is
a tap, a drag-to-reorder, or a page swipe -- so all three are decided at
on_touch_up based on how far the finger moved, exactly like the general
ScrollArea pattern used elsewhere in the OS.
"""

import os
import json
import math

from ui import theme
from ui.wallpaper import get_wallpaper
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_SM, FONT_MD
from apps.app_store_app import _load_registry, _save_registry, INSTALL_DIR

LAYOUT_PATH = os.path.expanduser("~/.pios_home_layout.json")
ICONS_PER_PAGE = 9      # only used to size the *initial* auto layout
COLS = 3
CONTENT_TOP = STATUS_BAR_H + 46
CONTENT_BOTTOM = SCREEN_H - 74
SWIPE_THRESHOLD = 36
DRAG_THRESHOLD = 14
EDGE_ZONE = 26


def _load_layout():
    try:
        with open(LAYOUT_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            return [list(p) for p in data if isinstance(p, list)]
    except Exception:
        pass
    return None


def _save_layout(pages):
    try:
        with open(LAYOUT_PATH, "w") as f:
            json.dump(pages, f)
    except Exception:
        pass


class Home(App):
    name = "Home"
    icon = "\u2302"

    def on_open(self):
        self.edit_mode = False
        self.page = 0
        self._press_name = None
        self._press_start = None
        self._last_dx = 0
        self._dragging = None
        self._drag_pos = None
        self._info_app = None
        self._sync_layout()
        self._rebuild()

    # -- layout persistence -------------------------------------------------
    def _all_home_names(self):
        return [n for n in self.os.apps
                if n != "Home" and n not in self.os.folder_members]

    def _sync_layout(self):
        saved = _load_layout()
        all_names = self._all_home_names()
        if saved is None:
            saved = [all_names[i:i + ICONS_PER_PAGE]
                     for i in range(0, len(all_names), ICONS_PER_PAGE)] or [[]]
        else:
            known = {n for page in saved for n in page}
            saved = [[n for n in page if n in all_names] for page in saved]
            saved = [p for p in saved if p] or [[]]
            for n in all_names:
                if n not in known:
                    if saved and len(saved[-1]) < ICONS_PER_PAGE:
                        saved[-1].append(n)
                    else:
                        saved.append([n])
        self.pages = saved
        self.page = min(self.page, len(self.pages) - 1)
        _save_layout(self.pages)

    # -- chrome + icon layout ------------------------------------------------
    def _rebuild(self):
        self.buttons = [
            Button(SCREEN_W - 92, SCREEN_H - 46, 78, 36,
                   "Done" if self.edit_mode else "Edit", self._toggle_edit, font=FONT_SM),
        ]
        self._layout_icons()

    def _toggle_edit(self):
        self.edit_mode = not self.edit_mode
        self._info_app = None
        self._rebuild()

    def _layout_icons(self):
        names = self.pages[self.page] if self.pages else []
        cols = COLS
        rows = max(1, math.ceil(max(1, len(names)) / cols))
        margin = 14
        avail_w = SCREEN_W - margin * (cols + 1)
        avail_h = CONTENT_BOTTOM - CONTENT_TOP - margin * (rows + 1)
        cell = max(60, min(avail_w // cols, avail_h // rows))
        grid_w = cell * cols + margin * (cols - 1)
        x0 = (SCREEN_W - grid_w) // 2
        self._icon_rects = []
        for i, name in enumerate(names):
            r, c = divmod(i, cols)
            x = x0 + c * (cell + margin)
            y = CONTENT_TOP + r * (cell + margin)
            self._icon_rects.append((x, y, cell, cell, name))

    # -- touch handling -------------------------------------------------------
    def on_tap(self, x, y):
        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True

        if self._info_app is not None:
            return True  # modal sheet: swallow taps on the backdrop

        for (rx, ry, rw, rh, name) in self._icon_rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self._press_name = name
                self._press_start = (x, y)
                self._last_dx = 0
                return True

        self._press_name = None
        self._press_start = (x, y)
        self._last_dx = 0
        return False

    def on_touch_move(self, x, y):
        if self._info_app is not None or self._press_start is None:
            return
        sx, sy = self._press_start
        dx, dy = x - sx, y - sy

        if self.edit_mode:
            if self._press_name is not None:
                if self._dragging is None and (abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD):
                    self._dragging = self._press_name
                if self._dragging is not None:
                    self._drag_pos = (x, y)
            return

        self._last_dx = dx
        if abs(dx) > DRAG_THRESHOLD:
            self._press_name = None  # this has become a swipe, not a tap

    def on_touch_up(self):
        if self._info_app is not None:
            self._press_start = None
            return

        if self.edit_mode:
            if self._dragging is not None and self._drag_pos is not None:
                self._drop_dragged_icon(*self._drag_pos)
            elif self._press_name is not None:
                self._open_info_sheet(self._press_name)
            self._dragging = None
            self._drag_pos = None
            self._press_name = None
            self._press_start = None
            return

        if self._press_name is not None:
            self.os.open_app(self._press_name)
        elif self._press_start is not None and abs(self._last_dx) > SWIPE_THRESHOLD:
            if self._last_dx < 0 and self.page < len(self.pages) - 1:
                self.page += 1
            elif self._last_dx > 0 and self.page > 0:
                self.page -= 1
            self._layout_icons()

        self._press_name = None
        self._press_start = None
        self._last_dx = 0

    # -- drag-to-reorder / drag-to-adjacent-page -----------------------------
    def _drop_dragged_icon(self, x, y):
        name = self._dragging
        cur_list = self.pages[self.page]
        if name in cur_list:
            cur_list.remove(name)

        if x < EDGE_ZONE and self.page > 0:
            self.page -= 1
            self.pages[self.page].append(name)
        elif x > SCREEN_W - EDGE_ZONE:
            if self.page == len(self.pages) - 1:
                self.pages.append([])
            self.page += 1
            self.pages[self.page].append(name)
        else:
            idx = len(cur_list)
            best = None
            for i, (rx, ry, rw, rh, nm) in enumerate(self._icon_rects):
                if nm == name:
                    continue
                cx, cy = rx + rw / 2, ry + rh / 2
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best is None or d < best:
                    best, idx = d, i
            cur_list.insert(min(idx, len(cur_list)), name)

        self.pages = [p for p in self.pages if p] or [[]]
        self.page = min(self.page, len(self.pages) - 1)
        _save_layout(self.pages)
        self._layout_icons()

    # -- per-app info sheet ---------------------------------------------------
    def _open_info_sheet(self, name):
        self._info_app = name
        is_installed = any(e.get("app_name") == name for e in _load_registry())
        y = SCREEN_H // 2 - 40
        buttons = [Button(SCREEN_W // 2 - 110, y, 220, 44, "Open", self._info_open, font=FONT_MD)]
        if is_installed:
            buttons.append(Button(SCREEN_W // 2 - 110, y + 54, 220, 44, "Uninstall",
                                   self._info_uninstall, font=FONT_MD, bg=(150, 60, 60)))
            cancel_y = y + 108
        else:
            cancel_y = y + 54
        buttons.append(Button(SCREEN_W // 2 - 110, cancel_y, 220, 40, "Cancel",
                               self._close_info, font=FONT_SM))
        self.buttons = buttons

    def _info_open(self):
        name = self._info_app
        self._close_info()
        self.os.open_app(name)

    def _info_uninstall(self):
        name = self._info_app
        registry = _load_registry()
        entry = next((e for e in registry if e.get("app_name") == name), None)
        if entry:
            try:
                filepath = os.path.join(INSTALL_DIR, entry.get("file"))
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            _save_registry([e for e in registry if e is not entry])
        if name in self.os.apps:
            del self.os.apps[name]
        self.os.folder_members.discard(name)
        self._info_app = None
        self._sync_layout()
        self._rebuild()

    def _close_info(self):
        self._info_app = None
        self._rebuild()

    # -- drawing --------------------------------------------------------------
    def draw(self, draw, canvas):
        wallpaper = get_wallpaper(SCREEN_W, SCREEN_H - STATUS_BAR_H)
        if wallpaper is not None:
            canvas.paste(wallpaper, (0, STATUS_BAR_H))
        else:
            draw.rectangle([0, STATUS_BAR_H, SCREEN_W, SCREEN_H], fill=theme.bg_color())

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "PiOS", font=FONT_LG,
                   fill=theme.fg_color(), anchor="mm")

        for (rx, ry, rw, rh, name) in self._icon_rects:
            if name == self._dragging:
                continue
            self._draw_icon(draw, rx, ry, rw, rh, name)

        if self._dragging is not None and self._drag_pos is not None:
            dx, dy = self._drag_pos
            size = 70
            self._draw_icon(draw, dx - size // 2, dy - size // 2, size, size,
                             self._dragging, lifted=True)

        if len(self.pages) > 1:
            self._draw_page_dots(draw)

        if self._info_app is not None:
            self._draw_info_sheet(draw)

        for b in self.buttons:
            b.draw(draw)

    def _draw_icon(self, draw, x, y, w, h, name, lifted=False):
        app = self.os.apps.get(name)
        if app is None:
            return
        if lifted:
            draw.rounded_rectangle([x - 4, y - 4, x + w + 4, y + h + 4], radius=16,
                                    fill=theme.accent_color())
        draw.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=theme.card_color())
        draw.text((x + w // 2, y + h // 2 - 12), app.icon, font=FONT_LG,
                   fill=theme.fg_color(), anchor="mm")
        label = name if len(name) <= 10 else name[:9] + "\u2026"
        draw.text((x + w // 2, y + h - 14), label, font=FONT_SM,
                   fill=theme.fg_color(), anchor="mm")
        if self.edit_mode and not lifted:
            bx, by = x + w - 10, y + 6
            draw.ellipse([bx - 8, by - 8, bx + 8, by + 8], fill=(230, 90, 90))
            draw.text((bx, by), "\u2212", font=FONT_SM, fill=(255, 255, 255), anchor="mm")

    def _draw_page_dots(self, draw):
        n = len(self.pages)
        gap = 16
        x0 = SCREEN_W // 2 - (n - 1) * gap // 2
        y = SCREEN_H - 58
        for i in range(n):
            x = x0 + i * gap
            color = theme.accent_color() if i == self.page else theme.card_color()
            draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=color)

    def _draw_info_sheet(self, draw):
        draw.rounded_rectangle([20, SCREEN_H // 2 - 90, SCREEN_W - 20, SCREEN_H // 2 + 170],
                                radius=16, fill=theme.card_color())
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 70), self._info_app, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
