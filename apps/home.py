"""
Home -- the launcher, with folders that work the way people expect from a
phone: drag one icon onto another to create a folder, drag an app onto an
existing folder to add it, tap a folder to open it as an overlay, drag a
member out of that overlay to remove it (back onto the current page), tap
the folder's name to rename it, and a folder that's down to one member (or
zero) automatically dissolves back into a plain icon (or disappears).

Other QoL carried over from before:
  Pages     -- apps/folders are grouped into pages; swipe left/right.
  Wallpaper -- an optional background, picked in Settings > Wallpaper.
  Moving    -- tap "Edit" to enter edit mode, then drag to reorder, or
               drag to the left/right screen edge to carry an icon onto
               the adjacent page (or a new one, off the last page).
  App info  -- in edit mode, tapping (not dragging) a plain app icon
               opens Open / Uninstall / Cancel. Folders always just open
               their overlay -- they're managed from inside it instead.

Everything is decided at on_touch_up based on how far the finger moved
during the gesture (tap vs. drag vs. swipe vs. drag-onto-another-icon),
the same pattern used by ScrollArea elsewhere in the OS.
"""

import os
import json
import math

from ui import theme
from ui.wallpaper import get_wallpaper
from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
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

FOLDER_PANEL_TOP = 110
FOLDER_PANEL_BOTTOM = SCREEN_H - 100
PANEL_LEFT, PANEL_RIGHT = 20, SCREEN_W - 20
PANEL_TOP, PANEL_BOTTOM = FOLDER_PANEL_TOP - 20, FOLDER_PANEL_BOTTOM

