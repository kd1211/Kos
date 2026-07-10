"""
Camera -- a live viewfinder and shutter for the Raspberry Pi Camera
Module, backed by drivers/camera.py (picamera2). Frame capture happens
directly in draw() each frame (no threading needed -- a 320x320 preview
grab is fast, unlike the multi-second Wi-Fi/Bluetooth scans elsewhere
in this OS that genuinely need a background thread), which is why this
app opts into continuous animation the same way Raycrawl does.

If no camera is attached (or picamera2 isn't installed), the app still
opens cleanly and just says so -- a camera is optional peripheral
hardware, unlike the LCD/touch/battery the rest of the OS assumes are
always present.
"""

import os
import time
from PIL import Image
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT
from drivers.camera import Camera

PICTURES_DIR = os.path.expanduser("~/Pictures")

PREVIEW_SIZE = 320
PREVIEW_TOP = STATUS_BAR_H
PREVIEW_BOTTOM = PREVIEW_TOP + PREVIEW_SIZE
CONTROLS_TOP = PREVIEW_BOTTOM + 6


class CameraApp(App):
    name = "Camera"
    icon = "\U0001F4F7"

    def on_open(self):
        self.wants_animation = True
        self.camera = Camera(preview_size=(PREVIEW_SIZE, PREVIEW_SIZE))
        self.mirror = False
        self.grid = False
        self.status = None
        self.status_until = 0
        self._last_frame = None
        self._build_buttons()

    def on_close(self):
        # release the camera device so it's free the moment you leave --
        # this is a single-screen OS with no background task model
        self.camera.close()

    def _build_buttons(self):
        self.buttons = []
        if not self.camera.available:
            self.buttons.append(
                Button(SCREEN_W // 2 - 60, SCREEN_H - 60, 120, 42,
                       "Home", self.os.go_home, font=FONT_SM))
            return

        shutter_d = 72
        self.shutter_button = Button(
            SCREEN_W // 2 - shutter_d // 2, CONTROLS_TOP + 8, shutter_d, shutter_d,
            "", self._capture, font=FONT_MD, bg=(255, 255, 255))
        self.buttons.append(self.shutter_button)
        self.buttons.append(
            Button(16, CONTROLS_TOP + 20, 64, 44, "Grid", self._toggle_grid, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W - 80, CONTROLS_TOP + 20, 64, 44, "Mirror",
                   self._toggle_mirror, font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2 - 50, SCREEN_H - 34, 100, 30, "Home",
                   self.os.go_home, font=FONT_SM))

    def _toggle_grid(self):
        self.grid = not self.grid

    def _toggle_mirror(self):
        self.mirror = not self.mirror

    def _capture(self):
        try:
            os.makedirs(PICTURES_DIR, exist_ok=True)
            fname = f"photo_{time.strftime('%Y%m%d_%H%M%S')}.jpg"
            path = os.path.join(PICTURES_DIR, fname)
            ok = self.camera.capture_still(path)
            self.status = f"Saved {fname}" if ok else "Couldn't save photo"
        except Exception as e:
            self.status = f"Capture failed: {e}"
        self.status_until = time.time() + 2.0

    def draw(self, draw, canvas):
        if not self.camera.available:
            self._draw_unavailable(draw)
            for b in self.buttons:
                b.draw(draw)
            return

        frame = self.camera.capture_preview_array()
        if frame is not None:
            img = Image.fromarray(frame)
            if self.mirror:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            self._last_frame = img
            canvas.paste(img, (0, PREVIEW_TOP))
        elif self._last_frame is not None:
            canvas.paste(self._last_frame, (0, PREVIEW_TOP))
        else:
            draw.rectangle([0, PREVIEW_TOP, SCREEN_W, PREVIEW_BOTTOM], fill=(20, 20, 24))

        if self.grid:
            self._draw_grid(draw)

        draw.rectangle([0, PREVIEW_BOTTOM, SCREEN_W, SCREEN_H], fill=(16, 16, 20))
        for b in self.buttons:
            if b is self.shutter_button:
                cx, cy = b.x + b.w / 2, b.y + b.h / 2
                r = b.w / 2
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=4)
                draw.ellipse([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8], fill=(255, 255, 255))
            else:
                b.draw(draw)

        if self.status and time.time() < self.status_until:
            draw.rounded_rectangle([SCREEN_W // 2 - 110, PREVIEW_TOP + 8,
                                     SCREEN_W // 2 + 110, PREVIEW_TOP + 32],
                                    radius=8, fill=(0, 0, 0))
            draw.text((SCREEN_W // 2, PREVIEW_TOP + 20), self.status, font=FONT_SM,
                       fill=(255, 255, 255), anchor="mm")

    def _draw_grid(self, draw):
        for i in (1, 2):
            x = i * PREVIEW_SIZE // 3
            draw.line([x, PREVIEW_TOP, x, PREVIEW_BOTTOM], fill=(230, 230, 230), width=1)
            y = PREVIEW_TOP + i * PREVIEW_SIZE // 3
            draw.line([0, y, SCREEN_W, y], fill=(230, 230, 230), width=1)

    def _draw_unavailable(self, draw):
        draw.rectangle([0, PREVIEW_TOP, SCREEN_W, SCREEN_H], fill=(16, 16, 20))
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 40), "\U0001F4F7", font=FONT_LG,
                   fill=(120, 120, 130), anchor="mm")
        draw.text((SCREEN_W // 2, SCREEN_H // 2 + 10), "No camera detected", font=FONT_MD,
                   fill=(200, 200, 210), anchor="mm")
        draw.text((SCREEN_W // 2, SCREEN_H // 2 + 36),
                   "Check the ribbon cable and that\npicamera2 is installed", font=FONT_SM,
                   fill=(140, 140, 150), anchor="mm", align="center")
