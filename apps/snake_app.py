import random
import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

GRID_W, GRID_H = 16, 18
BOARD_TOP = STATUS_BAR_H + 40
CELL = min((SCREEN_W - 20) // GRID_W, (SCREEN_H - BOARD_TOP - 120) // GRID_H)
BOARD_X = (SCREEN_W - CELL * GRID_W) // 2
STEP_SECONDS = 0.18
DPAD_Y = BOARD_TOP + CELL * GRID_H + 14


class SnakeApp(App):
    name = "Snake"
    icon = "\U0001F40D"

    def on_open(self):
        self.snake = [(GRID_W // 2, GRID_H // 2)]
        self.direction = (1, 0)
        self.pending_dir = (1, 0)
        self.food = self._new_food()
        self.score = 0
        self.game_over = False
        self.last_step = time.time()

        dpad_w = 56
        cx = SCREEN_W // 2
        self.buttons = [
            Button(cx - dpad_w // 2, DPAD_Y, dpad_w, 40, "\u2191", self._set_dir(0, -1), font=FONT_LG),
            Button(cx - dpad_w // 2, DPAD_Y + 44, dpad_w, 40, "\u2193", self._set_dir(0, 1), font=FONT_LG),
            Button(cx - dpad_w - 8, DPAD_Y + 22, dpad_w, 40, "\u2190", self._set_dir(-1, 0), font=FONT_LG),
            Button(cx + 8, DPAD_Y + 22, dpad_w, 40, "\u2192", self._set_dir(1, 0), font=FONT_LG),
            Button(16, SCREEN_H - 44, 90, 34, "Restart", self.on_open, font=FONT_SM),
            Button(SCREEN_W - 106, SCREEN_H - 44, 90, 34, "Home", self.os.go_home, font=FONT_SM),
        ]

    def _new_food(self):
        while True:
            cell = (random.randrange(GRID_W), random.randrange(GRID_H))
            if cell not in self.snake:
                return cell

    def _set_dir(self, dx, dy):
        def handler():
            # disallow reversing straight into yourself
            if (dx, dy) != (-self.direction[0], -self.direction[1]):
                self.pending_dir = (dx, dy)
        return handler

    def _step(self):
        if self.game_over:
            return
        self.direction = self.pending_dir
        hx, hy = self.snake[0]
        dx, dy = self.direction
        new_head = ((hx + dx) % GRID_W, (hy + dy) % GRID_H)

        if new_head in self.snake:
            self.game_over = True
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 1
            self.food = self._new_food()
        else:
            self.snake.pop()

    def draw(self, draw, canvas):
        now = time.time()
        if now - self.last_step >= STEP_SECONDS:
            self._step()
            self.last_step = now

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 18), f"Snake  Score: {self.score}",
                   font=FONT_MD, fill=(255, 255, 255), anchor="mm")

        board_bottom = BOARD_TOP + CELL * GRID_H
        draw.rectangle([BOARD_X, BOARD_TOP, BOARD_X + CELL * GRID_W, board_bottom],
                       fill=CARD_COLOR)

        fx, fy = self.food
        draw.rectangle([BOARD_X + fx * CELL, BOARD_TOP + fy * CELL,
                         BOARD_X + (fx + 1) * CELL, BOARD_TOP + (fy + 1) * CELL],
                       fill=(230, 90, 90))

        for i, (sx, sy) in enumerate(self.snake):
            color = ACCENT if i == 0 else (min(ACCENT[0] + 20, 255), ACCENT[1], ACCENT[2])
            draw.rectangle([BOARD_X + sx * CELL + 1, BOARD_TOP + sy * CELL + 1,
                             BOARD_X + (sx + 1) * CELL - 1, BOARD_TOP + (sy + 1) * CELL - 1],
                           fill=color)

        if self.game_over:
            draw.text((SCREEN_W // 2, BOARD_TOP + CELL * GRID_H // 2), "Game Over",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
