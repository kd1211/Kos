"""
RetroArch-style emulator frontend.

Real RetroArch is a native app that loads compiled libretro cores; this
is a from-scratch, pure-Python frontend built for Kos's screen and
touch input, but it borrows RetroArch's core ideas:

  - a ROM browser decoupled from any one system (emulators/core_base.py
    is the "core" interface -- see that file for how to add a new
    system's core alongside the built-in CHIP-8 one)
  - favorites + "last played" tracking
  - a Quick Menu (pause overlay) with Resume / Save State / Load State /
    Rewind / Restart / Fast-Forward / Mute / Exit
  - save states per ROM, persisted to disk
  - a short rewind buffer (like RetroArch's instant-rewind feature)
  - a fast-forward toggle

Only CHIP-8 is bundled, deliberately -- see emulators/chip8.py's
docstring for why (no copyrighted BIOS/ROM files needed). Drop more
`.ch8` files in roms/ to play more, or add another core.
"""

import os
import json
import time
from PIL import Image

from ui import theme, sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_MD, FONT_SM, FONT_LG
from emulators import core_base
from emulators import chip8_core  # noqa: F401 -- registers the CHIP-8 core

ROMS_DIR = os.path.join(os.path.dirname(__file__), "..", "roms")
STATES_DIR = os.path.expanduser("~/.kos_savestates")
LIBRARY_FILE = os.path.expanduser("~/.kos_retroarch_library.json")

ROW_H = 46
PAGE_SIZE = 6
REWIND_INTERVAL = 0.5     # seconds between rewind snapshots
REWIND_CAPACITY = 60      # ~30 seconds of rewind history
SOUND_BEEP_INTERVAL = 0.12


def _load_library():
    if os.path.exists(LIBRARY_FILE):
        try:
            with open(LIBRARY_FILE) as f:
                data = json.load(f)
            data.setdefault("favorites", [])
            data.setdefault("last_played", {})
            return data
        except Exception:
            pass
    return {"favorites": [], "last_played": {}}


