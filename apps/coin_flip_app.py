import random
from ui import sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_XL, FONT_MD, FONT_LG, CARD_COLOR, ACCENT


class CoinFlipApp(App):
    name = "Coin Flip"
    icon = "\U0001FA99"

    def on_open(self):
        self.result = None
        self.buttons = [
            Button(SCREEN_W // 2 - 80, STATUS_BAR_H + 200, 160, 52,
                   "Flip", self._flip, font=FONT_MD),
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD),
        ]

    def _flip(self):
        self.result = random.choice(["Heads", "Tails"])
        sound.beep(520 if self.result == "Heads" else 780, 100)

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 20
        draw.text((SCREEN_W // 2, top), "Coin Flip", font=FONT_MD,
                   fill=(180, 180, 190), anchor="mm")

        box_top = top + 40
        draw.rounded_rectangle([40, box_top, SCREEN_W - 40, box_top + 140],
                                radius=16, fill=CARD_COLOR)

        if self.result is None:
            draw.text((SCREEN_W // 2, box_top + 70), "\U0001FA99", font=FONT_LG,
                       fill=(140, 140, 150), anchor="mm")
        else:
            draw.text((SCREEN_W // 2, box_top + 60), self.result, font=FONT_XL,
                       fill=ACCENT, anchor="mm")
            icon = "\U0001F451" if self.result == "Heads" else "\U0001F343"
            draw.text((SCREEN_W // 2, box_top + 110), icon, font=FONT_MD,
                       fill=(200, 200, 210), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
