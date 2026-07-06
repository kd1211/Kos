import random
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

SIZE = 4
BOARD_TOP = STATUS_BAR_H + 56
BOARD_MARGIN = 20
CELL = (SCREEN_W - BOARD_MARGIN * 2) // SIZE
DPAD_Y = BOARD_TOP + CELL * SIZE + 14

TILE_COLORS = {
    0: (60, 60, 68), 2: (238, 228, 218), 4: (237, 224, 200),
    8: (242, 177, 121), 16: (245, 149, 99), 32: (246, 124, 95),
    64: (246, 94, 59), 128: (237, 207, 114), 256: (237, 204, 97),
    512: (237, 200, 80), 1024: (237, 197, 63), 2048: (237, 194, 46),
}


class Game2048App(App):
    name = "2048"
    icon = "\U0001F522"

    def on_open(self):
        self.board = [[0] * SIZE for _ in range(SIZE)]
        self.score = 0
        self.game_over = False
        self._spawn()
        self._spawn()

        dpad_w = 56
        cx = SCREEN_W // 2
        self.buttons = [
            Button(cx - dpad_w // 2, DPAD_Y, dpad_w, 40, "\u2191", self._move(0, -1), font=FONT_LG),
            Button(cx - dpad_w // 2, DPAD_Y + 44, dpad_w, 40, "\u2193", self._move(0, 1), font=FONT_LG),
            Button(cx - dpad_w - 8, DPAD_Y + 22, dpad_w, 40, "\u2190", self._move(-1, 0), font=FONT_LG),
            Button(cx + 8, DPAD_Y + 22, dpad_w, 40, "\u2192", self._move(1, 0), font=FONT_LG),
            Button(16, SCREEN_H - 44, 90, 34, "Restart", self.on_open, font=FONT_SM),
            Button(SCREEN_W - 106, SCREEN_H - 44, 90, 34, "Home", self.os.go_home, font=FONT_SM),
        ]

    def _spawn(self):
        empties = [(r, c) for r in range(SIZE) for c in range(SIZE) if self.board[r][c] == 0]
        if not empties:
            return
        r, c = random.choice(empties)
        self.board[r][c] = 4 if random.random() < 0.1 else 2

    def _line_merge(self, line):
        vals = [v for v in line if v != 0]
        merged = []
        gained = 0
        i = 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                merged.append(vals[i] * 2)
                gained += vals[i] * 2
                i += 2
            else:
                merged.append(vals[i])
                i += 1
        merged += [0] * (SIZE - len(merged))
        return merged, gained

    def _move(self, dx, dy):
        def handler():
            if self.game_over:
                return
            board = self.board
            moved = False
            gained_total = 0

            def get_line(i, reverse):
                if dx != 0:
                    line = board[i]
                else:
                    line = [board[r][i] for r in range(SIZE)]
                return line[::-1] if reverse else line

            def set_line(i, line, reverse):
                if reverse:
                    line = line[::-1]
                if dx != 0:
                    board[i] = line
                else:
                    for r in range(SIZE):
                        board[r][i] = line[r]

            reverse = (dx == 1) or (dy == 1)
            for i in range(SIZE):
                before = get_line(i, reverse)
                merged, gained = self._line_merge(before)
                if merged != before:
                    moved = True
                gained_total += gained
                set_line(i, merged, reverse)

            if moved:
                self.score += gained_total
                self._spawn()
                if not self._any_moves_left():
                    self.game_over = True
        return handler

    def _any_moves_left(self):
        for r in range(SIZE):
            for c in range(SIZE):
                if self.board[r][c] == 0:
                    return True
                if c + 1 < SIZE and self.board[r][c] == self.board[r][c + 1]:
                    return True
                if r + 1 < SIZE and self.board[r][c] == self.board[r + 1][c]:
                    return True
        return False

    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 26), f"2048  Score: {self.score}",
                   font=FONT_MD, fill=(255, 255, 255), anchor="mm")

        for r in range(SIZE):
            for c in range(SIZE):
                v = self.board[r][c]
                x0 = BOARD_MARGIN + c * CELL
                y0 = BOARD_TOP + r * CELL
                color = TILE_COLORS.get(v, (60, 200, 220))
                draw.rounded_rectangle([x0 + 3, y0 + 3, x0 + CELL - 3, y0 + CELL - 3],
                                        radius=8, fill=color)
                if v:
                    fg = (60, 55, 50) if v <= 4 else (250, 250, 250)
                    draw.text((x0 + CELL // 2, y0 + CELL // 2), str(v),
                               font=FONT_MD, fill=fg, anchor="mm")

        if self.game_over:
            draw.text((SCREEN_W // 2, BOARD_TOP + CELL * SIZE // 2), "Game Over",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
