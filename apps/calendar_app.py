import calendar
import datetime
import json
import os
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT

EVENTS_FILE = os.path.expanduser("~/.kos_calendar.json")
QUICK_EVENTS = ["Meeting", "Birthday", "Reminder", "Appointment"]

GRID_TOP = STATUS_BAR_H + 96
NAV_Y = STATUS_BAR_H + 40
CELL_W = 42
CELL_H = 28
MARGIN = 3


class CalendarApp(App):
    name = "Calendar"
    icon = "\U0001F4C5"

    def on_open(self):
        today = datetime.date.today()
        self.year = today.year
        self.month = today.month
        self.today = today
        self.selected_day = None
        self.events = self._load_events()
        self._build()

    def _load_events(self):
        if os.path.exists(EVENTS_FILE):
            try:
                with open(EVENTS_FILE) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_events(self):
        try:
            with open(EVENTS_FILE, "w") as f:
                json.dump(self.events, f)
        except Exception:
            pass

    def _build(self):
        self.buttons = []
        self.day_cells = []
        weeks = calendar.monthcalendar(self.year, self.month)

        for row, week in enumerate(weeks):
            for col, day in enumerate(week):
                if day == 0:
                    continue
                x = MARGIN + col * (CELL_W + MARGIN)
                y = GRID_TOP + row * (CELL_H + MARGIN)
                self.day_cells.append((x, y, day))
                self.buttons.append(
                    Button(x, y, CELL_W, CELL_H, str(day), self._select_day(day), font=FONT_SM))

        panel_y = GRID_TOP + len(weeks) * (CELL_H + MARGIN) + 10
        self.panel_y = panel_y
        self.buttons.append(Button(10, NAV_Y, 60, 30, "<", self._prev_month, font=FONT_MD))
        self.buttons.append(Button(SCREEN_W - 70, NAV_Y, 60, 30, ">", self._next_month, font=FONT_MD))

        if self.selected_day:
            summary_h = 22
            for i, label in enumerate(QUICK_EVENTS):
                row, col = divmod(i, 2)
                x = 16 + col * ((SCREEN_W - 48) // 2 + 16)
                y = panel_y + summary_h + row * 40
                self.buttons.append(
                    Button(x, y, (SCREEN_W - 48) // 2, 34, label,
                           self._add_event(label), font=FONT_SM))
            clear_y = panel_y + summary_h + 2 * 40 + 4
            self.buttons.append(Button(16, clear_y, (SCREEN_W - 48) // 2, 36,
                                        "Clear day", self._clear_day, font=FONT_SM))
            self.buttons.append(Button(32 + (SCREEN_W - 48) // 2, clear_y,
                                        (SCREEN_W - 48) // 2, 36, "Home", self.os.go_home, font=FONT_SM))
        else:
            self.buttons.append(Button(SCREEN_W // 2 - 60, panel_y, 120, 40,
                                        "Home", self.os.go_home, font=FONT_MD))

    def _date_key(self, day):
        return f"{self.year:04d}-{self.month:02d}-{day:02d}"

    def _select_day(self, day):
        def handler():
            self.selected_day = day
            self._build()
        return handler

    def _add_event(self, label):
        def handler():
            key = self._date_key(self.selected_day)
            self.events.setdefault(key, [])
            self.events[key].append(label)
            self._save_events()
        return handler

    def _clear_day(self):
        key = self._date_key(self.selected_day)
        self.events.pop(key, None)
        self._save_events()

    def _prev_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self.selected_day = None
        self._build()

    def _next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self.selected_day = None
        self._build()

    def draw(self, draw, canvas):
        title = f"{calendar.month_name[self.month]} {self.year}"
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 16), title, font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        headers = ["M", "T", "W", "T", "F", "S", "S"]
        for col, h in enumerate(headers):
            x = MARGIN + col * (CELL_W + MARGIN) + CELL_W / 2
            draw.text((x, GRID_TOP - 12), h, font=FONT_SM, fill=(150, 150, 160), anchor="mm")

        for x, y, day in self.day_cells:
            key = self._date_key(day)
            has_events = key in self.events and self.events[key]
            is_today = (day == self.today.day and self.month == self.today.month
                        and self.year == self.today.year)
            is_selected = day == self.selected_day
            color = ACCENT if is_selected else ((60, 90, 60) if is_today else CARD_COLOR)
            draw.rounded_rectangle([x, y, x + CELL_W, y + CELL_H], radius=6, fill=color)
            draw.text((x + CELL_W / 2, y + CELL_H / 2), str(day), font=FONT_SM,
                       fill=(255, 255, 255), anchor="mm")
            if has_events:
                draw.ellipse([x + CELL_W - 9, y + 2, x + CELL_W - 3, y + 8], fill=(240, 200, 60))

        for b in self.buttons:
            b.draw(draw)

        if self.selected_day:
            key = self._date_key(self.selected_day)
            events_here = self.events.get(key, [])
            summary = ", ".join(events_here) if events_here else "No events"
            draw.text((SCREEN_W // 2, self.panel_y), f"Day {self.selected_day}: {summary}",
                       font=FONT_SM, fill=(220, 220, 230), anchor="mm")
