import random
import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, CARD_COLOR, ACCENT

ROUND_TIME = 20
COLS, ROWS = 3, 3


class ReactionApp(App):
    name = "Reaction"
    icon = "\u26A1"

    def on_open(self):
        self.score = 0
        self.active_cell = None
        self.start_time = time.time()
        self.game_over = False
        self.buttons = []

        margin = 14
        top = STATUS_BAR_H + 60
        cell = (SCREEN_W - margin * (COLS + 1)) // COLS
        self.cells = []
        for i in range(COLS * ROWS):
            row, col = divmod(i, COLS)
            x = margin + col * (cell + margin)
            y = top + row * (cell + margin)
            self.cells.append((x, y, cell))
            self.buttons.append(Button(x, y, cell, cell, "", self._hit(i)))

        controls_y = top + ROWS * (cell + margin) + 10
        self.buttons.append(
            Button(SCREEN_W // 2 - 60, controls_y, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD))

        self._new_target()

    def _new_target(self):
        self.active_cell = random.randrange(COLS * ROWS)

    def _hit(self, i):
        def handler():
            if self.game_over:
                return
            if i == self.active_cell:
                self.score += 1
                self._new_target()
        return handler

    def draw(self, draw, canvas):
        elapsed = time.time() - self.start_time
        remaining = max(0, ROUND_TIME - elapsed)
        if remaining <= 0:
            self.game_over = True

        top = STATUS_BAR_H + 16
        if self.game_over:
            draw.text((SCREEN_W // 2, top), f"Time up! Score: {self.score}",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")
        else:
            draw.text((SCREEN_W // 2, top), f"Score {self.score}  |  {int(remaining)}s",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        for i, (x, y, cell) in enumerate(self.cells):
            lit = (not self.game_over) and i == self.active_cell
            color = (240, 200, 60) if lit else CARD_COLOR
            draw.rounded_rectangle([x, y, x + cell, y + cell], radius=12, fill=color)

        for b in self.buttons[-1:]:
            b.draw(draw)
