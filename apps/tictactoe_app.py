from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_XL, CARD_COLOR, ACCENT

WINS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


class TicTacToeApp(App):
    name = "TicTacToe"
    icon = "\u2716"

    def on_open(self):
        self.board = [None] * 9
        self.turn = "X"
        self.winner = None
        self.buttons = []

        margin = 16
        board_top = STATUS_BAR_H + 55
        cell = (SCREEN_W - margin * 4) // 3
        self.cells = []
        for i in range(9):
            row, col = divmod(i, 3)
            x = margin + col * (cell + margin)
            y = board_top + row * (cell + margin)
            self.cells.append((x, y, cell))
            self.buttons.append(Button(x, y, cell, cell, "", self._play(i)))

        controls_y = board_top + 3 * (cell + margin) + 10
        self.buttons.append(
            Button(16, controls_y, (SCREEN_W - 48) // 2, 44,
                   "New game", self._new_game, font=FONT_MD))
        self.buttons.append(
            Button(32 + (SCREEN_W - 48) // 2, controls_y, (SCREEN_W - 48) // 2, 44,
                   "Home", self.os.go_home, font=FONT_MD))

    def _new_game(self):
        self.on_open()

    def _play(self, i):
        def handler():
            if self.board[i] is None and not self.winner:
                self.board[i] = self.turn
                self._check_winner()
                self.turn = "O" if self.turn == "X" else "X"
        return handler

    def _check_winner(self):
        for a, b, c in WINS:
            if self.board[a] and self.board[a] == self.board[b] == self.board[c]:
                self.winner = self.board[a]
                return
        if all(self.board):
            self.winner = "Draw"

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 16
        if self.winner:
            msg = "Draw!" if self.winner == "Draw" else f"{self.winner} wins!"
        else:
            msg = f"{self.turn}'s turn"
        draw.text((SCREEN_W // 2, top), msg, font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        for i, (x, y, cell) in enumerate(self.cells):
            draw.rounded_rectangle([x, y, x + cell, y + cell], radius=10, fill=CARD_COLOR)
            if self.board[i]:
                draw.text((x + cell / 2, y + cell / 2), self.board[i],
                           font=FONT_XL, fill=ACCENT, anchor="mm")

        for b in self.buttons[-2:]:
            b.draw(draw)
