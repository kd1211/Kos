"""
Builds roms/demo.ch8 -- an original, hand-assembled CHIP-8 program that
draws the interpreter's built-in 0-F hex-digit sprites in a 4x4 grid on
screen, then halts. It exists purely to prove the interpreter works
without needing any third-party ROM. Run this script to regenerate the
file:  python3 scripts/make_demo_rom.py
"""

import os

FONT_ADDR = 0x50


def assemble():
    program = bytearray()
    start_addr = 0x200

    for digit in range(16):
        col, row = digit % 4, digit // 4
        x_coord = col * 10
        y_coord = row * 8
        i_addr = FONT_ADDR + digit * 5

        # ANNN - LD I, i_addr
        program += bytes([0xA0 | ((i_addr >> 8) & 0x0F), i_addr & 0xFF])
        # 6XNN - LD V0, x_coord
        program += bytes([0x60, x_coord & 0xFF])
        # 6YNN - LD V1, y_coord
        program += bytes([0x61, y_coord & 0xFF])
        # DXYN - DRW V0, V1, 5
        program += bytes([0xD0, 0x15])

    # 1NNN - JP to self (infinite loop / halt)
    halt_addr = start_addr + len(program)
    program += bytes([0x10 | ((halt_addr >> 8) & 0x0F), halt_addr & 0xFF])

    return bytes(program)


if __name__ == "__main__":
    rom = assemble()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "roms")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "demo.ch8")
    with open(out_path, "wb") as f:
        f.write(rom)
    print(f"Wrote {len(rom)} bytes to {out_path}")
