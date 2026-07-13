"""
Downloads -- a scoped view of ~/Downloads (the same folder Messages
already saves incoming files into), so received files have a proper
home screen instead of only being reachable by browsing there in File
Browser. Opens files the same way File Browser does: images to
Gallery, PDFs to PDF Viewer, .phoneapp to the installer, everything
else to Text Editor.
"""

import os
import shutil
from ui.framework import App, Button, ScrollArea, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, CARD_COLOR, ACCENT
from apps.gallery_app import IMAGE_EXTS
from apps.app_store_app import _import_app_class, _load_registry, _save_registry, INSTALL_DIR

DOWNLOADS_DIR = os.path.expanduser("~/Downloads")
LIST_TOP = STATUS_BAR_H + 44
LIST_BOTTOM = SCREEN_H - 60
ROW_H = 48


def _human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}TB"


class DownloadsApp(App):
    name = "Downloads"
    icon = "\U0001F4E5"

    def on_open(self):
        self.status = None
        self.scroll = ScrollArea(0, LIST_TOP, SCREEN_W, LIST_BOTTOM - LIST_TOP)
        self._press_row = None
        self._press_start = None
        self._load()
        self.buttons = [
            Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 36, "Home",
                   self.os.go_home, font=FONT_SM)
        ]

    def _load(self):
        try:
            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            names = sorted(os.listdir(DOWNLOADS_DIR),
                           key=lambda n: os.path.getmtime(os.path.join(DOWNLOADS_DIR, n)),
                           reverse=True)
        except Exception:
            names = []
        self.files = names
        self.scroll.offset = 0
        self.scroll.set_content_height(len(names) * ROW_H)

    def on_tap(self, x, y):
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
            if 0 <= idx < len(self.files):
                if x > SCREEN_W - 56:
                    self._press_row = ("delete", self.files[idx])
                else:
                    self._press_row = ("open", self.files[idx])
        return True

    def on_touch_move(self, x, y):
        if self._press_start is None:
            return
        self.scroll.drag_to(y)

    def on_touch_up(self):
        self.scroll.end_drag()
        if not self.scroll.was_drag() and self._press_row is not None:
            kind, name = self._press_row
            if kind == "delete":
                self._delete(name)
            else:
                self._open(name)
        self._press_row = None
        self._press_start = None

    def _delete(self, name):
        try:
            os.remove(os.path.join(DOWNLOADS_DIR, name))
            self.status = f"Deleted {name}"
        except Exception as e:
            self.status = f"Couldn't delete: {e}"
        self._load()

    def _open(self, name):
        path = os.path.join(DOWNLOADS_DIR, name)
        ext = os.path.splitext(name)[1].lower()
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
            self.status = f"Installed {cls.name} - find it on Home"
        except Exception as e:
            self.status = f"Install failed: {e}"

    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "Downloads", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")
        if self.status:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 38), self.status, font=FONT_SM,
                       fill=(150, 220, 150), anchor="mm")

        if not self.files:
            draw.text((SCREEN_W // 2, LIST_TOP + 100), "No downloads yet", font=FONT_SM,
                       fill=(150, 150, 160), anchor="mm")
        else:
            for i, name in enumerate(self.files):
                ry = i * ROW_H
                sy = self.scroll.y + (ry - self.scroll.offset)
                if sy + ROW_H < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                    continue
                path = os.path.join(DOWNLOADS_DIR, name)
                try:
                    size = _human_size(os.path.getsize(path))
                except Exception:
                    size = "?"
                draw.rounded_rectangle([16, sy, SCREEN_W - 16, sy + ROW_H - 8], radius=10,
                                        fill=CARD_COLOR)
                label = name if len(name) <= 26 else name[:25] + "\u2026"
                draw.text((28, sy + 12), label, font=FONT_SM, fill=(230, 230, 235), anchor="lm")
                draw.text((28, sy + 30), size, font=FONT_SM, fill=(150, 150, 160), anchor="lm")
                draw.text((SCREEN_W - 34, sy + (ROW_H - 8) // 2), "\U0001F5D1", font=FONT_SM,
                           fill=(230, 130, 130), anchor="mm")
            self.scroll.draw_scrollbar(draw, ACCENT)

        for b in self.buttons:
            b.draw(draw)
