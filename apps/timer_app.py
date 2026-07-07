import time
from ui import sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_XL, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

PRESETS = [60, 180, 300, 600]


class TimerApp(App):
    name = "Timer"
    icon = "\u23F2"

    def on_open(self):
        self.remaining = 0
        self.running = False
        self.done = False
        self._end_at = 0.0
        self._build_buttons()

    def _build_buttons(self):
        margin = 10
        top = STATUS_BAR_H + 130
        cell = (SCREEN_W - margin * 5) // 4
        self.buttons = []
        labels = ["1m", "3m", "5m", "10m"]
        for i, (secs, label) in enumerate(zip(PRESETS, labels)):
            x = margin + i * (cell + margin)
            self.buttons.append(
                Button(x, top, cell, 40, label, self._set_preset(secs), font=FONT_SM))

        row2 = top + 52
        self.buttons.append(
            Button(margin, row2, (SCREEN_W - margin * 3) // 2, 44,
                   "Start", self._toggle, font=FONT_MD))
        self.buttons.append(
            Button(margin * 2 + (SCREEN_W - margin * 3) // 2, row2,
                   (SCREEN_W - margin * 3) // 2, 44,
                   "Reset", self._reset, font=FONT_MD))
        self.buttons.append(
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD))

    def _set_preset(self, secs):
        def handler():
            if not self.running:
                self.remaining = secs
                self.done = False
        return handler

    def _toggle(self):
        if self.remaining <= 0 and not self.done:
            return
        if self.running:
            self.remaining = max(0, int(self._end_at - time.time()))
            self.running = False
        else:
            if self.done:
                self.done = False
            if self.remaining <= 0:
                self.remaining = 60
            self._end_at = time.time() + self.remaining
            self.running = True
            for b in self.buttons:
                if b.label == "Start":
                    b.label = "Pause"

    def _reset(self):
        self.running = False
        self.remaining = 0
        self.done = False
        for b in self.buttons:
            if b.label == "Pause":
                b.label = "Start"

    def draw(self, draw, canvas):
        if self.running:
            self.remaining = max(0, int(self._end_at - time.time()))
            if self.remaining <= 0:
                self.running = False
                self.done = True
                sound.chime()
                for b in self.buttons:
                    if b.label == "Pause":
                        b.label = "Start"

        mins, secs = divmod(max(0, self.remaining), 60)
        display = f"{mins:02d}:{secs:02d}"

        top = STATUS_BAR_H + 20
        if self.done:
            draw.text((SCREEN_W // 2, top + 30), "Time's up!", font=FONT_MD,
                       fill=ACCENT, anchor="mm")
            color = ACCENT
        else:
            draw.text((SCREEN_W // 2, top + 30), "Timer", font=FONT_MD,
                       fill=(180, 180, 190), anchor="mm")
            color = (255, 255, 255)

        draw.rounded_rectangle([24, top + 52, SCREEN_W - 24, top + 118],
                                radius=12, fill=CARD_COLOR)
        draw.text((SCREEN_W // 2, top + 85), display, font=FONT_XL,
                   fill=color, anchor="mm")

        for b in self.buttons:
            b.draw(draw)
