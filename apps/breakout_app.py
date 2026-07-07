import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

PLAY_TOP = STATUS_BAR_H + 34
PLAY_BOTTOM = SCREEN_H - 60

PADDLE_W, PADDLE_H = 60, 12
PADDLE_Y = PLAY_BOTTOM - 24
BALL_R = 6

BRICK_ROWS, BRICK_COLS = 5, 7
BRICK_MARGIN = 4
BRICK_TOP = PLAY_TOP + 10
BRICK_W = (SCREEN_W - BRICK_MARGIN * (BRICK_COLS + 1)) // BRICK_COLS
BRICK_H = 16
BRICK_COLORS = [(230, 90, 90), (240, 160, 70), (240, 210, 70), (100, 200, 120), (90, 150, 240)]

BALL_SPEED = 4.2


class BreakoutApp(App):
    name = "Breakout"
    icon = "\U0001F532"

    def on_open(self):
        self.paddle_x = SCREEN_W // 2 - PADDLE_W // 2
        self.ball = [SCREEN_W // 2, PADDLE_Y - BALL_R - 2]
        self.vel = [BALL_SPEED * 0.6, -BALL_SPEED]
        self.bricks = {(r, c) for r in range(BRICK_ROWS) for c in range(BRICK_COLS)}
        self.score = 0
        self.lives = 3
        self.game_over = False
        self.won = False
        self.last_tick = time.time()

        self.buttons = [
            Button(16, SCREEN_H - 44, 90, 34, "Restart", self.on_open, font=FONT_SM),
            Button(SCREEN_W - 106, SCREEN_H - 44, 90, 34, "Home", self.os.go_home, font=FONT_SM),
        ]

    def on_touch_move(self, x, y):
        self.paddle_x = max(0, min(SCREEN_W - PADDLE_W, x - PADDLE_W // 2))

    def _brick_rect(self, r, c):
        x0 = BRICK_MARGIN + c * (BRICK_W + BRICK_MARGIN)
        y0 = BRICK_TOP + r * (BRICK_H + BRICK_MARGIN)
        return x0, y0, x0 + BRICK_W, y0 + BRICK_H

    def _tick(self):
        if self.game_over or self.won:
            return
        bx, by = self.ball
        vx, vy = self.vel
        bx += vx
        by += vy

        if bx - BALL_R <= 0 or bx + BALL_R >= SCREEN_W:
            vx = -vx
            bx = max(BALL_R, min(SCREEN_W - BALL_R, bx))
        if by - BALL_R <= PLAY_TOP:
            vy = -vy
            by = PLAY_TOP + BALL_R

        # paddle collision
        if (PADDLE_Y <= by + BALL_R <= PADDLE_Y + PADDLE_H and
                self.paddle_x <= bx <= self.paddle_x + PADDLE_W and vy > 0):
            vy = -abs(vy)
            hit_pos = (bx - (self.paddle_x + PADDLE_W / 2)) / (PADDLE_W / 2)
            vx = BALL_SPEED * hit_pos

        # brick collisions
        for (r, c) in list(self.bricks):
            x0, y0, x1, y1 = self._brick_rect(r, c)
            if x0 <= bx <= x1 and y0 <= by <= y1:
                self.bricks.discard((r, c))
                self.score += 10
                vy = -vy
                break

        if by - BALL_R > SCREEN_H:
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
            else:
                bx, by = SCREEN_W // 2, PADDLE_Y - BALL_R - 2
                vx, vy = BALL_SPEED * 0.6, -BALL_SPEED

        if not self.bricks:
            self.won = True

        self.ball = [bx, by]
        self.vel = [vx, vy]

    def draw(self, draw, canvas):
        now = time.time()
        while now - self.last_tick >= 0.016:
            self._tick()
            self.last_tick += 0.016

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 14),
                   f"Score {self.score}   Lives {self.lives}", font=FONT_SM,
                   fill=(255, 255, 255), anchor="mm")

        for (r, c) in self.bricks:
            x0, y0, x1, y1 = self._brick_rect(r, c)
            draw.rectangle([x0, y0, x1, y1], fill=BRICK_COLORS[r % len(BRICK_COLORS)])

        draw.rounded_rectangle(
            [self.paddle_x, PADDLE_Y, self.paddle_x + PADDLE_W, PADDLE_Y + PADDLE_H],
            radius=4, fill=ACCENT)

        bx, by = self.ball
        draw.ellipse([bx - BALL_R, by - BALL_R, bx + BALL_R, by + BALL_R], fill=(255, 255, 255))

        if self.game_over:
            draw.text((SCREEN_W // 2, SCREEN_H // 2), "Game Over",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")
        elif self.won:
            draw.text((SCREEN_W // 2, SCREEN_H // 2), "You Win!",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
