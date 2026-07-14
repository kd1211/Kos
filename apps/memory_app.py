import random
import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_XL, CARD_COLOR, ACCENT

SYMBOLS = ["\u2764", "\u2605", "\u2600", "\u266A", "\u2618", "\u26A1", "\u2708", "\u26BD"]


class MemoryApp(App):
    name = "Memory"
    icon = "\U0001F0CF"

    def on_open(self):
        self.wants_animation = True
        pairs = SYMBOLS[:8] * 2
        random.shuffle(pairs)
        self.cards = pairs
        self.revealed = [False] * 16
        self.matched = [False] * 16
        self.pending = []      # indices currently face-up, awaiting resolution
        self.pending_since = 0
        self.moves = 0
        self.buttons = []

        cols, rows = 4, 4
        margin = 8
        top = STATUS_BAR_H + 50
        cell = (SCREEN_W - margin * (cols + 1)) // cols
        self.cells = []
        for i in range(16):
            row, col = divmod(i, cols)
            x = margin + col * (cell + margin)
            y = top + row * (cell + margin)
            self.cells.append((x, y, cell))
            self.buttons.append(Button(x, y, cell, cell, "", self._flip(i)))

        controls_y = top + rows * (cell + margin) + 6
        self.buttons.append(
            Button(16, controls_y, (SCREEN_W - 48) // 2, 40,
                   "New game", self.on_open, font=FONT_MD))
        self.buttons.append(
            Button(32 + (SCREEN_W - 48) // 2, controls_y, (SCREEN_W - 48) // 2, 40,
                   "Home", self.os.go_home, font=FONT_MD))

    def _flip(self, i):
        def handler():
            if self.matched[i] or self.revealed[i] or len(self.pending) == 2:
                return
            self.revealed[i] = True
            self.pending.append(i)
            if len(self.pending) == 2:
                self.moves += 1
                self.pending_since = time.time()
        return handler

    def _resolve_pending(self):
        if len(self.pending) == 2 and time.time() - self.pending_since > 0.6:
            a, b = self.pending
            if self.cards[a] == self.cards[b]:
                self.matched[a] = self.matched[b] = True
            else:
                self.revealed[a] = self.revealed[b] = False
            self.pending = []

    def draw(self, draw, canvas):
        self._resolve_pending()

        top = STATUS_BAR_H + 14
        won = all(self.matched)
        msg = "Solved!" if won else f"Moves: {self.moves}"
        draw.text((SCREEN_W // 2, top), msg, font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        for i, (x, y, cell) in enumerate(self.cells):
            face_up = self.revealed[i] or self.matched[i]
            color = ACCENT if self.matched[i] else CARD_COLOR
            draw.rounded_rectangle([x, y, x + cell, y + cell], radius=8, fill=color)
            if face_up:
                draw.text((x + cell / 2, y + cell / 2), self.cards[i],
                           font=FONT_XL, fill=(255, 255, 255), anchor="mm")

        for b in self.buttons[-2:]:
            b.draw(draw)
