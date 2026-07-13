"""
PDF Viewer -- rasterizes pages on demand via `pdftoppm`/`pdfinfo`
(poppler-utils, the same command-line tools `pdftotext`/etc. belong
to) rather than a heavy PDF-parsing Python library, since this only
needs to *display* pages, not edit them. Pages are rendered to a temp
PNG the first time you visit them and cached in memory after that, so
flipping back and forth is instant.

File Browser opens this for any `.pdf` file by setting `os.launch_arg`
before opening the app, the same way it already does for images
(Gallery) and everything else (Text Editor).
"""

import os
import shutil
import subprocess
import tempfile
from PIL import Image
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR

PAGE_TOP = STATUS_BAR_H + 40
PAGE_BOTTOM = SCREEN_H - 60


def _have(cmd):
    return shutil.which(cmd) is not None


class PdfViewerApp(App):
    name = "PDF Viewer"
    icon = "\U0001F4D5"

    def on_open(self):
        self.available = _have("pdftoppm") and _have("pdfinfo")
        self.path = getattr(self.os, "launch_arg", None)
        self.os.launch_arg = None
        self.page = 0
        self.page_count = 0
        self.status = None
        self._page_cache = {}
        self._tmpdir = tempfile.mkdtemp(prefix="kos_pdf_")

        if self.available and self.path and os.path.exists(self.path):
            self.page_count = self._get_page_count()
            if self.page_count == 0:
                self.status = "Couldn't read this PDF"
        elif self.available and self.path:
            self.status = "File not found"
        elif self.available:
            self.status = "No PDF file was given"

        self._build_buttons()

    def on_close(self):
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
        except Exception:
            pass

    def _get_page_count(self):
        try:
            r = subprocess.run(["pdfinfo", self.path], capture_output=True,
                                text=True, timeout=10)
            for line in r.stdout.splitlines():
                if line.startswith("Pages:"):
                    return int(line.split(":", 1)[1].strip())
        except Exception:
            pass
        return 0

    def _render_page(self, index):
        if index in self._page_cache:
            return self._page_cache[index]
        out_prefix = os.path.join(self._tmpdir, f"page_{index}")
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-f", str(index + 1), "-l", str(index + 1),
                 "-scale-to-x", str(SCREEN_W), "-scale-to-y", "-1",
                 self.path, out_prefix],
                capture_output=True, timeout=20)
            candidates = [f for f in os.listdir(self._tmpdir)
                          if f.startswith(f"page_{index}")]
            if not candidates:
                return None
            img = Image.open(os.path.join(self._tmpdir, candidates[0])).convert("RGB")
            self._page_cache[index] = img
            return img
        except Exception:
            return None

    def _build_buttons(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 168, SCREEN_H - 46, 80, 36, "Prev",
                   self._prev_page, font=FONT_SM),
            Button(SCREEN_W // 2 - 40, SCREEN_H - 46, 80, 36, "Next",
                   self._next_page, font=FONT_SM),
            Button(SCREEN_W // 2 + 88, SCREEN_H - 46, 80, 36, "Home",
                   self.os.go_home, font=FONT_SM),
        ]

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1

    def _next_page(self):
        if self.page < self.page_count - 1:
            self.page += 1

    def draw(self, draw, canvas):
        if not self.available:
            draw.text((SCREEN_W // 2, SCREEN_H // 2 - 30), "\U0001F4D5", font=FONT_LG,
                       fill=(120, 120, 130), anchor="mm")
            draw.text((SCREEN_W // 2, SCREEN_H // 2 + 10), "Can't view PDFs here",
                       font=FONT_MD, fill=(200, 200, 210), anchor="mm")
            draw.text((SCREEN_W // 2, SCREEN_H // 2 + 34), "poppler-utils isn't installed",
                       font=FONT_SM, fill=(140, 140, 150), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            return

        title = os.path.basename(self.path) if self.path else "PDF Viewer"
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 18), title, font=FONT_SM,
                   fill=(220, 220, 230), anchor="mm")

        if self.status:
            draw.text((SCREEN_W // 2, PAGE_TOP + 100), self.status, font=FONT_SM,
                       fill=(230, 90, 90), anchor="mm")
        elif self.page_count:
            img = self._render_page(self.page)
            if img is not None:
                x = (SCREEN_W - img.width) // 2
                y = PAGE_TOP + max(0, (PAGE_BOTTOM - PAGE_TOP - img.height) // 2)
                draw.rectangle([0, PAGE_TOP, SCREEN_W, PAGE_BOTTOM], fill=CARD_COLOR)
                canvas.paste(img, (x, y))
            else:
                draw.text((SCREEN_W // 2, PAGE_TOP + 100), "Couldn't render this page",
                           font=FONT_SM, fill=(230, 90, 90), anchor="mm")
            draw.text((SCREEN_W // 2, SCREEN_H - 12), f"Page {self.page + 1} / {self.page_count}",
                       font=FONT_SM, fill=(160, 160, 170), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
