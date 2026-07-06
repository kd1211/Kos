"""
INA219-based battery monitor for the Waveshare UPS HAT (C).

This follows the same calibration/register approach as Waveshare's own
INA219.py demo shipped with the UPS HAT (C): 16V bus range, calibrated
for the onboard 0.1 ohm shunt, giving voltage/current/power, from which
we estimate a single-cell Li-po remaining percentage.

Wiring: the UPS HAT (C) connects via pogo pins straight onto the GPIO
header (I2C1: SDA=GPIO2, SCL=GPIO3). Default I2C address is 0x43.
"""

import time
import smbus2

INA219_ADDR = 0x43

REG_CONFIG = 0x00
REG_SHUNTVOLTAGE = 0x01
REG_BUSVOLTAGE = 0x02
REG_POWER = 0x03
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05


class INA219:
    def __init__(self, i2c_bus=1, addr=INA219_ADDR):
        self.bus = smbus2.SMBus(i2c_bus)
        self.addr = addr
        self._cal_value = 0
        self._current_lsb = 0
        self._power_lsb = 0
        self._set_calibration_16v_5a()

    def _write(self, reg, value):
        self.bus.write_i2c_block_data(self.addr, reg, [(value >> 8) & 0xFF, value & 0xFF])

    def _read(self, reg):
        data = self.bus.read_i2c_block_data(self.addr, reg, 2)
        return (data[0] << 8) | data[1]

    def _set_calibration_16v_5a(self):
        # Matches Waveshare's demo constants for the UPS HAT (C) 0.1 ohm shunt
        self._current_lsb = 0.1524  # mA per bit
        self._cal_value = 26868
        self._power_lsb = 0.003048  # W per bit

        self._write(REG_CALIBRATION, self._cal_value)
        config = 0x1FFF  # 32V range placeholder bits, bus/shunt cont. mode
        self._write(REG_CONFIG, config)

    def bus_voltage_v(self):
        raw = self._read(REG_BUSVOLTAGE)
        return (raw >> 3) * 0.004

    def shunt_voltage_mv(self):
        raw = self._read(REG_SHUNTVOLTAGE)
        if raw > 32767:
            raw -= 65536
        return raw * 0.01

    def current_ma(self):
        self._write(REG_CALIBRATION, self._cal_value)
        raw = self._read(REG_CURRENT)
        if raw > 32767:
            raw -= 65536
        return raw * self._current_lsb

    def power_w(self):
        self._write(REG_CALIBRATION, self._cal_value)
        raw = self._read(REG_POWER)
        if raw > 32767:
            raw -= 65536
        return raw * self._power_lsb

    def percent(self):
        """Rough single-cell Li-po SoC estimate from voltage, 3.0V-4.2V range."""
        v = self.bus_voltage_v()
        pct = (v - 3.0) / (4.2 - 3.0) * 100
        return max(0, min(100, round(pct)))

    def read_all(self):
        return {
            "voltage": round(self.bus_voltage_v(), 2),
            "current_ma": round(self.current_ma(), 1),
            "power_w": round(self.power_w(), 2),
            "percent": self.percent(),
            "charging": self.current_ma() > 0,
        }

    def close(self):
        self.bus.close()


if __name__ == "__main__":
    ina = INA219()
    while True:
        print(ina.read_all())
        time.sleep(1)
