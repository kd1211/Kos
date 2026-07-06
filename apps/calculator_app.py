from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, CARD_COLOR, ACCENT

KEYS = [
    "7", "8", "9", "/",
    "4", "5", "6", "*",
    "1", "2", "3", "-",
    "0", ".", "=", "+",
]


class CalculatorApp(App):
    name = "Calculator"
    icon = "\U0001F5A9"

    def on_open(self):
        self.expr = ""
        self.result = ""
        self.buttons = []
        cols = 4
        margin = 10
        top = STATUS_BAR_H + 90
        cell = (SCREEN_W - margin * (cols + 1)) // cols

        for i, key in enumerate(KEYS):
            row, col = divmod(i, cols)
            x = margin + col * (cell + margin)
            y = top + row * (cell + margin)
            self.buttons.append(
                Button(x, y, cell, cell, key, self._press(key), font=FONT_MD))

        self.buttons.append(
            Button(margin, top + 4 * (cell + margin), cell, 40,
                   "C", self._clear, font=FONT_MD))
        self.buttons.append(
            Button(margin + cell + margin, top + 4 * (cell + margin),
                   cell * 3 + margin * 2, 40, "Home", self.os.go_home, font=FONT_MD))

    def _press(self, key):
        def handler():
            if key == "=":
                try:
                    # only digits/operators reach here, safe to evaluate
                    self.result = str(eval(self.expr))
                except Exception:
                    self.result = "Error"
            else:
                self.expr += key
        return handler

    def _clear(self):
        self.expr = ""
        self.result = ""

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 10
        draw.rectangle([16, top, SCREEN_W - 16, top + 70], fill=CARD_COLOR)
        draw.text((SCREEN_W - 26, top + 20), self.expr or "0", font=FONT_MD,
                   fill=(220, 220, 220), anchor="rm")
        draw.text((SCREEN_W - 26, top + 48), self.result, font=FONT_LG,
                   fill=ACCENT, anchor="rm")
        for b in self.buttons:
            b.draw(draw)
