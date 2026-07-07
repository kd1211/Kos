import random
from ui import sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_SM, CARD_COLOR, ACCENT

WORDS = [
    "PYTHON", "RASPBERRY", "TOUCHSCREEN", "BATTERY", "KEYBOARD",
    "GALLERY", "PAINT", "SNAKE", "CALENDAR", "WEATHER", "BROWSER",
    "MESSAGE", "PIOS", "FOLDER", "WALLPAPER", "SETTINGS", "CLOCK",
    "MEMORY", "BREAKOUT", "EMULATOR", "NOTES", "CALCULATOR",
]

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_WRONG = 6


class HangmanApp(App):
    name = "Hangman"
    icon = "\U0001F9D9"

    def on_open(self):
        self.word = random.choice(WORDS)
        self.guessed = set()
        self.wrong = 0
        self.won = False
        self.lost = False
        self._build_buttons()

    def _build_buttons(self):
        margin = 6
        cols = 7
        top = STATUS_BAR_H + 168
        cell = (SCREEN_W - margin * (cols + 1)) // cols
        self.buttons = []
        for i, ch in enumerate(LETTERS):
            row, col = divmod(i, cols)
            x = margin + col * (cell + margin)
            y = top + row * (cell + margin)
            if y + cell > SCREEN_H - 100:
                break
            self.buttons.append(
                Button(x, y, cell, cell - 4, ch, self._guess(ch), font=FONT_SM))

        self.buttons.append(
            Button(16, SCREEN_H - 48, 100, 36, "New", self.on_open, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W - 116, SCREEN_H - 48, 100, 36,
                   "Home", self.os.go_home, font=FONT_SM))

    def _guess(self, ch):
        def handler():
            if self.won or self.lost or ch in self.guessed:
                return
            self.guessed.add(ch)
            if ch in self.word:
                if all(c in self.guessed for c in self.word):
                    self.won = True
                    sound.chime()
            else:
                self.wrong += 1
                sound.beep(220, 120)
                if self.wrong >= MAX_WRONG:
                    self.lost = True
        return handler

    def _display_word(self):
        return " ".join(c if c in self.guessed else "_" for c in self.word)

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 12
        if self.won:
            status = "You win!"
            color = ACCENT
        elif self.lost:
            status = f"Word: {self.word}"
            color = (230, 90, 90)
        else:
            status = f"Wrong: {self.wrong}/{MAX_WRONG}"
            color = (220, 220, 220)

        draw.text((SCREEN_W // 2, top), status, font=FONT_MD, fill=color, anchor="mm")

        draw.rounded_rectangle([16, top + 28, SCREEN_W - 16, top + 72],
                                radius=10, fill=CARD_COLOR)
        draw.text((SCREEN_W // 2, top + 50), self._display_word(), font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        # simple gallows + stick figure progress
        gx, gy = 36, top + 88
        draw.line([gx, gy + 50, gx, gy], fill=(160, 160, 170), width=2)
        draw.line([gx, gy + 50, gx + 40, gy + 50], fill=(160, 160, 170), width=2)
        draw.line([gx + 20, gy, gx + 20, gy + 12], fill=(160, 160, 170), width=2)
        if self.wrong >= 1:
            draw.ellipse([gx + 14, gy + 12, gx + 26, gy + 24], outline=(200, 200, 210))
        if self.wrong >= 2:
            draw.line([gx + 20, gy + 24, gx + 20, gy + 40], fill=(200, 200, 210), width=2)
        if self.wrong >= 3:
            draw.line([gx + 20, gy + 28, gx + 10, gy + 36], fill=(200, 200, 210), width=2)
        if self.wrong >= 4:
            draw.line([gx + 20, gy + 28, gx + 30, gy + 36], fill=(200, 200, 210), width=2)
        if self.wrong >= 5:
            draw.line([gx + 20, gy + 40, gx + 12, gy + 52], fill=(200, 200, 210), width=2)
        if self.wrong >= 6:
            draw.line([gx + 20, gy + 40, gx + 28, gy + 52], fill=(200, 200, 210), width=2)

        for b in self.buttons:
            if b.label in LETTERS and b.label in self.guessed:
                b.bg = (60, 120, 80) if b.label in self.word else (120, 60, 60)
            b.draw(draw)
