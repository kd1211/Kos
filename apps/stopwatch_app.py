import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_XL, FONT_MD, FONT_SM, CARD_COLOR, ACCENT


class StopwatchApp(App):
    name = "Stopwatch"
    icon = "\u23F1"

    def on_open(self):
        self.running = False
        self.elapsed = 0.0
        self._started_at = 0.0
        self.laps = []
        self._build_buttons()

    def _build_buttons(self):
        margin = 12
        top = STATUS_BAR_H + 130
        bw = (SCREEN_W - margin * 4) // 3
        self.buttons = [
            Button(margin, top, bw, 44, "Start", self._toggle, font=FONT_MD),
            Button(margin * 2 + bw, top, bw, 44, "Lap", self._lap, font=FONT_MD),
            Button(margin * 3 + bw * 2, top, bw, 44, "Reset", self._reset, font=FONT_MD),
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD),
        ]

    def _now_elapsed(self):
        if self.running:
            return self.elapsed + (time.time() - self._started_at)
        return self.elapsed

    def _toggle(self):
        if self.running:
            self.elapsed = self._now_elapsed()
            self.running = False
            for b in self.buttons:
                if b.label == "Pause":
                    b.label = "Start"
        else:
            self._started_at = time.time()
            self.running = True
            for b in self.buttons:
                if b.label == "Start":
                    b.label = "Pause"

    def _lap(self):
        if not self.running:
            return
        total = self._now_elapsed()
        self.laps.insert(0, total)
        self.laps = self.laps[:5]

    def _reset(self):
        self.running = False
        self.elapsed = 0.0
        self.laps = []
        for b in self.buttons:
            if b.label == "Pause":
                b.label = "Start"

    @staticmethod
    def _fmt(seconds):
        s = int(seconds)
        ms = int((seconds - s) * 100)
        mins, secs = divmod(s, 60)
        return f"{mins:02d}:{secs:02d}.{ms:02d}"

    def draw(self, draw, canvas):
        total = self._now_elapsed()
        top = STATUS_BAR_H + 16

        draw.text((SCREEN_W // 2, top), "Stopwatch", font=FONT_MD,
                   fill=(180, 180, 190), anchor="mm")
        draw.rounded_rectangle([24, top + 24, SCREEN_W - 24, top + 90],
                                radius=12, fill=CARD_COLOR)
        draw.text((SCREEN_W // 2, top + 57), self._fmt(total), font=FONT_XL,
                   fill=(255, 255, 255), anchor="mm")

        lap_top = STATUS_BAR_H + 188
        if self.laps:
            draw.text((20, lap_top), "Laps", font=FONT_SM, fill=ACCENT, anchor="lm")
            for i, lap in enumerate(self.laps):
                y = lap_top + 22 + i * 22
                draw.text((28, y), f"{len(self.laps) - i}. {self._fmt(lap)}",
                           font=FONT_SM, fill=(200, 200, 210), anchor="lm")

        for b in self.buttons:
            b.draw(draw)
