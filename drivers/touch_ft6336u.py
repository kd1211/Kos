"""
Touch driver for the FT6336U capacitive touch controller used on the
Waveshare 3.5inch Capacitive Touch LCD (I2C interface, INT on GPIO).

Wiring (from the wiki's 15PIN hookup):
    TP_SDA -> GPIO2 (SDA)   TP_SCL -> GPIO3 (SCL)
    TP_INT -> GPIO17 (optional, we just poll here for simplicity)

Register map matches the FT6336U datasheet Waveshare ships with the demo:
    0x02 -> number of touch points
    0x03 -> XH (bits 3:0) | event flag (bits 7:6)
    0x04 -> XL
    0x05 -> YH
    0x06 -> YL
"""

import smbus2

FT6336_ADDR = 0x38

REG_NUM_TOUCHES = 0x02
REG_P1_XH = 0x03
REG_P1_XL = 0x04
REG_P1_YH = 0x05
REG_P1_YL = 0x06


class FT6336U:
    def __init__(self, i2c_bus=1, addr=FT6336_ADDR, width=320, height=480,
                 swap_xy=False, invert_x=False, invert_y=False):
        self.bus = smbus2.SMBus(i2c_bus)
        self.addr = addr
        self.width = width
        self.height = height
        self.swap_xy = swap_xy
        self.invert_x = invert_x
        self.invert_y = invert_y

    def read_point(self):
        """Return (x, y) of the first touch point, or None if no touch."""
        try:
            data = self.bus.read_i2c_block_data(self.addr, REG_NUM_TOUCHES, 6)
        except OSError:
            return None

        touches = data[0] & 0x0F
        if touches == 0:
            return None

        x = ((data[1] & 0x0F) << 8) | data[2]
        y = ((data[3] & 0x0F) << 8) | data[4]

        if self.swap_xy:
            x, y = y, x
        if self.invert_x:
            x = self.width - 1 - x
        if self.invert_y:
            y = self.height - 1 - y

        return (x, y)

    def close(self):
        self.bus.close()