# Used only the very first time Home ever runs (no saved layout yet), to
# preserve the app's previous default grouping. After that, folders are
# entirely user-editable -- rename, add, remove, dissolve, whatever.
DEFAULT_FOLDERS = [
    {"type": "folder", "name": "Games", "icon": "\U0001F3AE",
     "members": ["TicTacToe", "Memory", "Reaction", "RetroArch", "Snake", "2048", "Breakout", "Raycrawl"]},
    {"type": "folder", "name": "Tools", "icon": "\U0001F4C1",
     "members": ["Calculator", "Notes", "TextEditor", "FileBrowser", "Calendar",
                 "Weather", "Browser", "System", "Terminal", "Gallery", "Camera", "Messages",
                 "System Updater", "Calibrate Touch"]},
]


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
        self._press_item = None
        self._press_start = None
        self._last_dx = 0
        self._dragging = None
        self._drag_pos = None
        self._info_app = None
        self._info_return_to_folder = False
        self._open_folder = None
        self._folder_press_item = None
        self._folder_press_start = None
        self._folder_dragging = None
        self._folder_drag_pos = None
        self._renaming_folder = False
        self._rename_draft = ""
        self._rename_keyboard = None
        self._sync_layout()
        self._rebuild()

    # -- layout persistence -------------------------------------------------
    def _all_home_names(self):
        return [n for n in self.os.apps if n != "Home"]

    def _append_item(self, pages, item):
        if pages and len(pages[-1]) < ICONS_PER_PAGE:
            pages[-1].append(item)
        else:
            pages.append([item])

    def _known_names(self, pages):
        known = set()
        for page in pages:
            for item in page:
                if isinstance(item, dict):
                    known.update(item.get("members", []))
                else:
                    known.add(item)
        return known

    def _sync_layout(self):
        saved = _load_layout()
        all_names = self._all_home_names()
        all_set = set(all_names)

        if saved is None:
            pages = [[]]
            used = set()
            for folder in DEFAULT_FOLDERS:
                members = [n for n in folder["members"] if n in all_set]
                if not members:
                    continue
                used.update(members)
                self._append_item(pages, {"type": "folder", "name": folder["name"],
                                           "icon": folder["icon"], "members": members})
            for n in all_names:
                if n not in used:
                    self._append_item(pages, n)
            saved = pages
        else:
            cleaned = []
            for page in saved:
                new_page = []
                for item in page:
                    if isinstance(item, dict):
                        members = [n for n in item.get("members", []) if n in all_set]
                        if len(members) >= 2:
                            new_page.append(dict(item, members=members))
                        elif len(members) == 1:
                            new_page.append(members[0])
                        # else: folder emptied out entirely -- drop it
                    elif item in all_set:
                        new_page.append(item)
                cleaned.append(new_page)
            cleaned = [p for p in cleaned if p] or [[]]

            known = self._known_names(cleaned)
            for n in all_names:
                if n not in known:
                    self._append_item(cleaned, n)
            saved = cleaned

        self.pages = saved
        self.page = min(self.page, len(self.pages) - 1)
        _save_layout(self.pages)

    def _save_and_relayout(self):
        self.pages = [p for p in self.pages if p] or [[]]
        self.page = min(self.page, len(self.pages) - 1)
        _save_layout(self.pages)
        self._layout_icons()

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
        items = self.pages[self.page] if self.pages else []
        cols = COLS
        rows = max(1, math.ceil(max(1, len(items)) / cols))
        margin = 14
        avail_w = SCREEN_W - margin * (cols + 1)
        avail_h = CONTENT_BOTTOM - CONTENT_TOP - margin * (rows + 1)
        cell = max(60, min(avail_w // cols, avail_h // rows))
        grid_w = cell * cols + margin * (cols - 1)
        x0 = (SCREEN_W - grid_w) // 2
        self._icon_rects = []
        for i, item in enumerate(items):
            r, c = divmod(i, cols)
            x = x0 + c * (cell + margin)
            y = CONTENT_TOP + r * (cell + margin)
            self._icon_rects.append((x, y, cell, cell, item))

    # -- top-level touch handling --------------------------------------------
    def on_tap(self, x, y):
        if self._renaming_folder:
            return self._rename_on_tap(x, y)

        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True

        if self._info_app is not None:
            return True  # modal sheet: swallow taps on the backdrop

        if self._open_folder is not None:
            return self._folder_on_tap(x, y)

        for (rx, ry, rw, rh, item) in self._icon_rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self._press_item = item
                self._press_start = (x, y)
                self._last_dx = 0
                return True

        self._press_item = None
        self._press_start = (x, y)
        self._last_dx = 0
        return False

    def on_touch_move(self, x, y):
        if self._renaming_folder or self._info_app is not None:
            return
        if self._open_folder is not None:
            self._folder_touch_move(x, y)
            return
        if self._press_start is None:
            return
        sx, sy = self._press_start
        dx, dy = x - sx, y - sy

        if self.edit_mode:
            if self._press_item is not None:
                if self._dragging is None and (abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD):
                    self._dragging = self._press_item
                if self._dragging is not None:
                    self._drag_pos = (x, y)
            return

        self._last_dx = dx
        if abs(dx) > DRAG_THRESHOLD:
            self._press_item = None  # this has become a swipe, not a tap

    def on_touch_up(self):
        if self._renaming_folder:
            return
        if self._info_app is not None:
            self._press_start = None
            return
        if self._open_folder is not None:
            self._folder_touch_up()
            return

        if self.edit_mode:
            if self._dragging is not None and self._drag_pos is not None:
                self._drop_dragged_icon(*self._drag_pos)
            elif self._press_item is not None:
                if isinstance(self._press_item, dict):
                    self._open_folder_view(self._press_item)
                else:
                    self._open_info_sheet(self._press_item)
            self._dragging = None
            self._drag_pos = None
            self._press_item = None
            self._press_start = None
            return

        if self._press_item is not None:
            if isinstance(self._press_item, dict):
                self._open_folder_view(self._press_item)
            else:
                self.os.open_app(self._press_item)
        elif self._press_start is not None and abs(self._last_dx) > SWIPE_THRESHOLD:
            if self._last_dx < 0 and self.page < len(self.pages) - 1:
                self.page += 1
            elif self._last_dx > 0 and self.page > 0:
                self.page -= 1
            self._layout_icons()

        self._press_item = None
        self._press_start = None
        self._last_dx = 0

    # -- drag-to-reorder / drag-to-adjacent-page / drag-to-merge -------------
    def _drop_dragged_icon(self, x, y):
        item = self._dragging
        cur_list = self.pages[self.page]
        idx = next((i for i, it in enumerate(cur_list) if it is item), None)
        if idx is not None:
            cur_list.pop(idx)

        if x < EDGE_ZONE and self.page > 0:
            self.page -= 1
            self.pages[self.page].append(item)
            self._save_and_relayout()
            return
        if x > SCREEN_W - EDGE_ZONE:
            if self.page == len(self.pages) - 1:
                self.pages.append([])
            self.page += 1
            self.pages[self.page].append(item)
            self._save_and_relayout()
            return

        # dropped directly on top of another icon? merge into a folder, or
        # add to one that already exists there -- same gesture as a phone
        target = None
        for (rx, ry, rw, rh, other) in self._icon_rects:
            if other is item:
                continue
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                target = other
                break

        if target is not None and isinstance(item, str):
            if isinstance(target, dict):
                if item not in target["members"]:
                    target["members"].append(item)
                self._save_and_relayout()
                return
            elif isinstance(target, str):
                new_folder = {"type": "folder", "name": "New Folder",
                              "icon": "\U0001F4C1", "members": [target, item]}
                tidx = next((i for i, it in enumerate(cur_list) if it is target), None)
                if tidx is not None:
                    cur_list[tidx] = new_folder
                else:
                    cur_list.append(new_folder)
                self._save_and_relayout()
                self._open_folder_view(new_folder)
                self._start_rename()
                return

        # plain reorder within the current page
        idx2 = len(cur_list)
        best = None
        for i, (rx, ry, rw, rh, other) in enumerate(self._icon_rects):
            if other is item:
                continue
            cx, cy = rx + rw / 2, ry + rh / 2
            d = (cx - x) ** 2 + (cy - y) ** 2
            if best is None or d < best:
                best, idx2 = d, i
        cur_list.insert(min(idx2, len(cur_list)), item)
        self._save_and_relayout()

    # -- per-app info sheet (Open / Uninstall / Cancel) ----------------------
    def _open_info_sheet(self, name):
        self._info_app = name
        self._info_return_to_folder = self._open_folder is not None
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
        self._info_app = None
        self._open_folder = None
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
        self._info_app = None
        self._open_folder = None
        self._sync_layout()
        self._rebuild()

    def _close_info(self):
        self._info_app = None
        if self._info_return_to_folder and self._open_folder is not None:
            self.buttons = [Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 40,
                                    "Close", self._close_folder, font=FONT_SM)]
        else:
            self._rebuild()

    # -- folder overlay -------------------------------------------------------
    def _open_folder_view(self, folder_item):
        self._open_folder = folder_item
        self._layout_folder_icons()
        self.buttons = [Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 40,
                                "Close", self._close_folder, font=FONT_SM)]

    def _close_folder(self):
        self._open_folder = None
        self._folder_dragging = None
        self._folder_drag_pos = None
        self._renaming_folder = False
        self._rebuild()

    def _layout_folder_icons(self):
        members = self._open_folder["members"] if self._open_folder else []
        cols = 3
        rows = max(1, math.ceil(max(1, len(members)) / cols))
        margin = 14
        avail_w = (PANEL_RIGHT - PANEL_LEFT) - margin * (cols + 1)
        avail_h = (FOLDER_PANEL_BOTTOM - 50) - (FOLDER_PANEL_TOP + 40) - margin * (rows + 1)
        cell = max(56, min(avail_w // cols, avail_h // rows))
        grid_w = cell * cols + margin * (cols - 1)
        x0 = (SCREEN_W - grid_w) // 2
        y0 = FOLDER_PANEL_TOP + 46
        self._folder_icon_rects = []
        for i, name in enumerate(members):
            r, c = divmod(i, cols)
            x = x0 + c * (cell + margin)
            y = y0 + r * (cell + margin)
            self._folder_icon_rects.append((x, y, cell, cell, name))

    def _folder_name_hit(self, x, y):
        return FOLDER_PANEL_TOP <= y <= FOLDER_PANEL_TOP + 36 and 40 <= x <= SCREEN_W - 40

    def _folder_on_tap(self, x, y):
        if self._folder_name_hit(x, y):
            self._start_rename()
            return True
        for (rx, ry, rw, rh, name) in self._folder_icon_rects:
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                self._folder_press_item = name
                self._folder_press_start = (x, y)
                return True
        self._folder_press_item = None
        self._folder_press_start = (x, y)
        return True

    def _folder_touch_move(self, x, y):
        if not self.edit_mode or self._folder_press_item is None or self._folder_press_start is None:
            return
        sx, sy = self._folder_press_start
        dx, dy = x - sx, y - sy
        if self._folder_dragging is None and (abs(dx) > DRAG_THRESHOLD or abs(dy) > DRAG_THRESHOLD):
            self._folder_dragging = self._folder_press_item
        if self._folder_dragging is not None:
            self._folder_drag_pos = (x, y)

    def _folder_touch_up(self):
        if self.edit_mode and self._folder_dragging is not None and self._folder_drag_pos is not None:
            self._drop_dragged_folder_member(*self._folder_drag_pos)
        elif self.edit_mode and self._folder_press_item is not None:
            self._open_info_sheet(self._folder_press_item)
        elif not self.edit_mode and self._folder_press_item is not None:
            name = self._folder_press_item
            self._close_folder()
            self.os.open_app(name)
        self._folder_press_item = None
        self._folder_press_start = None
        self._folder_dragging = None
        self._folder_drag_pos = None

    def _drop_dragged_folder_member(self, x, y):
        folder = self._open_folder
        name = self._folder_dragging
        members = folder["members"]
        idx = next((i for i, m in enumerate(members) if m == name), None)
        if idx is not None:
            members.pop(idx)

        inside_panel = (PANEL_LEFT <= x <= PANEL_RIGHT and PANEL_TOP <= y <= PANEL_BOTTOM)
        if inside_panel:
            best, insert_idx = None, len(members)
            for i, (rx, ry, rw, rh, nm) in enumerate(self._folder_icon_rects):
                if nm == name:
                    continue
                cx, cy = rx + rw / 2, ry + rh / 2
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best is None or d < best:
                    best, insert_idx = d, i
            members.insert(min(insert_idx, len(members)), name)
            _save_layout(self.pages)
            self._layout_folder_icons()
        else:
            self._insert_into_current_page(name, x, y)
            self._dissolve_if_needed(folder)
            _save_layout(self.pages)
            self._close_folder()

    def _dissolve_if_needed(self, folder):
        if len(folder["members"]) > 1:
            return
        page_list = self.pages[self.page]
        idx = next((i for i, it in enumerate(page_list) if it is folder), None)
        if idx is None:
            return
        if len(folder["members"]) == 1:
            page_list[idx] = folder["members"][0]
        else:
            page_list.pop(idx)

    def _insert_into_current_page(self, name, x, y):
        page_list = self.pages[self.page]
        idx = len(page_list)
        best = None
        for i, (rx, ry, rw, rh, item) in enumerate(self._icon_rects):
            cx, cy = rx + rw / 2, ry + rh / 2
            d = (cx - x) ** 2 + (cy - y) ** 2
            if best is None or d < best:
                best, idx = d, i
        page_list.insert(min(idx, len(page_list)), name)

    # -- folder rename --------------------------------------------------------
    def _start_rename(self):
        self._renaming_folder = True
        self._rename_draft = self._open_folder.get("name", "")
        self._rename_keyboard = Keyboard(4, SCREEN_H - 190, SCREEN_W - 8, 184)
        self.buttons = [
            Button(16, SCREEN_H - 210, 90, 34, "Cancel", self._cancel_rename, font=FONT_SM),
            Button(SCREEN_W - 106, SCREEN_H - 210, 90, 34, "Save", self._save_rename, font=FONT_SM),
        ]

    def _rename_on_tap(self, x, y):
        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True
        if self._rename_keyboard.on_tap(x, y, self._rename_on_key):
            return True
        return True

    def _rename_on_key(self, val):
        if val == "BACKSPACE":
            self._rename_draft = self._rename_draft[:-1]
        elif val == "ENTER":
            self._save_rename()
        elif len(self._rename_draft) < 18:
            self._rename_draft += val

    def _cancel_rename(self):
        self._renaming_folder = False
        self.buttons = [Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 40,
                                "Close", self._close_folder, font=FONT_SM)]

    def _save_rename(self):
        name = self._rename_draft.strip() or "Folder"
        self._open_folder["name"] = name
        _save_layout(self.pages)
        self._renaming_folder = False
        self.buttons = [Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 40,
                                "Close", self._close_folder, font=FONT_SM)]

    # -- drawing --------------------------------------------------------------
    def draw(self, draw, canvas):
        wallpaper = get_wallpaper(SCREEN_W, SCREEN_H - STATUS_BAR_H)
        if wallpaper is not None:
            canvas.paste(wallpaper, (0, STATUS_BAR_H))
        else:
            draw.rectangle([0, STATUS_BAR_H, SCREEN_W, SCREEN_H], fill=theme.bg_color())

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "PiOS", font=FONT_LG,
                   fill=theme.fg_color(), anchor="mm")

        for (rx, ry, rw, rh, item) in self._icon_rects:
            if item is self._dragging:
                continue
            self._draw_icon(draw, rx, ry, rw, rh, item)

        if self._dragging is not None and self._drag_pos is not None:
            dx, dy = self._drag_pos
            size = 70
            self._draw_icon(draw, dx - size // 2, dy - size // 2, size, size,
                             self._dragging, lifted=True)

        if len(self.pages) > 1:
            self._draw_page_dots(draw)

        if self._open_folder is not None:
            self._draw_folder_overlay(draw)

        if self._info_app is not None:
            self._draw_info_sheet(draw)

        if self._renaming_folder:
            self._draw_rename_overlay(draw)

        for b in self.buttons:
            b.draw(draw)

    def _draw_icon(self, draw, x, y, w, h, item, lifted=False):
        if lifted:
            draw.rounded_rectangle([x - 4, y - 4, x + w + 4, y + h + 4], radius=16,
                                    fill=theme.accent_color())
        draw.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=theme.card_color())

        if isinstance(item, dict):
            self._draw_folder_glyph(draw, x, y, w, h, item)
            label = item.get("name", "Folder")
        else:
            app = self.os.apps.get(item)
            if app is None:
                return
            draw.text((x + w // 2, y + h // 2 - 12), app.icon, font=FONT_LG,
                       fill=theme.fg_color(), anchor="mm")
            label = item

        if len(label) > 10:
            label = label[:9] + "\u2026"
        draw.text((x + w // 2, y + h - 14), label, font=FONT_SM,
                   fill=theme.fg_color(), anchor="mm")

        if self.edit_mode and not lifted:
            bx, by = x + w - 10, y + 6
            draw.ellipse([bx - 8, by - 8, bx + 8, by + 8], fill=(230, 90, 90))
            draw.text((bx, by), "\u2212", font=FONT_SM, fill=(255, 255, 255), anchor="mm")

    def _draw_folder_glyph(self, draw, x, y, w, h, item):
        members = item.get("members", [])[:4]
        pad = int(w * 0.16)
        inner = w - pad * 2
        cell = inner // 2
        gap = max(2, int(cell * 0.12))
        for i in range(4):
            r, c = divmod(i, 2)
            cx = x + pad + c * (cell + gap)
            cy = y + pad + r * (cell + gap) - 6
            if i < len(members):
                app = self.os.apps.get(members[i])
                glyph = app.icon if app else "?"
                draw.text((cx + cell // 2, cy + cell // 2), glyph, font=FONT_SM,
                           fill=theme.fg_color(), anchor="mm")

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

    def _draw_folder_overlay(self, draw):
        folder = self._open_folder
        draw.rounded_rectangle([PANEL_LEFT, PANEL_TOP, PANEL_RIGHT, PANEL_BOTTOM],
                                radius=18, fill=theme.card_color())
        name = folder.get("name", "Folder")
        draw.text((SCREEN_W // 2, FOLDER_PANEL_TOP), name, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        if self.edit_mode:
            draw.text((SCREEN_W // 2, FOLDER_PANEL_TOP + 20), "tap name to rename",
                       font=FONT_SM, fill=(150, 150, 160), anchor="mm")

        for (rx, ry, rw, rh, mname) in self._folder_icon_rects:
            if mname == self._folder_dragging:
                continue
            self._draw_member_icon(draw, rx, ry, rw, rh, mname)

        if self._folder_dragging is not None and self._folder_drag_pos is not None:
            dx, dy = self._folder_drag_pos
            size = 60
            self._draw_member_icon(draw, dx - size // 2, dy - size // 2, size, size,
                                    self._folder_dragging, lifted=True)

    def _draw_member_icon(self, draw, x, y, w, h, name, lifted=False):
        app = self.os.apps.get(name)
        if app is None:
            return
        if lifted:
            draw.rounded_rectangle([x - 4, y - 4, x + w + 4, y + h + 4], radius=14,
                                    fill=theme.accent_color())
        draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=theme.bg_color())
        draw.text((x + w // 2, y + h // 2 - 10), app.icon, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        label = name if len(name) <= 9 else name[:8] + "\u2026"
        draw.text((x + w // 2, y + h - 10), label, font=FONT_SM,
                   fill=theme.fg_color(), anchor="mm")

    def _draw_rename_overlay(self, draw):
        draw.rounded_rectangle([30, SCREEN_H // 2 - 70, SCREEN_W - 30, SCREEN_H // 2 + 10],
                                radius=16, fill=theme.card_color())
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 50), "Rename Folder", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        draw.rounded_rectangle([46, SCREEN_H // 2 - 20, SCREEN_W - 46, SCREEN_H // 2 + 16],
                                radius=8, fill=theme.bg_color())
        draw.text((56, SCREEN_H // 2 - 2), self._rename_draft or "Folder name", font=FONT_SM,
                   fill=theme.fg_color(), anchor="lm")
        self._rename_keyboard.draw(draw)
