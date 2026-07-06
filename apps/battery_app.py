from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_LG, FONT_MD, CARD_COLOR, ACCENT


class BatteryApp(App):
    name = "Battery"
    icon = "\u26A1"

    def on_open(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 60, SCREEN_H - 70, 120, 45,
                   "Home", self.os.go_home)
        ]

    def draw(self, draw, canvas):
        data = self.os._read_battery()
        top = STATUS_BAR_H + 30

        draw.text((SCREEN_W // 2, top), "Battery", font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        pct = data.get("percent", 0)
        cx, cy, r = SCREEN_W // 2, top + 100, 70
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(80, 80, 90), width=6)
        color = (80, 220, 120) if pct > 20 else (230, 90, 90)
        draw.arc([cx - r, cy - r, cx + r, cy + r], start=-90,
                  end=-90 + 360 * pct / 100, fill=color, width=6)
        draw.text((cx, cy), f"{pct}%", font=FONT_LG, fill=(255, 255, 255), anchor="mm")

        rows = [
            ("Voltage", f"{data.get('voltage', 0)} V"),
            ("Current", f"{data.get('current_ma', 0)} mA"),
            ("Power", f"{data.get('power_w', 0)} W"),
            ("Status", "Charging" if data.get("charging") else "On battery"),
        ]
        y = cy + r + 30
        for label, value in rows:
            draw.rectangle([20, y, SCREEN_W - 20, y + 34], fill=CARD_COLOR)
            draw.text((30, y + 17), label, font=FONT_MD, fill=(200, 200, 210), anchor="lm")
            draw.text((SCREEN_W - 30, y + 17), value, font=FONT_MD, fill=ACCENT, anchor="rm")
            y += 40

        for b in self.buttons:
            b.draw(draw)
