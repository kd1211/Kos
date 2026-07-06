"""
Paint -- finger-drag drawing with a color palette, eraser, adjustable brush
sizes, multi-step undo, and one-tap saving into the Gallery's Pictures
folder (~/Pictures), timestamped so repeated saves never collide.
"""

import os
import time
from PIL import Image, ImageDraw
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, CARD_COLOR, ACCENT

PICTURES_DIR = os.path.expanduser("~/Pictures")

TOOLBAR_H = 132
CANVAS_TOP = STATUS_BAR_H
CANVAS_BOTTOM = SCREEN_H - TOOLBAR_H
CANVAS_H = CANVAS_BOTTOM - CANVAS_TOP

PAPER_COLOR = (250, 250, 250)

PALETTE = [
    ("Black", (20, 20, 20)),
    ("White", (255, 255, 255)),
    ("Red", (230, 70, 70)),
    ("Green", (80, 210, 120)),
    ("Blue", (80, 140, 240)),
    ("Yellow", (240, 210, 70)),
]

BRUSH_SIZES = [3, 5, 9, 15]  # radii
MAX_UNDO = 15


class PaintApp(App):
    name = "Paint"
    icon = "\U0001F3A8"

    def __init__(self, os_ref):
        super().__init__(os_ref)
        self.surface = Image.new("RGB", (SCREEN_W, CANVAS_H), PAPER_COLOR)
        self.surface_draw = ImageDraw.Draw(self.surface)
        self.current_color = (20, 20, 20)
        self.erasing = False
        self.brush_index = 1
        self._last_point = None
        self._undo_stack = []
        self.status = None

    def on_open(self):
        self._last_point = None
        self.status = None
        self._build_buttons()

    def _build_buttons(self):
        self.buttons = []
        row1_y = CANVAS_BOTTOM
        row2_y = CANVAS_BOTTOM + 40
        row3_y = CANVAS_BOTTOM + 88

        # row 1: color palette
        swatch_w = SCREEN_W // len(PALETTE)
        for i, (label, color) in enumerate(PALETTE):
            self.buttons.append(
                Button(i * swatch_w, row1_y, swatch_w, 36, "",
                       self._pick_color(color), bg=color, font=FONT_SM))

        # row 2: eraser, brush size, undo
        third = SCREEN_W // 3
        self.buttons.append(
            Button(0, row2_y, third, 44, "Eraser", self._pick_eraser, font=FONT_SM))
        self.buttons.append(
            Button(third, row2_y, third, 44, self._size_label(), self._cycle_size, font=FONT_SM))
        self.buttons.append(
            Button(2 * third, row2_y, third, 44, "Undo", self._undo, font=FONT_SM))

        # row 3: save, clear, home
        self.buttons.append(
            Button(0, row3_y, third, 40, "Save", self._save_to_gallery, font=FONT_SM))
        self.buttons.append(
            Button(third, row3_y, third, 40, "Clear", self._clear, font=FONT_SM))
        self.buttons.append(
            Button(2 * third, row3_y, third, 40, "Home", self.os.go_home, font=FONT_SM))

    def _size_label(self):
        return f"Size: {BRUSH_SIZES[self.brush_index]}"

    def _cycle_size(self):
        self.brush_index = (self.brush_index + 1) % len(BRUSH_SIZES)
        self.buttons[7].label = self._size_label()

    def _pick_color(self, color):
        def handler():
            self.current_color = color
            self.erasing = False
        return handler

    def _pick_eraser(self):
        self.erasing = True

    def _push_undo(self):
        self._undo_stack.append(self.surface.copy())
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack.pop(0)

    def _undo(self):
        if self._undo_stack:
            self.surface = self._undo_stack.pop()
            self.surface_draw = ImageDraw.Draw(self.surface)
            self.status = None

    def _clear(self):
        self._push_undo()
        self.surface_draw.rectangle([0, 0, SCREEN_W, CANVAS_H], fill=PAPER_COLOR)
        self.status = None

    def _save_to_gallery(self):
        try:
            os.makedirs(PICTURES_DIR, exist_ok=True)
            fname = f"paint_{time.strftime('%Y%m%d_%H%M%S')}.png"
            self.surface.save(os.path.join(PICTURES_DIR, fname))
            self.status = f"Saved {fname}"
        except Exception as e:
            self.status = f"Save failed: {e}"

    def _active_color(self):
        return PAPER_COLOR if self.erasing else self.current_color

    def on_touch_move(self, x, y):
        if y >= CANVAS_BOTTOM:
            self._last_point = None  # finger is over the toolbar, don't draw
            return
        local_y = y - CANVAS_TOP
        radius = BRUSH_SIZES[self.brush_index]
        color = self._active_color()
        if self._last_point is None:
            self._push_undo()  # snapshot at the start of every new stroke
        else:
            self.surface_draw.line(
                [self._last_point, (x, local_y)], fill=color, width=radius * 2)
        self.surface_draw.ellipse(
            [x - radius, local_y - radius, x + radius, local_y + radius], fill=color)
        self._last_point = (x, local_y)

    def on_touch_up(self):
        self._last_point = None

    def draw(self, draw, canvas):
        canvas.paste(self.surface, (0, CANVAS_TOP))
        draw.rectangle([0, CANVAS_BOTTOM, SCREEN_W, SCREEN_H], fill=CARD_COLOR)
        for b in self.buttons:
            b.draw(draw)

        # outline the active color/eraser so it's clear what's selected
        swatch_w = SCREEN_W // len(PALETTE)
        if not self.erasing:
            for i, (_, color) in enumerate(PALETTE):
                if color == self.current_color:
                    x0 = i * swatch_w
                    draw.rectangle([x0, CANVAS_BOTTOM, x0 + swatch_w, CANVAS_BOTTOM + 36],
                                    outline=(255, 255, 255), width=3)
        else:
            third = SCREEN_W // 3
            draw.rectangle([0, CANVAS_BOTTOM + 40, third, CANVAS_BOTTOM + 84],
                            outline=ACCENT, width=3)

        if self.status:
            draw.rounded_rectangle([SCREEN_W // 2 - 100, CANVAS_TOP + 6,
                                     SCREEN_W // 2 + 100, CANVAS_TOP + 30],
                                    radius=8, fill=CARD_COLOR)
            draw.text((SCREEN_W // 2, CANVAS_TOP + 18), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm")
