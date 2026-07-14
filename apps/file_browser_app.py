"""
File Browser -- navigate the filesystem with a drag-to-scroll list (see
ScrollArea in ui/framework.py) instead of fixed pages, plus an "Up" button.

Tapping a file selects it and shows an action bar (Open / Copy / Move /
Delete). Copy and Move stash the path in a small clipboard; navigate to
the destination folder and a "Paste" button appears. Opening a file
routes it to the right app: images go to Gallery, ".phoneapp" packages
go through the same single-file install path as the App Store, and
everything else opens in the Text Editor.
"""

import os
import shutil
from ui.framework import App, Button, ScrollArea, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, CARD_COLOR, ACCENT
from apps.gallery_app import IMAGE_EXTS
from apps.app_store_app import _import_app_class, _load_registry, _save_registry, INSTALL_DIR

START_DIR = os.path.expanduser("~")
ROW_H = 44

LIST_TOP = STATUS_BAR_H + 44
LIST_BOTTOM = SCREEN_H - 106  # leaves room for the Up/Home row (+ Paste row)


def _human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}TB"


def _unique_dest(dest):
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


class FileBrowserApp(App):
    name = "FileBrowser"
    icon = "\U0001F4C2"

    def on_open(self):
        self.path = START_DIR
        self.mode = "browse"          # browse | selected | confirm_delete
        self.selected_name = None
        self.clipboard = None          # {"path": ..., "mode": "copy"/"move"}
        self.action_status = None
        self._press_row = None
        self._press_start = None
        self.scroll = ScrollArea(0, LIST_TOP, SCREEN_W, LIST_BOTTOM - LIST_TOP)
        self._load_dir()

    def _load_dir(self):
        entries = []
        try:
            for name in sorted(os.listdir(self.path)):
                full = os.path.join(self.path, name)
                is_dir = os.path.isdir(full)
                size = 0 if is_dir else (os.path.getsize(full) if os.path.exists(full) else 0)
                entries.append((name, is_dir, size))
            entries.sort(key=lambda e: (not e[1], e[0].lower()))
            self.error = None
        except Exception as e:
            entries = []
            self.error = str(e)
        self.entries = entries
        self.scroll.offset = 0
        self.scroll.set_content_height(len(entries) * ROW_H)
        self._build_buttons()

    def _build_buttons(self):
        if self.mode == "selected":
            self._build_action_buttons()
            return
        if self.mode == "confirm_delete":
            self._build_confirm_buttons()
            return

        self.buttons = [
            Button(10, LIST_BOTTOM + 12, 70, 36, "Up", self._go_up, font=FONT_SM),
            Button(SCREEN_W - 100, LIST_BOTTOM + 12, 90, 36, "Home", self.os.go_home, font=FONT_SM),
        ]
        if self.clipboard:
            name = os.path.basename(self.clipboard["path"])
            verb = "Paste (move)" if self.clipboard["mode"] == "move" else "Paste (copy)"
            self.buttons.append(Button(10, LIST_BOTTOM + 54, 200, 36, f"{verb}: {name[:14]}",
                                        self._paste, font=FONT_SM))
            self.buttons.append(Button(220, LIST_BOTTOM + 54, 90, 36, "Cancel",
                                        self._cancel_clipboard, font=FONT_SM))

    # -- scroll list dispatch (browse mode only) -----------------------------
    def on_tap(self, x, y):
        if self.mode != "browse":
            return super().on_tap(x, y)

        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True

        self._press_row = None
        self._press_start = (x, y)
        if self.scroll.contains(x, y):
            self.scroll.begin_drag(y)
            content_y = (y - self.scroll.y) + self.scroll.offset
            idx = int(content_y // ROW_H)
            if 0 <= idx < len(self.entries):
                self._press_row = idx
        return True

    def on_touch_move(self, x, y):
        if self.mode != "browse" or self._press_start is None:
            return
        self.scroll.drag_to(y)

    def on_touch_up(self):
        if self.mode != "browse":
            return
        self.scroll.end_drag()
        if not self.scroll.was_drag() and self._press_row is not None:
            self._activate_entry(self._press_row)
        self._press_row = None
        self._press_start = None

    def _activate_entry(self, idx):
        name, is_dir, size = self.entries[idx]
        if is_dir:
            self.path = os.path.join(self.path, name)
            self._load_dir()
        else:
            self.selected_name = name
            self.mode = "selected"
            self.action_status = None
            self._build_buttons()

    def _go_up(self):
        parent = os.path.dirname(self.path.rstrip("/"))
        if parent:
            self.path = parent
            self._load_dir()

    # -- selected-file action bar --------------------------------------------
    def _full_selected_path(self):
        return os.path.join(self.path, self.selected_name)

    def _build_action_buttons(self):
        self.buttons = []
        top = STATUS_BAR_H + 120
        row_h = 44
        gap = 8
        actions = [
            ("Open", self._open_selected),
            ("Copy", self._copy_selected),
            ("Move", self._move_selected),
            ("Delete", self._confirm_delete),
        ]
        for i, (label, handler) in enumerate(actions):
            y = top + i * (row_h + gap)
            self.buttons.append(Button(30, y, SCREEN_W - 60, row_h, label, handler, font=FONT_MD))
        cancel_y = top + len(actions) * (row_h + gap) + 10
        self.buttons.append(Button(SCREEN_W // 2 - 70, cancel_y, 140, 40, "Cancel",
                                    self._deselect, font=FONT_SM))

    def _deselect(self):
        self.mode = "browse"
        self.selected_name = None
        self._build_buttons()

    def _open_selected(self):
        path = self._full_selected_path()
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTS:
            self.os.launch_arg = path
            self.os.open_app("Gallery")
        elif ext == ".pdf":
            self.os.launch_arg = path
            self.os.open_app("PDF Viewer")
        elif ext == ".phoneapp":
            self._install_phoneapp(path)
        else:
            self.os.launch_arg = path
            self.os.open_app("TextEditor")

    def _install_phoneapp(self, path):
        try:
            os.makedirs(INSTALL_DIR, exist_ok=True)
            base = os.path.splitext(os.path.basename(path))[0] + ".py"
            dest = os.path.join(INSTALL_DIR, base)
            shutil.copy2(path, dest)
            cls = _import_app_class(dest)
            self.os.register_app(cls)

            registry = [e for e in _load_registry() if e.get("file") != base]
            registry.append({"file": base, "class_name": cls.__name__, "app_name": cls.name})
            _save_registry(registry)

            self.mode = "browse"
            self.action_status = f"Installed {cls.name} - find it on Home"
            self._build_buttons()
        except Exception as e:
            self.action_status = f"Install failed: {e}"
            self._build_action_buttons()

    def _copy_selected(self):
        self.clipboard = {"path": self._full_selected_path(), "mode": "copy"}
        self.mode = "browse"
        self._build_buttons()

    def _move_selected(self):
        self.clipboard = {"path": self._full_selected_path(), "mode": "move"}
        self.mode = "browse"
        self._build_buttons()

    def _cancel_clipboard(self):
        self.clipboard = None
        self._build_buttons()

    def _paste(self):
        src = self.clipboard["path"]
        dest = _unique_dest(os.path.join(self.path, os.path.basename(src)))
        try:
            if self.clipboard["mode"] == "copy":
                if os.path.isdir(src):
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
                self.action_status = f"Copied {os.path.basename(dest)}"
            else:
                shutil.move(src, dest)
                self.action_status = f"Moved {os.path.basename(dest)}"
                self.clipboard = None
        except Exception as e:
            self.action_status = f"Paste failed: {e}"
        self._load_dir()

    # -- delete with confirmation --------------------------------------------
    def _confirm_delete(self):
        self.mode = "confirm_delete"
        self._build_buttons()

    def _build_confirm_buttons(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 130, SCREEN_H // 2 + 10, 120, 46, "Delete",
                   self._do_delete, font=FONT_MD, bg=(180, 60, 60)),
            Button(SCREEN_W // 2 + 10, SCREEN_H // 2 + 10, 120, 46, "Cancel",
                   self._deselect, font=FONT_MD),
        ]

    def _do_delete(self):
        path = self._full_selected_path()
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            self.action_status = f"Deleted {self.selected_name}"
        except Exception as e:
            self.action_status = f"Delete failed: {e}"
        self.mode = "browse"
        self.selected_name = None
        self._load_dir()

    # -- drawing --------------------------------------------------------------
    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 14
        display_path = self.path
        if len(display_path) > 34:
            display_path = "..." + display_path[-31:]
        draw.text((SCREEN_W // 2, top), display_path, font=FONT_SM,
                   fill=(210, 210, 220), anchor="mm")

        if self.mode == "confirm_delete":
            draw.text((SCREEN_W // 2, SCREEN_H // 2 - 40),
                       f"Delete \"{self.selected_name}\"?", font=FONT_MD,
                       fill=(230, 90, 90), anchor="mm", align="center")
            for b in self.buttons:
                b.draw(draw)
            return

        if self.mode == "selected":
            draw.text((SCREEN_W // 2, top + 30), self.selected_name, font=FONT_MD,
                       fill=ACCENT, anchor="mm")
            if self.action_status:
                draw.text((SCREEN_W // 2, top + 54), self.action_status, font=FONT_SM,
                           fill=(150, 220, 150), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            return

        if self.action_status:
            draw.text((SCREEN_W // 2, top + 22), self.action_status, font=FONT_SM,
                       fill=(150, 220, 150), anchor="mm")

        if self.error:
            draw.text((SCREEN_W // 2, LIST_TOP + 100), f"Can't open:\n{self.error}",
                       font=FONT_SM, fill=(230, 90, 90), anchor="mm", align="center")
        elif not self.entries:
            draw.text((SCREEN_W // 2, LIST_TOP + 100), "Empty folder",
                       font=FONT_SM, fill=(150, 150, 160), anchor="mm")
        else:
            for i, (name, is_dir, size) in enumerate(self.entries):
                ry = i * ROW_H
                sy = self.scroll.y + (ry - self.scroll.offset)
                if sy + ROW_H < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                    continue
                label = name if is_dir else f"{name} ({_human_size(size)})"
                icon = "\U0001F4C1 " if is_dir else "\U0001F4C4 "
                draw.rounded_rectangle([16, sy, SCREEN_W - 16, sy + ROW_H - 6], radius=10,
                                        fill=CARD_COLOR)
                draw.text((28, sy + (ROW_H - 6) // 2), icon + label, font=FONT_SM,
                           fill=(230, 230, 235), anchor="lm")
            self.scroll.draw_scrollbar(draw, ACCENT)

        for b in self.buttons:
            b.draw(draw)
