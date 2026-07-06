import shutil
import subprocess
import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, FONT_SM, CARD_COLOR, ACCENT


def _cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def _uptime():
    try:
        with open("/proc/uptime") as f:
            secs = float(f.read().split()[0])
        h, rem = divmod(int(secs), 3600)
        m, _ = divmod(rem, 60)
        return f"{h}h {m}m"
    except Exception:
        return "n/a"


def _disk_usage():
    try:
        total, used, free = shutil.disk_usage("/")
        return f"{used // (2**30)} / {total // (2**30)} GB used"
    except Exception:
        return "n/a"


def _mem_usage():
    try:
        out = subprocess.check_output(["free", "-m"]).decode()
        line = out.splitlines()[1].split()
        used, total = int(line[2]), int(line[1])
        return f"{used} / {total} MB"
    except Exception:
        return "n/a"


class SysInfoApp(App):
    name = "System"
    icon = "\u2139"

    def on_open(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 60, SCREEN_H - 60, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD)
        ]

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 20
        draw.text((SCREEN_W // 2, top), "System Info", font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        temp = _cpu_temp()
        rows = [
            ("CPU temp", f"{temp} \u00b0C" if temp is not None else "n/a"),
            ("Uptime", _uptime()),
            ("Storage", _disk_usage()),
            ("Memory", _mem_usage()),
        ]
        y = top + 40
        for label, value in rows:
            draw.rectangle([20, y, SCREEN_W - 20, y + 40], fill=CARD_COLOR)
            draw.text((30, y + 20), label, font=FONT_SM, fill=(200, 200, 210), anchor="lm")
            draw.text((SCREEN_W - 30, y + 20), value, font=FONT_SM, fill=ACCENT, anchor="rm")
            y += 46

        for b in self.buttons:
            b.draw(draw)
