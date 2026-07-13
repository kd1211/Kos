import json
import os
import time
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, FONT_XL, CARD_COLOR, ACCENT

CONFIG_FILE = os.path.expanduser("~/.kos_weather.json")

CITIES = [
    ("New York", 40.71, -74.01),
    ("London", 51.51, -0.13),
    ("Tokyo", 35.68, 139.69),
    ("Sydney", -33.87, 151.21),
]

# WMO weather codes -> (description, emoji), per Open-Meteo's documented code table
WMO_CODES = {
    0: ("Clear sky", "\u2600"),
    1: ("Mainly clear", "\U0001F324"),
    2: ("Partly cloudy", "\u26C5"),
    3: ("Overcast", "\u2601"),
    45: ("Fog", "\U0001F32B"),
    48: ("Fog", "\U0001F32B"),
    51: ("Light drizzle", "\U0001F326"),
    61: ("Light rain", "\U0001F327"),
    63: ("Rain", "\U0001F327"),
    65: ("Heavy rain", "\U0001F327"),
    71: ("Light snow", "\U0001F328"),
    75: ("Heavy snow", "\U0001F328"),
    80: ("Rain showers", "\U0001F326"),
    95: ("Thunderstorm", "\u26C8"),
}


class WeatherApp(App):
    name = "Weather"
    icon = "\u26C5"

    def on_open(self):
        self.city = self._load_city()
        self.data = None
        self.status = "Tap Refresh to fetch weather"
        self._build_buttons()

    def _load_city(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    return json.load(f).get("city", CITIES[0][0])
            except Exception:
                pass
        return CITIES[0][0]

    def _save_city(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"city": self.city}, f)
        except Exception:
            pass

    def _build_buttons(self):
        self.buttons = []
        top = STATUS_BAR_H + 20 + 215
        for i, (name, lat, lon) in enumerate(CITIES):
            row, col = divmod(i, 2)
            x = 16 + col * ((SCREEN_W - 48) // 2 + 16)
            y = top + row * 42
            self.buttons.append(
                Button(x, y, (SCREEN_W - 48) // 2, 36, name, self._pick_city(name), font=FONT_SM))

        controls_y = top + 2 * 42 + 10
        self.buttons.append(
            Button(16, controls_y, (SCREEN_W - 48) // 2, 40, "Refresh", self._fetch, font=FONT_SM))
        self.buttons.append(
            Button(32 + (SCREEN_W - 48) // 2, controls_y, (SCREEN_W - 48) // 2, 40,
                   "Home", self.os.go_home, font=FONT_SM))

    def _pick_city(self, name):
        def handler():
            self.city = name
            self._save_city()
            self._fetch()
        return handler

    def _fetch(self):
        try:
            import requests
        except ImportError:
            self.status = "The 'requests' package isn't installed"
            return

        coords = next((c for c in CITIES if c[0] == self.city), CITIES[0])
        _, lat, lon = coords
        url = (f"https://api.open-meteo.com/v1/forecast?"
               f"latitude={lat}&longitude={lon}&current_weather=true")
        try:
            resp = requests.get(url, timeout=6)
            resp.raise_for_status()
            payload = resp.json()
            self.data = payload.get("current_weather")
            self.status = f"Updated {time.strftime('%H:%M')}"
        except Exception as e:
            self.status = f"Couldn't fetch weather: {e}"

    def draw(self, draw, canvas):
        top = STATUS_BAR_H + 20
        draw.text((SCREEN_W // 2, top), self.city, font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        if self.data:
            temp = self.data.get("temperature")
            wind = self.data.get("windspeed")
            code = self.data.get("weathercode")
            desc, emoji = WMO_CODES.get(code, ("Unknown", "\u2753"))

            draw.text((SCREEN_W // 2, top + 60), emoji, font=FONT_XL,
                       fill=(255, 255, 255), anchor="mm")
            draw.text((SCREEN_W // 2, top + 110), f"{temp}\u00b0C", font=FONT_XL,
                       fill=ACCENT, anchor="mm")
            draw.text((SCREEN_W // 2, top + 145), desc, font=FONT_MD,
                       fill=(220, 220, 230), anchor="mm")
            draw.text((SCREEN_W // 2, top + 170), f"Wind {wind} km/h", font=FONT_SM,
                       fill=(180, 180, 190), anchor="mm")
        else:
            draw.text((SCREEN_W // 2, top + 90), "No data yet", font=FONT_MD,
                       fill=(180, 180, 190), anchor="mm")

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20 + 195), self.status, font=FONT_SM,
                   fill=(150, 150, 160), anchor="mm")

        for b in self.buttons:
            b.draw(draw)
