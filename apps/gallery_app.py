"""
Gallery -- thumbnail grid + fullscreen viewer for images, backed by Pillow.

Looks at ~/Pictures by default (created if missing). Paint's "Save" button
writes PNGs there, and File Browser opens any image file straight into
the fullscreen viewer here.
"""

import os
from PIL import Image

from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, CARD_COLOR

PICTURES_DIR = os.path.expanduser("~/Pictures")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif")

THUMB = 92
GRID_COLS = 3
GRID_GAP = 8


def is_image(path):
    return path.lower().endswith(IMAGE_EXTS)


class GalleryApp(App):
    name = "Gallery"
    icon = "\U0001F5BC"

    def on_open(self):
        os.makedirs(PICTURES_DIR, exist_ok=True)
        # A one-off "open this specific file" launch, e.g. from File Browser:
        # `os.launch_arg` is set right before `open_app("Gallery")`.
        launch_path = getattr(self.os, "launch_arg", None)
        self.os.launch_arg = None

        self.mode = "grid"
        self.page = 0
        self.viewer_image = None
        self.status = None
        self._load_files()

        if launch_path and os.path.exists(launch_path):
            self._open_viewer_path(launch_path)
        else:
            self._build_grid_buttons()

    def _load_files(self):
        try:
            names = sorted(f for f in os.listdir(PICTURES_DIR) if is_image(f))
        except Exception:
            names = []
        self.files = names

    def _thumbs_per_page(self):
        rows = max(1, (SCREEN_H - STATUS_BAR_H - 100) // (THUMB + GRID_GAP))
        return rows * GRID_COLS

    def _build_grid_buttons(self):
        self.buttons = []
        per_page = self._thumbs_per_page()
        start = self.page * per_page
        page_files = self.files[start:start + per_page]
        top = STATUS_BAR_H + 46
        for i, fname in enumerate(page_files):
            row, col = divmod(i, GRID_COLS)
            x = 10 + col * (THUMB + GRID_GAP)
            y = top + row * (THUMB + GRID_GAP)
            self.buttons.append(
                Button(x, y, THUMB, THUMB, "", self._open_viewer(fname)))
        footer_y = SCREEN_H - 56
        self.buttons.append(Button(16, footer_y, 70, 40, "Prev", self._prev_page, font=FONT_SM))
        self.buttons.append(Button(94, footer_y, 70, 40, "Next", self._next_page, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 106, footer_y, 90, 40, "Home",
                                    self.os.go_home, font=FONT_SM))
        self._per_page = per_page

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._build_grid_buttons()

    def _next_page(self):
        if (self.page + 1) * self._per_page < len(self.files):
            self.page += 1
            self._build_grid_buttons()

    def _open_viewer(self, fname):
        def handler():
            self._open_viewer_path(os.path.join(PICTURES_DIR, fname))
        return handler

    def _open_viewer_path(self, path):
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((SCREEN_W, SCREEN_H - STATUS_BAR_H - 60))
            self.viewer_image = img
            self.viewer_name = os.path.basename(path)
            self.status = None
        except Exception as e:
            self.viewer_image = None
            self.status = f"Can't open image: {e}"
        self.mode = "viewer"
        self.buttons = [
            Button(16, SCREEN_H - 56, 100, 40, "Back", self._back_to_grid, font=FONT_SM),
            Button(SCREEN_W - 116, SCREEN_H - 56, 100, 40, "Home", self.os.go_home, font=FONT_SM),
        ]

    def _back_to_grid(self):
        self.mode = "grid"
        self._load_files()
        self._build_grid_buttons()

    def draw(self, draw, canvas):
        if self.mode == "viewer":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 16),
                       getattr(self, "viewer_name", ""), font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            if self.viewer_image:
                img = self.viewer_image
                x = (SCREEN_W - img.width) // 2
                y = STATUS_BAR_H + 36
                canvas.paste(img, (x, y))
            elif self.status:
                draw.text((SCREEN_W // 2, SCREEN_H // 2), self.status,
                           font=FONT_SM, fill=(230, 90, 90), anchor="mm", align="center")
            for b in self.buttons:
                b.draw(draw)
            return

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 22), "Gallery", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")
        if not self.files:
            draw.text((SCREEN_W // 2, SCREEN_H // 2), "No pictures yet\n(Paint saves here)",
                       font=FONT_SM, fill=(150, 150, 160), anchor="mm", align="center")

        per_page = getattr(self, "_per_page", self._thumbs_per_page())
        start = self.page * per_page
        page_files = self.files[start:start + per_page]
        for btn, fname in zip(self.buttons, page_files):
            try:
                thumb = Image.open(os.path.join(PICTURES_DIR, fname)).convert("RGB")
                thumb.thumbnail((THUMB, THUMB))
                tx = btn.x + (THUMB - thumb.width) // 2
                ty = btn.y + (THUMB - thumb.height) // 2
                draw.rectangle([btn.x, btn.y, btn.x + THUMB, btn.y + THUMB], fill=CARD_COLOR)
                canvas.paste(thumb, (tx, ty))
            except Exception:
                draw.rectangle([btn.x, btn.y, btn.x + THUMB, btn.y + THUMB], fill=CARD_COLOR)
                draw.text((btn.x + THUMB // 2, btn.y + THUMB // 2), "?", font=FONT_SM,
                           fill=(150, 150, 160), anchor="mm")

        for b in self.buttons[len(page_files):]:
            b.draw(draw)

        total_pages = max(1, (len(self.files) + per_page - 1) // per_page)
        draw.text((SCREEN_W // 2, SCREEN_H - 12), f"Page {self.page + 1}/{total_pages}",
                   font=FONT_SM, fill=(140, 140, 150), anchor="mm")
