"""
A standard CHIP-8 interpreter.

CHIP-8 is a simple, well-documented virtual machine from the 1970s with a
64x32 1-bit display, 16 general-purpose 8-bit registers, and a 16-key hex
keypad. Its small size makes it one of the only "emulator" targets that
comfortably runs on something as modest as a Pi Zero-class board, and
there is a large body of freely redistributable / public-domain CHIP-8
software, unlike console emulation which involves copyrighted BIOS/ROM
files.

This module only implements the interpreter itself; apps/emulator_app.py
handles ROM selection, rendering the display, and the on-screen keypad.
"""

import random

FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,  # 0
    0x20, 0x60, 0x20, 0x20, 0x70,  # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0,  # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0,  # 3
    0x90, 0x90, 0xF0, 0x10, 0x10,  # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0,  # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0,  # 6
    0xF0, 0x10, 0x20, 0x40, 0x40,  # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0,  # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0,  # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90,  # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0,  # B
    0xF0, 0x80, 0x80, 0x80, 0xF0,  # C
    0xE0, 0x90, 0x90, 0x90, 0xE0,  # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0,  # E
    0xF0, 0x80, 0xF0, 0x80, 0x80,  # F
]
FONT_ADDR = 0x50

DISPLAY_W = 64
DISPLAY_H = 32


class Chip8:
    def __init__(self):
        self.memory = bytearray(4096)
        self.memory[FONT_ADDR:FONT_ADDR + len(FONTSET)] = bytes(FONTSET)
        self.v = [0] * 16
        self.i = 0
        self.pc = 0x200
        self.stack = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.display = [0] * (DISPLAY_W * DISPLAY_H)
        self.keys = [False] * 16
        self.draw_flag = True
        self._timer_acc = 0.0
        self.loaded = False
        self.error = None

    def load_rom(self, path):
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > len(self.memory) - 0x200:
            raise ValueError("ROM too large for CHIP-8 memory")
        self.memory[0x200:0x200 + len(data)] = data
        self.loaded = True

    def update_timers(self, dt):
        self._timer_acc += dt
        while self._timer_acc >= 1 / 60:
            if self.delay_timer > 0:
                self.delay_timer -= 1
            if self.sound_timer > 0:
                self.sound_timer -= 1
            self._timer_acc -= 1 / 60

    def cycle(self):
        if not self.loaded or self.error:
            return
        try:
            opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
            self.pc = (self.pc + 2) & 0xFFF
            self._execute(opcode)
        except Exception as e:  # a malformed/unsupported ROM shouldn't crash the OS
            self.error = str(e)

    def _execute(self, opcode):
        v = self.v
        nnn = opcode & 0x0FFF
        nn = opcode & 0x00FF
        n = opcode & 0x000F
        x = (opcode >> 8) & 0xF
        y = (opcode >> 4) & 0xF
        top = (opcode & 0xF000) >> 12

        if top == 0x0:
            if opcode == 0x00E0:
                self.display = [0] * (DISPLAY_W * DISPLAY_H)
                self.draw_flag = True
            elif opcode == 0x00EE:
                self.pc = self.stack.pop()
        elif top == 0x1:
            self.pc = nnn
        elif top == 0x2:
            self.stack.append(self.pc)
            self.pc = nnn
        elif top == 0x3:
            if v[x] == nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x4:
            if v[x] != nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x5:
            if v[x] == v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0x6:
            v[x] = nn
        elif top == 0x7:
            v[x] = (v[x] + nn) & 0xFF
        elif top == 0x8:
            if n == 0x0:
                v[x] = v[y]
            elif n == 0x1:
                v[x] |= v[y]
            elif n == 0x2:
                v[x] &= v[y]
            elif n == 0x3:
                v[x] ^= v[y]
            elif n == 0x4:
                total = v[x] + v[y]
                v[0xF] = 1 if total > 255 else 0
                v[x] = total & 0xFF
            elif n == 0x5:
                v[0xF] = 1 if v[x] >= v[y] else 0
                v[x] = (v[x] - v[y]) & 0xFF
            elif n == 0x6:
                v[0xF] = v[x] & 0x1
                v[x] = (v[x] >> 1) & 0xFF
            elif n == 0x7:
                v[0xF] = 1 if v[y] >= v[x] else 0
                v[x] = (v[y] - v[x]) & 0xFF
            elif n == 0xE:
                v[0xF] = (v[x] >> 7) & 0x1
                v[x] = (v[x] << 1) & 0xFF
        elif top == 0x9:
            if v[x] != v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif top == 0xA:
            self.i = nnn
        elif top == 0xB:
            self.pc = (nnn + v[0]) & 0xFFF
        elif top == 0xC:
            v[x] = random.randint(0, 255) & nn
        elif top == 0xD:
            x_coord, y_coord = v[x] % DISPLAY_W, v[y] % DISPLAY_H
            v[0xF] = 0
            for row in range(n):
                sprite_byte = self.memory[(self.i + row) & 0xFFF]
                for col in range(8):
                    if sprite_byte & (0x80 >> col):
                        px = (x_coord + col) % DISPLAY_W
                        py = (y_coord + row) % DISPLAY_H
                        idx = py * DISPLAY_W + px
                        if self.display[idx] == 1:
                            v[0xF] = 1
                        self.display[idx] ^= 1
            self.draw_flag = True
        elif top == 0xE:
            if nn == 0x9E:
                if self.keys[v[x] & 0xF]:
                    self.pc = (self.pc + 2) & 0xFFF
            elif nn == 0xA1:
                if not self.keys[v[x] & 0xF]:
                    self.pc = (self.pc + 2) & 0xFFF
        elif top == 0xF:
            if nn == 0x07:
                v[x] = self.delay_timer
            elif nn == 0x0A:
                pressed = next((i for i in range(16) if self.keys[i]), None)
                if pressed is not None:
                    v[x] = pressed
                else:
                    self.pc = (self.pc - 2) & 0xFFF
            elif nn == 0x15:
                self.delay_timer = v[x]
            elif nn == 0x18:
                self.sound_timer = v[x]
            elif nn == 0x1E:
                self.i = (self.i + v[x]) & 0xFFF
            elif nn == 0x29:
                self.i = FONT_ADDR + (v[x] & 0xF) * 5
            elif nn == 0x33:
                val = v[x]
                self.memory[self.i] = val // 100
                self.memory[(self.i + 1) & 0xFFF] = (val // 10) % 10
                self.memory[(self.i + 2) & 0xFFF] = val % 10
            elif nn == 0x55:
                for idx in range(x + 1):
                    self.memory[(self.i + idx) & 0xFFF] = v[idx]
            elif nn == 0x65:
                for idx in range(x + 1):
                    v[idx] = self.memory[(self.i + idx) & 0xFFF]
