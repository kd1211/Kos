import os
from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_MD, FONT_SM, CARD_COLOR, ACCENT, FG_COLOR

NOTES_FILE = os.path.expanduser("~/.pios_notes.txt")

QUICK_PHRASES = ["Milk", "Call mom", "Water plants", "Pay bills",
                 "Meeting 3pm", "Backup files"]

KEYBOARD_H = 188
MAX_DRAFT_LEN = 80


class NotesApp(App):
    name = "Notes"
    icon = "\U0001F4DD"

    def on_open(self):
        self.notes = self._load()
        self.mode = "list"
        self.draft = ""
        self.keyboard = None
        self._build_list_buttons()

    # -- list mode ------------------------------------------------------
    def _build_list_buttons(self):
        self.buttons = []
        top = STATUS_BAR_H + 90
        for i, phrase in enumerate(QUICK_PHRASES):
            row, col = divmod(i, 2)
            x = 16 + col * ((SCREEN_W - 48) // 2 + 16)
            y = top + row * 46
            self.buttons.append(
                Button(x, y, (SCREEN_W - 48) // 2, 38, phrase,
                       self._add(phrase), font=FONT_SM))
        self.buttons.append(
            Button(16, SCREEN_H - 108, (SCREEN_W - 48) // 2, 40,
                   "Type note...", self._start_typing, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2, SCREEN_H - 108, (SCREEN_W - 48) // 2, 40,
                   "Clear", self._clear, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2 - 60, SCREEN_H - 58, 120, 42,
                   "Home", self.os.go_home, font=FONT_SM))

    # -- typing mode ------------------------------------------------------
    def _start_typing(self):
        self.mode = "type"
        self.draft = ""
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self.buttons = [
            Button(16, STATUS_BAR_H + 92, 90, 34, "Cancel", self._cancel_typing, font=FONT_SM),
            Button(SCREEN_W - 106, STATUS_BAR_H + 92, 90, 34, "Save", self._save_draft, font=FONT_SM),
        ]

    def _cancel_typing(self):
        self.mode = "list"
        self._build_list_buttons()

    def _save_draft(self):
        if self.draft.strip():
            self.notes.append(self.draft.strip())
            self._save()
        self.mode = "list"
        self._build_list_buttons()

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft = self.draft[:-1]
        elif val == "ENTER":
            self._save_draft()
        elif len(self.draft) < MAX_DRAFT_LEN:
            self.draft += val

    def on_tap(self, x, y):
        if self.mode == "type" and self.keyboard.on_tap(x, y, self._on_key):
            return True
        return super().on_tap(x, y)

    # -- storage ------------------------------------------------------
    def _load(self):
        if os.path.exists(NOTES_FILE):
            with open(NOTES_FILE) as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def _save(self):
        with open(NOTES_FILE, "w") as f:
            f.write("\n".join(self.notes[-6:]))

    def _add(self, phrase):
        def handler():
            self.notes.append(phrase)
            self._save()
        return handler

    def _clear(self):
        self.notes = []
        self._save()

    # -- drawing ------------------------------------------------------
    def draw(self, draw, canvas):
        if self.mode == "type":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 18), "New note", font=FONT_MD,
                       fill=(255, 255, 255), anchor="mm")
            draw.rounded_rectangle([16, STATUS_BAR_H + 38, SCREEN_W - 16, STATUS_BAR_H + 78],
                                    radius=10, fill=CARD_COLOR)
            text = self.draft if self.draft else "Type below..."
            color = FG_COLOR if self.draft else (140, 140, 150)
            draw.text((24, STATUS_BAR_H + 58), text, font=FONT_SM, fill=color, anchor="lm")
            for b in self.buttons:
                b.draw(draw)
            self.keyboard.draw(draw)
            return

        top = STATUS_BAR_H + 10
        draw.text((SCREEN_W // 2, top), "Notes", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")

        draw.rectangle([16, top + 16, SCREEN_W - 16, top + 66], fill=CARD_COLOR)
        text = self.notes[-1] if self.notes else "No notes yet - tap a quick note"
        draw.text((24, top + 41), text, font=FONT_SM, fill=ACCENT, anchor="lm")

        for b in self.buttons:
            b.draw(draw)