def _save_library(data):
    try:
        with open(LIBRARY_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


class EmulatorApp(App):
    name = "RetroArch"
    icon = "\U0001F579"

    @property
    def wants_animation(self):
        # only keep the OS rendering every frame while a core is actually
        # stepping -- sitting in the ROM picker is just as static as any
        # other menu and shouldn't keep the display looping at full speed
        return self.state in ("running", "quickmenu")

    def __init__(self, os_ref):
        super().__init__(os_ref)
        self.state = "picker"
        self.page = 0
        self.core = None
        self.core_id = None
        self.rom_name = None
        self.held_key = None
        self.fast_forward = False
        self.muted = False
        self._last_tick = time.time()
        self._last_beep = 0.0
        self._last_rewind = 0.0
        self._rewind_buffer = []
        self.pad_buttons = []
        self.library = _load_library()
        self.status_msg = None
        self._status_until = 0

    def on_open(self):
        self.state = "picker"
        self.page = 0
        self._build_picker()

    # -- ROM library ----------------------------------------------------
    def _list_roms(self):
        """Returns [(core_id, filename)] for every ROM the registered
        cores can handle, favorites first, then alphabetical."""
        found = []
        if os.path.isdir(ROMS_DIR):
            for f in sorted(os.listdir(ROMS_DIR)):
                core_cls = core_base.core_for_filename(f)
                if core_cls:
                    found.append((core_cls.core_id, f))
        favs = set(self.library["favorites"])

        def sort_key(item):
            return (item[1] not in favs, item[1].lower())
        found.sort(key=sort_key)
        return found

    def _build_picker(self):
        self.roms = self._list_roms()
        top = STATUS_BAR_H + 66
        self.buttons = []
        start = self.page * PAGE_SIZE
        page_roms = self.roms[start:start + PAGE_SIZE]

        for i, (core_id, filename) in enumerate(page_roms):
            y = top + i * ROW_H
            is_fav = filename in self.library["favorites"]
            self.buttons.append(
                Button(16, y, 34, ROW_H - 6, "\u2605" if is_fav else "\u2606",
                       self._toggle_favorite(filename), font=FONT_MD))
            self.buttons.append(
                Button(56, y, SCREEN_W - 72, ROW_H - 6, filename,
                       self._load_rom(core_id, filename), font=FONT_SM))

        footer_y = top + len(page_roms) * ROW_H + 14
        total_pages = max(1, (len(self.roms) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._total_pages = total_pages
        self.buttons.append(Button(16, footer_y, 70, 36, "Prev", self._prev_page, font=FONT_SM))
        self.buttons.append(Button(94, footer_y, 70, 36, "Next", self._next_page, font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 106, footer_y, 90, 36,
                                    "Home", self.os.go_home, font=FONT_SM))

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._build_picker()

    def _next_page(self):
        if (self.page + 1) * PAGE_SIZE < len(self.roms):
            self.page += 1
            self._build_picker()

    def _toggle_favorite(self, filename):
        def handler():
            favs = self.library["favorites"]
            if filename in favs:
                favs.remove(filename)
            else:
                favs.append(filename)
            _save_library(self.library)
            self._build_picker()
        return handler

    def _load_rom(self, core_id, filename):
        def handler():
            core_cls = core_base.REGISTRY[core_id]
            self.core = core_cls()
            try:
                self.core.load(os.path.join(ROMS_DIR, filename))
            except Exception as e:
                self._flash(f"Load failed: {e}")
                self.core = None
                return
            self.core_id = core_id
            self.rom_name = filename
            self.fast_forward = False
            self.muted = False
            self._rewind_buffer = []
            self._last_tick = time.time()
            self.library["last_played"][filename] = time.time()
            _save_library(self.library)
            self.state = "running"
            self._build_run_controls()
        return handler

    def _restart_rom(self):
        if self.core_id and self.rom_name:
            self._load_rom(self.core_id, self.rom_name)()

    def _back_to_picker(self):
        self.core = None
        self.state = "picker"
        self._build_picker()

    # -- running: on-screen pad ------------------------------------------
    def _build_run_controls(self):
        layout = self.core.input_layout
        rows = len(layout)
        cols = max(len(r) for r in layout) if rows else 0
        margin = 8
        pad_top = SCREEN_H - 8 - rows * 50 - (rows - 1) * margin
        cell_w = (SCREEN_W - margin * (cols + 1)) // cols if cols else 0
        cell_h = 44
        self.pad_buttons = []
        for r, row in enumerate(layout):
            row_cols = len(row)
            row_w = row_cols * cell_w + (row_cols - 1) * margin
            x0 = (SCREEN_W - row_w) // 2
            for c, label in enumerate(row):
                x = x0 + c * (cell_w + margin)
                y = pad_top + r * (cell_h + margin)
                self.pad_buttons.append((x, y, cell_w, cell_h, label))
        self._pad_top = pad_top

        self.buttons = [
            Button(SCREEN_W - 76, STATUS_BAR_H + 8, 60, 30,
                   "\u2261 Menu", self._open_quickmenu, font=FONT_SM),
        ]

    def _key_at(self, x, y):
        for kx, ky, kw, kh, label in self.pad_buttons:
            if kx <= x <= kx + kw and ky <= y <= ky + kh:
                return label
        return None

    # -- quick menu ------------------------------------------------------
    def _open_quickmenu(self):
        self.state = "quickmenu"
        self._build_quickmenu()

    def _build_quickmenu(self):
        items = [
            ("Resume", self._resume),
            ("Save State", self._save_state),
            ("Load State", self._load_state),
            (f"Rewind ({len(self._rewind_buffer)})", self._rewind),
            ("Restart", self._restart_and_resume),
            (f"Fast-Forward: {'On' if self.fast_forward else 'Off'}", self._toggle_ff),
            (f"Sound: {'Muted' if self.muted else 'On'}", self._toggle_mute),
            ("Exit to ROM list", self._back_to_picker),
            ("Exit to Home", self.os.go_home),
        ]
        top = STATUS_BAR_H + 56
        self.buttons = []
        for i, (label, handler) in enumerate(items):
            y = top + i * 40
            self.buttons.append(Button(30, y, SCREEN_W - 60, 34, label, handler, font=FONT_SM))

    def _resume(self):
        self.state = "running"
        self._last_tick = time.time()

    def _restart_and_resume(self):
        self._restart_rom()

    def _toggle_ff(self):
        self.fast_forward = not self.fast_forward
        self._build_quickmenu()

    def _toggle_mute(self):
        self.muted = not self.muted
        self._build_quickmenu()

    def _state_path(self):
        os.makedirs(STATES_DIR, exist_ok=True)
        return os.path.join(STATES_DIR, f"{self.core_id}_{self.rom_name}.json")

    def _save_state(self):
        try:
            with open(self._state_path(), "w") as f:
                json.dump(self.core.save_state(), f)
            self._flash("State saved")
        except Exception as e:
            self._flash(f"Save failed: {e}")
        self._resume()

    def _load_state(self):
        path = self._state_path()
        if not os.path.exists(path):
            self._flash("No save state yet")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.core.load_state(data)
            self._flash("State loaded")
        except Exception as e:
            self._flash(f"Load failed: {e}")
        self._resume()

    def _rewind(self):
        if self._rewind_buffer:
            snapshot = self._rewind_buffer.pop()
            try:
                self.core.load_state(snapshot)
                self._flash("Rewound")
            except Exception:
                pass
            self._build_quickmenu()
        else:
            self._flash("Nothing to rewind")

    def _flash(self, msg, seconds=1.6):
        self.status_msg = msg
        self._status_until = time.time() + seconds

    # -- touch handling ----------------------------------------------------
    def on_tap(self, x, y):
        if self.state != "running":
            return super().on_tap(x, y)
        key = self._key_at(x, y)
        if key is not None:
            self.held_key = key
            self.core.press(key)
            return True
        return super().on_tap(x, y)

    def on_touch_move(self, x, y):
        if self.state != "running":
            return
        key = self._key_at(x, y)
        if key != self.held_key:
            if self.held_key is not None:
                self.core.release(self.held_key)
            self.held_key = key
            if key is not None:
                self.core.press(key)

    def on_touch_up(self):
        if self.held_key is not None and self.core:
            self.core.release(self.held_key)
        self.held_key = None

    # -- emulation step + rewind sampling --------------------------------
    def _step_emulator(self):
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self.core.run_frame(dt, fast_forward=self.fast_forward)

        if self.core.is_sound_active() and not self.muted:
            if now - self._last_beep > SOUND_BEEP_INTERVAL:
                sound.beep(660, 90)
                self._last_beep = now

        if now - self._last_rewind > REWIND_INTERVAL and not self.fast_forward:
            try:
                self._rewind_buffer.append(self.core.save_state())
                if len(self._rewind_buffer) > REWIND_CAPACITY:
                    self._rewind_buffer.pop(0)
            except Exception:
                pass
            self._last_rewind = now

    # -- drawing ------------------------------------------------------------
    def draw(self, draw, canvas):
        if self.state == "picker":
            self._draw_picker(draw)
        elif self.state in ("running", "quickmenu"):
            self._draw_running(draw, canvas)
            if self.state == "quickmenu":
                self._draw_quickmenu(draw)

    def _draw_picker(self, draw):
        fg, accent = theme.fg_color(), theme.accent_color()
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 22), "RetroArch",
                   font=FONT_LG, fill=fg, anchor="mm")
        cores = ", ".join(sorted({c.display_name for c in core_base.REGISTRY.values()}))
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 48), f"Cores loaded: {cores}",
                   font=FONT_SM, fill=(160, 160, 175), anchor="mm")

        if not self.roms:
            draw.text((SCREEN_W // 2, SCREEN_H // 2 - 20),
                       "No ROMs found.\nCopy .ch8 files into\nthe roms/ folder.",
                       font=FONT_SM, fill=(180, 180, 190), anchor="mm", align="center")

        for b in self.buttons:
            b.draw(draw)
        draw.text((SCREEN_W // 2, SCREEN_H - 10),
                   f"Page {self.page + 1}/{self._total_pages}", font=FONT_SM,
                   fill=(140, 140, 150), anchor="mm")

    def _draw_running(self, draw, canvas):
        if self.state == "running":
            self._step_emulator()

        core = self.core
        native_w, native_h = core.display_size
        scale = max(1, min(4, (SCREEN_W - 16) // native_w))
        disp_w, disp_h = native_w * scale, native_h * scale
        disp_x = (SCREEN_W - disp_w) // 2
        disp_y = STATUS_BAR_H + 40

        draw.text((14, STATUS_BAR_H + 18), self.rom_name or "", font=FONT_SM,
                   fill=(190, 190, 200), anchor="lm")
        if self.fast_forward:
            draw.text((14, STATUS_BAR_H + 36), "FF", font=FONT_SM,
                      fill=theme.accent_color(), anchor="lm")

        pixels = core.get_display()
        img = Image.new("RGB", (native_w, native_h))
        img.putdata([core.on_color if p else core.off_color for p in pixels])
        img = img.resize((disp_w, disp_h), Image.NEAREST)
        canvas.paste(img, (disp_x, disp_y))
        draw.rectangle([disp_x - 4, disp_y - 4, disp_x + disp_w + 4, disp_y + disp_h + 4],
                        outline=(80, 80, 90), width=2)

        card, fg, accent = theme.card_color(), theme.fg_color(), theme.accent_color()
        for kx, ky, kw, kh, label in self.pad_buttons:
            is_held = self.held_key == label
            draw.rounded_rectangle([kx, ky, kx + kw, ky + kh], radius=8,
                                    fill=accent if is_held else card)
            draw.text((kx + kw / 2, ky + kh / 2), label, font=FONT_MD, fill=fg, anchor="mm")

        if self.state == "running":
            for b in self.buttons:
                b.draw(draw)

        if core.error:
            draw.text((SCREEN_W // 2, disp_y + disp_h // 2), "ROM error:\n" + core.error,
                       font=FONT_SM, fill=(230, 90, 90), anchor="mm", align="center")

        if self.status_msg and time.time() < self._status_until:
            draw.text((SCREEN_W // 2, disp_y - 16), self.status_msg,
                       font=FONT_SM, fill=accent, anchor="mm")

    def _draw_quickmenu(self, draw):
        draw.rectangle([0, STATUS_BAR_H, SCREEN_W, SCREEN_H], fill=(8, 8, 12))
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 26), "Quick Menu", font=FONT_LG,
                   fill=theme.fg_color(), anchor="mm")
        for b in self.buttons:
            b.draw(draw)
