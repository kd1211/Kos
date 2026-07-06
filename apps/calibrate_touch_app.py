"""
Calibrate Touch -- classic 3-point calibration wizard.

Shows a crosshair target in three corners (top-left, top-right,
bottom-left -- the third point can't be collinear with the other two, so
diagonal corners are used the same way resistive-touchscreen calibration
routines have always done it). Whatever pixel the driver reports for
each tap is recorded, and the resulting affine correction (independent
scale + offset per axis) is saved to Settings so every app benefits
immediately, via PhoneOS.poll_touch_raw().
"""

from ui import theme
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, ACCENT

MARGIN = 40
TARGETS = [
    (MARGIN, STATUS_BAR_H + MARGIN),
    (SCREEN_W - MARGIN, STATUS_BAR_H + MARGIN),
    (MARGIN, SCREEN_H - MARGIN),
]
CROSS_R = 14


class CalibrateTouchApp(App):
    name = "Calibrate Touch"
    icon = "\U0001F3AF"

    def on_open(self):
        self.step = 0
        self.samples = []
        self.done_status = None
        self.buttons = [
            Button(SCREEN_W // 2 - 90, SCREEN_H - 56, 180, 42,
                   "Cancel", self.os.go_home, font=FONT_SM),
        ]

    def on_tap(self, x, y):
        # let Cancel/Reset buttons take priority over recording a sample
        for b in self.buttons:
            if b.contains(x, y):
                return super().on_tap(x, y)

        if self.step < len(TARGETS):
            self.samples.append((x, y))
            self.step += 1
            if self.step == len(TARGETS):
                self._finish()
            return True
        return super().on_tap(x, y)

    def _finish(self):
        # Solve independent linear fits x_true = ax*x_raw + bx (and same
        # for y) from the two points per axis with the most separation,
        # i.e. targets 0->1 for X and 0->2 for Y.
        (x0r, y0r), (x1r, _), (_, y2r) = self.samples
        x0t, x1t = TARGETS[0][0], TARGETS[1][0]
        y0t, y2t = TARGETS[0][1], TARGETS[2][1]

        try:
            ax = (x1t - x0t) / (x1r - x0r)
            bx = x0t - ax * x0r
            ay = (y2t - y0t) / (y2r - y0r)
            by = y0t - ay * y0r
            theme.set("touch_cal", {"ax": ax, "bx": bx, "ay": ay, "by": by})
            self.done_status = "Calibration saved!"
        except ZeroDivisionError:
            self.done_status = "Taps were too close together -- try again"
            self.step = 0
            self.samples = []
            return

        self.buttons = [
            Button(SCREEN_W // 2 - 100, SCREEN_H - 130, 200, 42,
                   "Reset to factory", self._reset, font=FONT_SM),
            Button(SCREEN_W // 2 - 90, SCREEN_H - 56, 180, 42,
                   "Done", self.os.go_home, font=FONT_SM),
        ]

    def _reset(self):
        theme.set("touch_cal", None)
        self.step = 0
        self.samples = []
        self.done_status = None
        self.buttons = [
            Button(SCREEN_W // 2 - 90, SCREEN_H - 56, 180, 42,
                   "Cancel", self.os.go_home, font=FONT_SM),
        ]

    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "Calibrate Touch",
                   font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        if self.step < len(TARGETS):
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 200),
                       f"Tap the target ({self.step + 1}/{len(TARGETS)})",
                       font=FONT_MD, fill=(200, 200, 210), anchor="mm")
            tx, ty = TARGETS[self.step]
            draw.line([tx - CROSS_R, ty, tx + CROSS_R, ty], fill=ACCENT, width=3)
            draw.line([tx, ty - CROSS_R, tx, ty + CROSS_R], fill=ACCENT, width=3)
            draw.ellipse([tx - CROSS_R, ty - CROSS_R, tx + CROSS_R, ty + CROSS_R],
                         outline=ACCENT, width=2)
        elif self.done_status:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 200), self.done_status,
                       font=FONT_MD, fill=ACCENT, anchor="mm", align="center")

        for b in self.buttons:
            b.draw(draw)
