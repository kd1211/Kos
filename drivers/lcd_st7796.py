"""
Driver for the Waveshare 3.5inch Capacitive Touch LCD.

Panel:  ST7796S, 320 x 480, SPI
Wiring (from the Waveshare wiki's 15PIN Raspberry Pi hookup guide):
    VCC  -> 3.3V/5V   GND -> GND
    DIN  -> MOSI (GPIO10)   CLK -> SCLK (GPIO11)
    CS   -> GPIO8 (CE0)     DC  -> GPIO25
    RST  -> GPIO27          BL  -> GPIO18 (backlight, PWM-capable)

This mirrors the structure of Waveshare's own LCD_xxin_yy.py demo drivers:
a thin SPI command/data layer, an init sequence for the panel, and a
SetWindow + WriteData path for pushing a PIL image to the screen.
"""

import time
import numpy as np
import spidev
import RPi.GPIO as GPIO

# Default pin assignment used throughout Waveshare's Raspberry Pi demos
RST_PIN = 27
DC_PIN = 25
CS_PIN = 8
BL_PIN = 18

WIDTH = 320
HEIGHT = 480


class ST7796:
    def __init__(self, rst=RST_PIN, dc=DC_PIN, cs=CS_PIN, bl=BL_PIN,
                 spi_bus=0, spi_device=0, spi_freq=40000000):
        self.rst = rst
        self.dc = dc
        self.cs = cs
        self.bl = bl
        self.width = WIDTH
        self.height = HEIGHT

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.rst, GPIO.OUT)
        GPIO.setup(self.dc, GPIO.OUT)
        GPIO.setup(self.cs, GPIO.OUT)
        GPIO.setup(self.bl, GPIO.OUT)

        self.spi = spidev.SpiDev(spi_bus, spi_device)
        self.spi.max_speed_hz = spi_freq
        self.spi.mode = 0b00

        self._pwm = GPIO.PWM(self.bl, 1000)
        self._pwm.start(90)  # backlight duty cycle, 0-100

    # -- low level -------------------------------------------------
    def _cmd(self, cmd):
        GPIO.output(self.dc, GPIO.LOW)
        GPIO.output(self.cs, GPIO.LOW)
        self.spi.writebytes([cmd])
        GPIO.output(self.cs, GPIO.HIGH)

    def _data(self, data):
        GPIO.output(self.dc, GPIO.HIGH)
        GPIO.output(self.cs, GPIO.LOW)
        if isinstance(data, int):
            self.spi.writebytes([data])
        else:
            for start in range(0, len(data), 4096):
                self.spi.writebytes(list(data[start:start + 4096]))
        GPIO.output(self.cs, GPIO.HIGH)

    def reset(self):
        GPIO.output(self.rst, GPIO.HIGH)
        time.sleep(0.02)
        GPIO.output(self.rst, GPIO.LOW)
        time.sleep(0.02)
        GPIO.output(self.rst, GPIO.HIGH)
        time.sleep(0.12)

    def set_backlight(self, percent):
        """0-100"""
        self._pwm.ChangeDutyCycle(max(0, min(100, percent)))

    # -- init sequence (standard ST7796S bring-up) ------------------
    def init(self):
        self.reset()
        self._cmd(0x11)  # sleep out
        time.sleep(0.12)

        self._cmd(0x36); self._data(0x48)      # memory access control
        self._cmd(0x3A); self._data(0x55)      # 16-bit color (RGB565)

        self._cmd(0xF0); self._data([0xC3])
        self._cmd(0xF0); self._data([0x96])
        self._cmd(0xB4); self._data([0x01])
        self._cmd(0xB7); self._data([0xC6])
        self._cmd(0xE8); self._data([0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])
        self._cmd(0xC1); self._data([0x06])
        self._cmd(0xC2); self._data([0xA7])
        self._cmd(0xC5); self._data([0x18])

        self._cmd(0xE0)
        self._data([0xF0, 0x09, 0x0B, 0x06, 0x04, 0x15, 0x2F, 0x54,
                     0x42, 0x3C, 0x17, 0x14, 0x18, 0x1B])
        self._cmd(0xE1)
        self._data([0xE0, 0x09, 0x0B, 0x06, 0x04, 0x03, 0x2B, 0x43,
                     0x42, 0x3B, 0x16, 0x14, 0x17, 0x1B])

        self._cmd(0xF0); self._data([0x3C])
        self._cmd(0xF0); self._data([0x69])
        time.sleep(0.12)
        self._cmd(0x21)  # display inversion on
        self._cmd(0x29)  # display on

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        self._cmd(0x2C)

    def display(self, image):
        """Push a PIL.Image (RGB, size == self.width x self.height) to the panel."""
        img = image
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height))
        img = img.convert("RGB")

        arr = np.asarray(img, dtype=np.uint8)
        r = (arr[:, :, 0] >> 3).astype(np.uint16)
        g = (arr[:, :, 1] >> 2).astype(np.uint16)
        b = (arr[:, :, 2] >> 3).astype(np.uint16)
        rgb565 = (r << 11) | (g << 5) | b

        hi = (rgb565 >> 8).astype(np.uint8)
        lo = (rgb565 & 0xFF).astype(np.uint8)
        buf = np.empty(rgb565.size * 2, dtype=np.uint8)
        buf[0::2] = hi.flatten()
        buf[1::2] = lo.flatten()

        self._set_window(0, 0, self.width - 1, self.height - 1)
        self._data(buf.tobytes())

    def close(self):
        self._pwm.stop()
        self.spi.close()
        GPIO.cleanup()
