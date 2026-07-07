import random
from ui import sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_XL, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

DICE_FACES = ["\u2680", "\u2681", "\u2682", "\u2683", "\u2684", "\u2685"]


class DiceApp(App):
    name = "Dice"
    icon = "\U0001F3B2"

    def on_open(self):
        self.value = None
        self.sides = 6
        self.buttons = [
            Button(SCREEN_W // 2 - 80, STATUS_BAR_H + 200, 160, 52,
                   "Roll", self._roll, font=FONT_MD),
            Button(SCREEN_W // 2 - 110, STATUS_BAR_H + 268, 100, 40,
                   "D6", self._set_sides(6), font=FONT_SM),
            Button(SCREEN_W // 2 + 10, STATUS_BAR_H + 268, 100, 40,
                   "D20", self._set_sides(20), font=FONT_SM),
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD),
        ]

    def _set_sides(self, n):
        def handler():
            self.sides = n
            self.value = None
        return handler

    def _roll(self):
        self.value = random.randint(1, self.sides)
        sound.beep(660, 80)

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 20
        draw.text((SCREEN_W // 2, top), f"D{self.sides}", font=FONT_MD,
                   fill=(180, 180, 190), anchor="mm")

        box_top = top + 36
        draw.rounded_rectangle([40, box_top, SCREEN_W - 40, box_top + 140],
                                radius=16, fill=CARD_COLOR)

        if self.value is None:
            draw.text((SCREEN_W // 2, box_top + 70), "Tap Roll", font=FONT_MD,
                       fill=(140, 140, 150), anchor="mm")
        elif self.sides == 6:
            face = DICE_FACES[self.value - 1]
            draw.text((SCREEN_W // 2, box_top + 70), face, font=FONT_XL,
                       fill=ACCENT, anchor="mm")
        else:
            draw.text((SCREEN_W // 2, box_top + 70), str(self.value), font=FONT_XL,
                       fill=ACCENT, anchor="mm")

        for b in self.buttons:
            b.draw(draw)
