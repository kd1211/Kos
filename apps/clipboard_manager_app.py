"""
Clipboard Manager -- browse, reuse, and clear the text clipboard history
(ui/clipboard.py) that Notes, Text Editor, and anything else with a
Copy/Paste button share. There's no OS-level text selection here (the
on-screen Keyboard can't select a range), so this is the closest thing
to a "clipboard" this device has -- a shared history apps opt into
rather than an invisible single-slot buffer.
"""

from ui import clipboard
from ui.framework import App, Button, ScrollArea, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, CARD_COLOR, ACCENT

LIST_TOP = STATUS_BAR_H + 44
LIST_BOTTOM = SCREEN_H - 70
ROW_H = 58


class ClipboardManagerApp(App):
    name = "Clipboard Manager"
    icon = "\U0001F4CB"

    def on_open(self):
        self.status = None
        self.scroll = ScrollArea(0, LIST_TOP, SCREEN_W, LIST_BOTTOM - LIST_TOP)
        self._press_row = None
        self._press_start = None
        self._refresh()
        self.buttons = [
            Button(SCREEN_W // 2 - 100, SCREEN_H - 50, 90, 40, "Clear All",
                   self._clear_all, font=FONT_SM, bg=(150, 60, 60)),
            Button(SCREEN_W // 2 + 10, SCREEN_H - 50, 90, 40, "Home",
                   self.os.go_home, font=FONT_SM),
        ]

    def _refresh(self):
        self.items = clipboard.history()
        self.scroll.offset = 0
        self.scroll.set_content_height(len(self.items) * ROW_H)

    def _clear_all(self):
        clipboard.clear()
        self._refresh()
        self.status = "Cleared"

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
            if 0 <= idx < len(self.items):
                if x > SCREEN_W - 56:
                    self._press_row = ("delete", idx)
                else:
                    self._press_row = ("recopy", idx)
        return True

    def on_touch_move(self, x, y):
        if self._press_start is None:
            return
        self.scroll.drag_to(y)

    def on_touch_up(self):
        self.scroll.end_drag()
        if not self.scroll.was_drag() and self._press_row is not None:
            kind, idx = self._press_row
            if kind == "delete":
                clipboard.remove(idx)
                self._refresh()
            else:
                # move this entry back to the top (it's now the "latest"
                # any app's Paste button will pick up)
                item = self.items[idx]
                clipboard.copy(item["text"], source=item["source"])
                self._refresh()
                self.status = "Moved to top - ready to paste"
        self._press_row = None
        self._press_start = None

    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "Clipboard", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")
        if self.status:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 38), self.status, font=FONT_SM,
                       fill=(150, 220, 150), anchor="mm")

        if not self.items:
            draw.text((SCREEN_W // 2, LIST_TOP + 100), "Clipboard is empty", font=FONT_SM,
                       fill=(150, 150, 160), anchor="mm")
        else:
            for i, item in enumerate(self.items):
                ry = i * ROW_H
                sy = self.scroll.y + (ry - self.scroll.offset)
                if sy + ROW_H < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                    continue
                bg = ACCENT if i == 0 else CARD_COLOR
                draw.rounded_rectangle([16, sy, SCREEN_W - 16, sy + ROW_H - 8], radius=10, fill=bg)
                text = item["text"] if len(item["text"]) <= 36 else item["text"][:35] + "\u2026"
                draw.text((26, sy + 14), text, font=FONT_SM, fill=(255, 255, 255), anchor="lm")
                draw.text((26, sy + 34), item["source"], font=FONT_SM,
                           fill=(230, 230, 240) if i == 0 else (150, 150, 160), anchor="lm")
                draw.text((SCREEN_W - 34, sy + (ROW_H - 8) // 2), "\u2715", font=FONT_SM,
                           fill=(230, 130, 130) if i != 0 else (255, 210, 210), anchor="mm")
            self.scroll.draw_scrollbar(draw, ACCENT)

        for b in self.buttons:
            b.draw(draw)
