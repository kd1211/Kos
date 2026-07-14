"""
Text Editor -- opens and edits arbitrary plain-text files (as opposed to
Notes, which is a fixed quick-notes scratchpad). File Browser launches
this for any file it doesn't recognize as an image, by setting
`os.launch_arg` to the file's path right before opening this app.
"""

import os
import textwrap

from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, \
    STATUS_BAR_H, FONT_SM, FONT_MD, CARD_COLOR, FG_COLOR, ACCENT

KEYBOARD_H = 188
CHARS_PER_LINE = 40
VISIBLE_LINES = 9
MAX_LEN = 4000


class TextEditorApp(App):
    name = "TextEditor"
    icon = "\U0001F4C4"

    def on_open(self):
        launch_path = getattr(self.os, "launch_arg", None)
        self.os.launch_arg = None

        self.path = launch_path
        self.content = ""
        self.status = None
        self.mode = "edit"
        if launch_path and os.path.exists(launch_path):
            try:
                with open(launch_path, "r", errors="replace") as f:
                    self.content = f.read()[:MAX_LEN]
            except Exception as e:
                self.status = f"Couldn't open: {e}"

        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self._build_buttons()

    def _build_buttons(self):
        top = STATUS_BAR_H + 4
        self.buttons = [
            Button(10, top, 70, 30, "Save", self._save, font=FONT_SM),
            Button(86, top, 90, 30, "Save As", self._save_as, font=FONT_SM),
            Button(SCREEN_W - 96, top, 80, 30, "Home", self.os.go_home, font=FONT_SM),
        ]

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.content = self.content[:-1]
        elif val == "ENTER":
            self.content += "\n"
        elif len(self.content) < MAX_LEN:
            self.content += val

    def on_tap(self, x, y):
        handler = self._saveas_key if getattr(self, "mode", "edit") == "saveas" else self._on_key
        if self.keyboard.on_tap(x, y, handler):
            return True
        return super().on_tap(x, y)

    def _save(self):
        if not self.path:
            self._save_as()
            return
        try:
            with open(self.path, "w") as f:
                f.write(self.content)
            self.status = f"Saved {os.path.basename(self.path)}"
        except Exception as e:
            self.status = f"Save failed: {e}"

    def _save_as(self):
        self._saveas_draft = os.path.basename(self.path) if self.path else "note.txt"
        self._prev_buttons = self.buttons
        self.mode = "saveas"
        self.buttons = [
            Button(16, STATUS_BAR_H + 92, 90, 34, "Cancel", self._cancel_saveas, font=FONT_SM),
            Button(SCREEN_W - 106, STATUS_BAR_H + 92, 90, 34, "Save", self._confirm_saveas, font=FONT_SM),
        ]

    def _cancel_saveas(self):
        self.mode = "edit"
        self.buttons = self._prev_buttons

    def _confirm_saveas(self):
        name = self._saveas_draft.strip() or "note.txt"
        base_dir = os.path.dirname(self.path) if self.path else os.path.expanduser("~")
        self.path = os.path.join(base_dir, name)
        self.mode = "edit"
        self.buttons = self._prev_buttons
        self._save()

    def _saveas_key(self, val):
        if val == "BACKSPACE":
            self._saveas_draft = self._saveas_draft[:-1]
        elif val == "ENTER":
            self._confirm_saveas()
        elif len(self._saveas_draft) < 60:
            self._saveas_draft += val

    def draw(self, draw, canvas):
        mode = getattr(self, "mode", "edit")

        if mode == "saveas":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 18), "Save As", font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            draw.rounded_rectangle([16, STATUS_BAR_H + 38, SCREEN_W - 16, STATUS_BAR_H + 78],
                                    radius=10, fill=CARD_COLOR)
            draw.text((24, STATUS_BAR_H + 58), self._saveas_draft, font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            for b in self.buttons:
                b.draw(draw)
            self.keyboard.draw(draw)
            return

        for b in self.buttons:
            b.draw(draw)

        title = os.path.basename(self.path) if self.path else "Untitled"
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 46), title, font=FONT_SM,
                   fill=(180, 180, 190), anchor="mm")

        wrapped = []
        for line in self.content.splitlines() or [""]:
            wrapped.extend(textwrap.wrap(line, CHARS_PER_LINE) or [""])
        visible = wrapped[-VISIBLE_LINES:]

        text_top = STATUS_BAR_H + 62
        text_bottom = self.keyboard.y - 10
        draw.rounded_rectangle([8, text_top, SCREEN_W - 8, text_bottom], radius=8, fill=CARD_COLOR)
        y = text_top + 8
        for line in visible:
            draw.text((14, y), line, font=FONT_SM, fill=FG_COLOR, anchor="lm")
            y += 20

        if self.status:
            draw.text((SCREEN_W // 2, text_bottom - 12), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm")

        self.keyboard.draw(draw)
