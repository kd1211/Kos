from PIL import Image
from ui.framework import App, SCREEN_W, SCREEN_H, STATUS_BAR_H, FONT_MD


class FlashlightApp(App):
    """Turns the whole screen white at full backlight - handy as a torch
    and a quick real-world use of the UPS HAT's power (worth knowing this
    will drain the battery faster than normal use)."""

    name = "Flashlight"
    icon = "\U0001F526"

    def on_open(self):
        self.buttons = []
        try:
            self.os.lcd.set_backlight(100)
        except Exception:
            pass

    def on_close(self):
        try:
            self.os.lcd.set_backlight(90)
        except Exception:
            pass

    def draw(self, draw, canvas):
        draw.rectangle([0, STATUS_BAR_H, SCREEN_W, SCREEN_H], fill=(255, 255, 255))
        draw.text((SCREEN_W // 2, SCREEN_H - 30), "Tap to go Home", font=FONT_MD,
                   fill=(120, 120, 120), anchor="mm")

    def on_tap(self, x, y):
        self.os.go_home()
        return True
