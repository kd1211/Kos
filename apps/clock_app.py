import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, FONT_XL, FONT_MD, ACCENT


class ClockApp(App):
    name = "Clock"
    icon = "\u23F0"

    def on_open(self):
        self.wants_animation = True
        self.buttons = [
            Button(SCREEN_W // 2 - 60, SCREEN_H - 70, 120, 45,
                   "Home", self.os.go_home)
        ]

    def draw(self, draw, canvas):
        now = time.localtime()
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 40),
                   time.strftime("%H:%M:%S", now), font=FONT_XL,
                   fill=ACCENT, anchor="mm")
        draw.text((SCREEN_W // 2, SCREEN_H // 2 + 20),
                   time.strftime("%A, %d %B %Y", now), font=FONT_MD,
                   fill=(220, 220, 220), anchor="mm")
        for b in self.buttons:
            b.draw(draw)
