"""
Adapts the standalone CHIP-8 interpreter (emulators/chip8.py, unchanged)
to the EmulatorCore interface so the RetroArch-style frontend can drive
it generically -- ROM browsing, save states, rewind, and fast-forward
all live in apps/emulator_app.py and know nothing CHIP-8-specific.
"""

from emulators.chip8 import Chip8, DISPLAY_W, DISPLAY_H
from emulators.core_base import EmulatorCore, register

KEY_LAYOUT = [
    ["1", "2", "3", "C"],
    ["4", "5", "6", "D"],
    ["7", "8", "9", "E"],
    ["A", "0", "B", "F"],
]

_LABEL_TO_INDEX = {label: int(label, 16) for row in KEY_LAYOUT for label in row}


@register
class Chip8Core(EmulatorCore):
    core_id = "chip8"
    display_name = "CHIP-8"
    extensions = (".ch8",)
    input_layout = KEY_LAYOUT
    display_size = (DISPLAY_W, DISPLAY_H)
    on_color = (210, 235, 210)
    off_color = (12, 24, 14)

    def __init__(self):
        self.cpu = Chip8()
        self.cycles_per_frame = 8

    def load(self, path):
        self.cpu.load_rom(path)

    def run_frame(self, dt, fast_forward=False):
        cycles = self.cycles_per_frame * (4 if fast_forward else 1)
        for _ in range(cycles):
            self.cpu.cycle()
        self.cpu.update_timers(dt)

    def get_display(self):
        return self.cpu.display

    def press(self, label):
        idx = _LABEL_TO_INDEX.get(label)
        if idx is not None:
            self.cpu.keys[idx] = True

    def release(self, label):
        idx = _LABEL_TO_INDEX.get(label)
        if idx is not None:
            self.cpu.keys[idx] = False

    def is_sound_active(self):
        return self.cpu.sound_timer > 0

    @property
    def error(self):
        return self.cpu.error

    def save_state(self):
        c = self.cpu
        return {
            "memory": list(c.memory),
            "v": list(c.v),
            "i": c.i,
            "pc": c.pc,
            "stack": list(c.stack),
            "delay_timer": c.delay_timer,
            "sound_timer": c.sound_timer,
            "display": list(c.display),
            "keys": list(c.keys),
        }

    def load_state(self, state):
        c = self.cpu
        c.memory = bytearray(state["memory"])
        c.v = list(state["v"])
        c.i = state["i"]
        c.pc = state["pc"]
        c.stack = list(state["stack"])
        c.delay_timer = state["delay_timer"]
        c.sound_timer = state["sound_timer"]
        c.display = list(state["display"])
        c.keys = list(state["keys"])
        c.loaded = True
        c.error = None
