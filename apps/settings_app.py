"""
Settings -- sections:
  Display        - backlight brightness, auto-sleep (screen timeout)
  Sound          - master volume, sound on/off, tap-click feedback
  Theme          - pick from several full-OS color palettes, live preview
  Wallpaper      - a gradient preset, a photo from ~/Pictures, or none
  Wi-Fi & BT     - toggle Wi-Fi / Bluetooth radios
  Security       - PIN lock enable/disable + change PIN (numeric keypad)
  Date/Time      - 12h vs 24h clock
  Installed Apps - manage apps installed from the App Store / .phoneapp files
  Developer      - developer mode toggle (status-bar DEV tag + extra info)
  About          - version info + reset everything to defaults

Every control here writes straight through ui.theme (persisted to
~/.kos_settings.json), so other apps/screens read the same live values
immediately -- no reboot needed to see a new theme, wallpaper, or volume.
The PIN itself is enforced by the OS lock screen in ui/framework.py.

The main menu and the Installed Apps / Wallpaper lists use a drag
ScrollArea (see ui/framework.py) instead of a fixed grid, since the menu
alone is taller than the screen -- tapping still works normally, and a
drag scrolls instead of firing whatever row it started on.
"""

import os
import shutil
import time
from ui import theme, sound
from ui.wallpaper import WALLPAPER_CHOICES, GRADIENTS
from ui.framework import App, Button, Keyboard, ScrollArea, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_MD, FONT_SM, FONT_LG, ACCENT
from ui import net_control
from apps.app_store_app import _load_registry, _save_registry, INSTALL_DIR

TOP = STATUS_BAR_H + 20
PICTURES_DIR = os.path.expanduser("~/Pictures")

MENU_ITEMS = [
    ("display", "\U0001F506", "Display"),
    ("sound", "\U0001F50A", "Sound"),
    ("theme", "\U0001F3A8", "Theme"),
    ("wallpaper", "\U0001F5BC", "Wallpaper"),
    ("wifi", "\U0001F4F6", "Wi-Fi"),
    ("bluetooth", "\U0001F517", "Bluetooth"),
    ("security", "\U0001F512", "Security"),
    ("datetime", "\U0001F550", "Date & Time"),
    ("apps", "\U0001F4E6", "Installed Apps"),
    ("developer", "\U0001F6E0", "Developer"),
    ("power", "\u23FB", "Power"),
    ("about", "\u2139", "About"),
]

SLEEP_CHOICES = [(0, "Off"), (30, "30s"), (60, "1m"), (120, "2m"), (300, "5m")]
NUMPAD_LABELS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "\u232B"]
KEYBOARD_H = 188

SCROLL_SECTIONS = {"menu", "apps", "wallpaper", "wallpaper_photos", "wifi", "bluetooth"}
SCROLL_Y0 = TOP + 20
SCROLL_Y1 = SCREEN_H - 58


class SettingsApp(App):
    name = "Settings"
    icon = "\u2699"

    @property
    def wants_animation(self):
        # keep polling/redrawing while a scan or connect/pair is actually
        # in flight, so status updates from the background thread in
        # ui/net_control show up without needing a touch -- everywhere
        # else in Settings is static and doesn't need this
        if self.section in ("wifi", "bluetooth"):
            snap = net_control.wifi.snapshot() if self.section == "wifi" \
                else net_control.bluetooth.snapshot()
            return snap["scanning"] or snap["busy"]
        return False

    def on_open(self):
        self.section = "menu"
        self._pin_draft = ""
        self._pin_stage = None
        self._pin_pending = None
        self._pin_error = None
        self._press_row = None
        self._press_start = None
        self._pending_uninstall = None
        self.scroll = ScrollArea(0, SCROLL_Y0, SCREEN_W, SCROLL_Y1 - SCROLL_Y0)
        self._scroll_rows = []

        self._wifi_target = None       # network dict awaiting password/action
        self._wifi_password = ""
        self._wifi_keyboard = None
        self._bt_target = None         # device dict awaiting an action
        self._power_action = None
        self.status_flash = None
        self._renaming_device = False
        self._device_name_draft = ""
        self._rename_keyboard = None

        self._build_menu()

    # -- navigation -----------------------------------------------------
    def _goto(self, section):
        def handler():
            self.section = section
            {
                "menu": self._build_menu,
                "display": self._build_display,
                "sound": self._build_sound,
                "theme": self._build_theme,
                "wallpaper": self._build_wallpaper,
                "wifi": self._build_wifi,
                "bluetooth": self._build_bluetooth,
                "security": self._build_security,
                "datetime": self._build_datetime,
                "apps": self._build_apps,
                "developer": self._build_developer,
                "power": self._build_power,
                "about": self._build_about,
            }[section]()
        return handler

    def _back_button(self):
        return Button(16, SCREEN_H - 60, 90, 42, "Back", self._goto("menu"), font=FONT_SM)

    def _home_button(self, x):
        return Button(x, SCREEN_H - 60, 90, 42, "Home", self.os.go_home, font=FONT_SM)

    # -- scroll dispatch (menu / apps / wallpaper / wallpaper_photos / wifi / bluetooth) --
    def _scroll_on_tap(self, x, y):
        if self.section not in SCROLL_SECTIONS:
            return super().on_tap(x, y)

        for b in self.buttons:
            if b.contains(x, y):
                b.on_tap()
                return True

        self._press_row = None
        self._press_start = (x, y)
        if self.scroll.contains(x, y):
            self.scroll.begin_drag(y)
            content_y = (y - self.scroll.y) + self.scroll.offset
            for row in self._scroll_rows:
                label, handler, ry, rh = row[0], row[1], row[2], row[3]
                if ry <= content_y <= ry + rh and 20 <= x <= SCREEN_W - 20:
                    self._press_row = handler
                    break
        return True

    def on_touch_move(self, x, y):
        if self.section not in SCROLL_SECTIONS or self._press_start is None:
            return
        self.scroll.drag_to(y)

    def on_touch_up(self):
        if self.section not in SCROLL_SECTIONS:
            return
        self.scroll.end_drag()
        if not self.scroll.was_drag() and self._press_row is not None:
            self._press_row()
        self._press_row = None
        self._press_start = None

    def _set_scroll_rows(self, rows, top=None):
        """rows: list of (label, handler) or (label, handler, meta) tuples.
        meta is an optional dict a section-specific draw method can use
        for extra per-row decoration (signal bars, connected badges).
        `top` lets a section reserve header space (e.g. a radio toggle)
        above the scrollable list instead of using the shared default."""
        self._scroll_rows = []
        y = 0
        row_h = 48
        for row in rows:
            if len(row) == 3:
                label, handler, meta = row
            else:
                label, handler = row
                meta = None
            self._scroll_rows.append((label, handler, y, row_h - 8, meta))
            y += row_h
        y0 = SCROLL_Y0 if top is None else top
        self.scroll = ScrollArea(0, y0, SCREEN_W, SCREEN_H - 58 - y0)
        self.scroll.set_content_height(y)

    def _draw_scroll_rows(self, draw, extra_draw=None):
        for i, (label, handler, ry, rh, meta) in enumerate(self._scroll_rows):
            sy = self.scroll.y + (ry - self.scroll.offset)
            if sy + rh < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                continue
            draw.rounded_rectangle([20, sy, SCREEN_W - 20, sy + rh], radius=12,
                                    fill=theme.card_color())
            draw.text((34, sy + rh // 2), label, font=FONT_SM,
                       fill=theme.fg_color(), anchor="lm")
            if extra_draw:
                extra_draw(draw, i, sy, rh, meta)
        self.scroll.draw_scrollbar(draw, theme.accent_color())

    # -- menu -------------------------------------------------------------
    def _build_menu(self):
        rows = [(f"{icon}  {label}", self._goto(key)) for key, icon, label in MENU_ITEMS]
        self._set_scroll_rows(rows)
        self.buttons = [
            Button(SCREEN_W // 2 - 60, SCREEN_H - 46, 120, 40, "Home", self.os.go_home, font=FONT_SM)
        ]

    # -- display ------------------------------------------------------
    def _build_display(self):
        self.buttons = [
            Button(30, TOP + 130, 70, 55, "-10", self._adjust_brightness(-10), font=FONT_MD),
            Button(SCREEN_W - 100, TOP + 130, 70, 55, "+10", self._adjust_brightness(10), font=FONT_MD),
        ]
        y = TOP + 230
        n = len(SLEEP_CHOICES)
        margin = 10
        cell_w = (SCREEN_W - margin * (n + 1)) // n
        for i, (secs, label) in enumerate(SLEEP_CHOICES):
            x = margin + i * (cell_w + margin)
            self.buttons.append(
                Button(x, y, cell_w, 44, label, self._set_sleep_timeout(secs), font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2 - 90, y + 70, 180, 44, "Sleep now", self._sleep_now, font=FONT_SM))
        self.buttons.append(self._back_button())
        self.buttons.append(self._home_button(SCREEN_W - 106))

    def _adjust_brightness(self, delta):
        def handler():
            b = max(10, min(100, theme.get("brightness") + delta))
            theme.set("brightness", b)
            try:
                self.os.lcd.set_backlight(b)
            except Exception:
                pass
        return handler

    def _set_sleep_timeout(self, secs):
        def handler():
            theme.set("sleep_timeout", secs)
        return handler

    def _sleep_now(self):
        self.os.enter_sleep(theme.get("brightness"))

    # -- sound ------------------------------------------------------------
    def _build_sound(self):
        self.buttons = [
            Button(30, TOP + 130, 70, 55, "-10", self._adjust_volume(-10), font=FONT_MD),
            Button(SCREEN_W - 100, TOP + 130, 70, 55, "+10", self._adjust_volume(10), font=FONT_MD),
            Button(SCREEN_W // 2 - 140, TOP + 220, 280, 46,
                   self._sound_label(), self._toggle_sound, font=FONT_SM),
            Button(SCREEN_W // 2 - 140, TOP + 276, 280, 46,
                   self._click_label(), self._toggle_click, font=FONT_SM),
            self._back_button(),
            self._home_button(SCREEN_W - 106),
        ]

    def _sound_label(self):
        return f"Sound: {'On' if theme.get('sound_enabled') else 'Off'}"

    def _click_label(self):
        return f"Tap sounds: {'On' if theme.get('click_sound') else 'Off'}"

    def _adjust_volume(self, delta):
        def handler():
            v = max(0, min(100, theme.get("volume") + delta))
            theme.set("volume", v)
            sound.refresh_volume()
            sound.click()
        return handler

    def _toggle_sound(self):
        theme.set("sound_enabled", not theme.get("sound_enabled"))
        self._build_sound()

    def _toggle_click(self):
        theme.set("click_sound", not theme.get("click_sound"))
        self._build_sound()
        sound.click()

    # -- theme ------------------------------------------------------------
    def _build_theme(self):
        self.buttons = []
        names = theme.PRESET_NAMES
        y = TOP + 60
        for i, name in enumerate(names):
            self.buttons.append(
                Button(20, y, SCREEN_W - 40, 44, name, self._set_theme(name), font=FONT_SM))
            y += 50
        self.buttons.append(self._back_button())
        self.buttons.append(self._home_button(SCREEN_W - 106))

    def _set_theme(self, name):
        def handler():
            theme.set("theme", name)
        return handler

    # -- wallpaper ------------------------------------------------------------
    def _build_wallpaper(self):
        current = theme.get("wallpaper")
        rows = []
        for choice in WALLPAPER_CHOICES:
            label = choice
            if choice == current:
                label = f"\u2713 {choice}"
            rows.append((label, self._pick_wallpaper(choice)))
        self._set_scroll_rows(rows)
        self.buttons = [self._back_button(), self._home_button(SCREEN_W - 106)]

    def _pick_wallpaper(self, choice):
        def handler():
            if choice == "Custom Photo":
                self._build_wallpaper_photos()
            else:
                theme.set("wallpaper", choice)
                self._build_wallpaper()
        return handler

    def _build_wallpaper_photos(self):
        self.section = "wallpaper_photos"
        try:
            names = sorted(f for f in os.listdir(PICTURES_DIR)
                           if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")))
        except Exception:
            names = []
        rows = [(name, self._set_photo_wallpaper(name)) for name in names]
        if not rows:
            rows = [("No photos in ~/Pictures yet", lambda: None)]
        self._set_scroll_rows(rows)
        self.buttons = [self._back_button(), self._home_button(SCREEN_W - 106)]
        self.buttons[0] = Button(16, SCREEN_H - 60, 90, 42, "Back", self._goto("wallpaper"), font=FONT_SM)

    def _set_photo_wallpaper(self, filename):
        def handler():
            theme.set("wallpaper_path", os.path.join(PICTURES_DIR, filename))
            theme.set("wallpaper", "Custom Photo")
            self.section = "wallpaper"
            self._build_wallpaper()
        return handler

    # -- Wi-Fi ----------------------------------------------------------------
    def _build_wifi(self):
        self.section = "wifi"
        net_control.wifi.scan_async()
        self._refresh_wifi_rows()
        self.buttons = [
            Button(16, TOP + 20, SCREEN_W - 32 - 74, 40, self._wifi_toggle_label(),
                   self._toggle_wifi_radio, font=FONT_SM),
            Button(SCREEN_W - 90, TOP + 20, 74, 40, "Scan", self._start_wifi_scan, font=FONT_SM),
            self._back_button(), self._home_button(SCREEN_W - 106),
        ]

    def _wifi_toggle_label(self):
        on = net_control.wifi.is_radio_on()
        if on is None:
            return "Wi-Fi: (unavailable)"
        return f"Wi-Fi: {'On' if on else 'Off'}  \u2013  tap to {'disable' if on else 'enable'}"

    def _toggle_wifi_radio(self):
        on = net_control.wifi.is_radio_on()
        net_control.wifi.set_radio(not on)
        self.buttons[0].label = self._wifi_toggle_label()

    def _refresh_wifi_rows(self):
        snap = net_control.wifi.snapshot()
        rows = []
        for n in snap["networks"]:
            label = n["ssid"]
            if n["connected"]:
                label += "  (connected)"
            rows.append((label, self._wifi_row_tap(n), n))
        if snap["scanning"]:
            rows.append(("Scanning\u2026", lambda: None, None))
        elif not rows:
            msg = snap["status"] or "No networks found - tap Scan to try again"
            rows.append((msg, self._start_wifi_scan, None))
        self._set_scroll_rows(rows, top=TOP + 72)

    def _start_wifi_scan(self):
        net_control.wifi.scan_async()
        self._refresh_wifi_rows()

    def _wifi_row_tap(self, network):
        def handler():
            if network["connected"]:
                self._wifi_target = network
                self._build_wifi_actions()
            elif network["secure"]:
                self._wifi_target = network
                self._wifi_password = ""
                self._wifi_keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
                self.section = "wifi_password"
                self._build_wifi_password_buttons()
            else:
                net_control.wifi.connect_async(network["ssid"])
                self._refresh_wifi_rows()
        return handler

    def _build_wifi_password_buttons(self):
        y0 = TOP + 8
        self.buttons = [
            Button(16, y0 + 100, 90, 34, "Cancel", self._cancel_wifi_password, font=FONT_SM),
            Button(SCREEN_W - 106, y0 + 100, 90, 34, "Connect", self._submit_wifi_password, font=FONT_SM),
        ]

    def _wifi_password_key(self, val):
        if val == "BACKSPACE":
            self._wifi_password = self._wifi_password[:-1]
        elif val == "ENTER":
            self._submit_wifi_password()
        elif len(self._wifi_password) < 63:
            self._wifi_password += val

    def _cancel_wifi_password(self):
        self._wifi_target = None
        self.section = "wifi"
        self._build_wifi()

    def _submit_wifi_password(self):
        net_control.wifi.connect_async(self._wifi_target["ssid"], self._wifi_password)
        self._wifi_target = None
        self.section = "wifi"
        self._build_wifi()

    def _build_wifi_actions(self):
        self.section = "wifi_actions"
        ssid = self._wifi_target["ssid"]
        y = SCREEN_H // 2 - 60
        self.buttons = [
            Button(SCREEN_W // 2 - 110, y, 220, 44, "Disconnect",
                   self._wifi_disconnect_target, font=FONT_MD),
            Button(SCREEN_W // 2 - 110, y + 54, 220, 44, "Forget This Network",
                   self._wifi_forget_target, font=FONT_MD, bg=(150, 60, 60)),
            Button(SCREEN_W // 2 - 110, y + 108, 220, 40, "Cancel",
                   self._cancel_wifi_action, font=FONT_SM),
        ]
        self._wifi_actions_ssid = ssid

    def _wifi_disconnect_target(self):
        net_control.wifi.disconnect_async(self._wifi_target["ssid"])
        self._cancel_wifi_action()

    def _wifi_forget_target(self):
        net_control.wifi.forget_async(self._wifi_target["ssid"])
        self._cancel_wifi_action()

    def _cancel_wifi_action(self):
        self._wifi_target = None
        self.section = "wifi"
        self._build_wifi()

    # -- Bluetooth --------------------------------------------------------------
    def _build_bluetooth(self):
        self.section = "bluetooth"
        net_control.bluetooth.scan_async()
        self._refresh_bt_rows()
        self.buttons = [
            Button(16, TOP + 20, SCREEN_W - 32 - 74, 40, self._bt_toggle_label(),
                   self._toggle_bt_power, font=FONT_SM),
            Button(SCREEN_W - 90, TOP + 20, 74, 40, "Scan", self._start_bt_scan, font=FONT_SM),
            self._back_button(), self._home_button(SCREEN_W - 106),
        ]

    def _bt_toggle_label(self):
        on = net_control.bluetooth.is_powered_on()
        if on is None:
            return "Bluetooth: (unavailable)"
        return f"Bluetooth: {'On' if on else 'Off'}  \u2013  tap to {'disable' if on else 'enable'}"

    def _toggle_bt_power(self):
        on = net_control.bluetooth.is_powered_on()
        net_control.bluetooth.set_power(not on)
        self.buttons[0].label = self._bt_toggle_label()

    def _refresh_bt_rows(self):
        snap = net_control.bluetooth.snapshot()
        rows = []
        for d in snap["devices"]:
            label = d["name"]
            if d.get("connected"):
                label += "  (connected)"
            elif d.get("paired"):
                label += "  (paired)"
            rows.append((label, self._bt_row_tap(d), d))
        if snap["scanning"]:
            rows.append(("Scanning\u2026", lambda: None, None))
        elif not rows:
            msg = snap["status"] or "No devices found - tap Scan to try again"
            rows.append((msg, self._start_bt_scan, None))
        self._set_scroll_rows(rows, top=TOP + 72)

    def _start_bt_scan(self):
        net_control.bluetooth.scan_async()
        self._refresh_bt_rows()

    def _bt_row_tap(self, device):
        def handler():
            self._bt_target = device
            if device.get("connected"):
                self._build_bt_actions()
            elif device.get("paired"):
                net_control.bluetooth.connect_async(device["mac"])
                self._refresh_bt_rows()
            else:
                net_control.bluetooth.pair_async(device["mac"])
                self._refresh_bt_rows()
        return handler

    def _build_bt_actions(self):
        self.section = "bt_actions"
        y = SCREEN_H // 2 - 60
        self.buttons = [
            Button(SCREEN_W // 2 - 110, y, 220, 44, "Disconnect",
                   self._bt_disconnect_target, font=FONT_MD),
            Button(SCREEN_W // 2 - 110, y + 54, 220, 44, "Remove Device",
                   self._bt_remove_target, font=FONT_MD, bg=(150, 60, 60)),
            Button(SCREEN_W // 2 - 110, y + 108, 220, 40, "Cancel",
                   self._cancel_bt_action, font=FONT_SM),
        ]

    def _bt_disconnect_target(self):
        net_control.bluetooth.disconnect_async(self._bt_target["mac"])
        self._cancel_bt_action()

    def _bt_remove_target(self):
        net_control.bluetooth.remove_async(self._bt_target["mac"])
        self._cancel_bt_action()

    def _cancel_bt_action(self):
        self._bt_target = None
        self.section = "bluetooth"
        self._build_bluetooth()

    # -- tap dispatch: password keyboard needs its own hook ------------------
    def on_tap(self, x, y):
        if self.section == "wifi_password" and \
                self._wifi_keyboard.on_tap(x, y, self._wifi_password_key):
            return True
        if self.section == "device_rename" and \
                self._rename_keyboard.on_tap(x, y, self._device_rename_key):
            return True
        if self.section not in SCROLL_SECTIONS:
            return super().on_tap(x, y)
        return self._scroll_on_tap(x, y)

    # -- Security / PIN lock -------------------------------------------------
    def _build_security(self):
        self.buttons = []
        pin_on = theme.get("pin_enabled")
        y = TOP + 60
        label = "Disable PIN Lock" if pin_on else "Enable PIN Lock"
        self.buttons.append(Button(20, y, SCREEN_W - 40, 46, label, self._toggle_pin_lock, font=FONT_SM))
        if pin_on:
            self.buttons.append(
                Button(20, y + 56, SCREEN_W - 40, 46, "Change PIN", self._start_change_pin, font=FONT_SM))
        self.buttons.append(self._back_button())
        self.buttons.append(self._home_button(SCREEN_W - 106))

    def _toggle_pin_lock(self):
        if theme.get("pin_enabled"):
            self._start_verify("disable")
        else:
            if theme.get("pin_code"):
                theme.set("pin_enabled", True)
                self._build_security()
            else:
                self._start_setpin("enable")

    def _start_change_pin(self):
        self._start_verify("change")

    def _start_verify(self, pending):
        self.section = "security_verify"
        self._pin_draft = ""
        self._pin_error = None
        self._pin_pending = pending
        self._build_pin_screen()

    def _build_pin_screen(self):
        self.buttons = []
        cols, rows = 3, 4
        bw, bh = 78, 50
        gap = 10
        grid_w = cols * bw + (cols - 1) * gap
        x0 = (SCREEN_W - grid_w) // 2
        y0 = TOP + 140
        for i, lab in enumerate(NUMPAD_LABELS):
            r, c = divmod(i, cols)
            x = x0 + c * (bw + gap)
            y = y0 + r * (bh + gap)
            self.buttons.append(Button(x, y, bw, bh, lab, self._pin_key(lab), font=FONT_MD))
        self.buttons.append(Button(16, SCREEN_H - 50, 90, 38, "Cancel", self._cancel_pin_flow, font=FONT_SM))

    def _pin_key(self, lab):
        def handler():
            if lab == "C":
                self._pin_draft = ""
            elif lab == "\u232B":
                self._pin_draft = self._pin_draft[:-1]
            elif len(self._pin_draft) < 4:
                self._pin_draft += lab
                if len(self._pin_draft) == 4:
                    self._pin_submit()
        return handler

    def _pin_submit(self):
        if self.section == "security_verify":
            if self._pin_draft == theme.get("pin_code"):
                pending = self._pin_pending
                self._pin_error = None
                if pending == "disable":
                    theme.set("pin_enabled", False)
                    self.section = "security"
                    self._build_security()
                else:
                    self._start_setpin("change")
            else:
                self._pin_error = "Incorrect PIN"
                self._pin_draft = ""
        else:
            theme.set("pin_code", self._pin_draft)
            theme.set("pin_enabled", True)
            self.section = "security"
            self._build_security()

    def _start_setpin(self, pending):
        self.section = "security_setpin"
        self._pin_draft = ""
        self._pin_error = None
        self._pin_pending = pending
        self._build_pin_screen()

    def _cancel_pin_flow(self):
        self.section = "security"
        self._pin_draft = ""
        self._pin_error = None
        self._build_security()

    # -- date & time --------------------------------------------------
    def _build_datetime(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 140, TOP + 100, 280, 50,
                   self._clock_label(), self._toggle_clock_format, font=FONT_MD),
            self._back_button(),
            self._home_button(SCREEN_W - 106),
        ]

    def _clock_label(self):
        return "24-hour clock" if theme.get("clock_24h") else "12-hour clock"

    def _toggle_clock_format(self):
        theme.set("clock_24h", not theme.get("clock_24h"))
        self._build_datetime()

    # -- installed apps -------------------------------------------------------
    def _build_apps(self):
        self.section = "apps"
        registry = _load_registry()
        rows = [(entry.get("app_name", "?"), self._confirm_uninstall(entry)) for entry in registry]
        if not rows:
            rows = [("No apps installed yet (try the App Store)", lambda: None)]
        self._set_scroll_rows(rows)
        self.buttons = [self._back_button(), self._home_button(SCREEN_W - 106)]

    def _confirm_uninstall(self, entry):
        def handler():
            self._pending_uninstall = entry
            self.section = "apps_confirm_uninstall"
            self.buttons = [
                Button(SCREEN_W // 2 - 130, SCREEN_H // 2 + 10, 120, 46, "Uninstall",
                       self._do_uninstall, font=FONT_MD, bg=(180, 60, 60)),
                Button(SCREEN_W // 2 + 10, SCREEN_H // 2 + 10, 120, 46, "Cancel",
                       self._goto("apps"), font=FONT_MD),
            ]
        return handler

    def _do_uninstall(self):
        entry = self._pending_uninstall
        if entry:
            try:
                filepath = os.path.join(INSTALL_DIR, entry.get("file"))
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
            registry = [e for e in _load_registry() if e.get("file") != entry.get("file")]
            _save_registry(registry)
            name = entry.get("app_name")
            if name in self.os.apps:
                del self.os.apps[name]
        self._pending_uninstall = None
        self.section = "apps"
        self._build_apps()

    # -- developer mode ---------------------------------------------------
    def _build_developer(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 140, TOP + 110, 280, 50,
                   self._dev_label(), self._toggle_dev, font=FONT_MD),
            self._back_button(),
            self._home_button(SCREEN_W - 106),
        ]

    def _dev_label(self):
        return f"Developer Mode: {'On' if theme.get('developer_mode') else 'Off'}"

    def _toggle_dev(self):
        theme.set("developer_mode", not theme.get("developer_mode"))
        self._build_developer()

    # -- power --------------------------------------------------------------
    def _build_power(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 100, TOP + 60, 200, 46,
                   "Restart Kos", self._confirm_restart, font=FONT_SM),
            Button(SCREEN_W // 2 - 100, TOP + 116, 200, 46,
                   "Shut Down", self._confirm_shutdown, font=FONT_SM, bg=(150, 60, 60)),
            self._back_button(),
            self._home_button(SCREEN_W - 106),
        ]

    def _confirm_restart(self):
        self.section = "power_confirm"
        self._power_action = "restart"
        self.buttons = [
            Button(SCREEN_W // 2 - 130, SCREEN_H // 2 + 10, 120, 46, "Restart",
                   self._do_restart, font=FONT_MD, bg=(180, 120, 40)),
            Button(SCREEN_W // 2 + 10, SCREEN_H // 2 + 10, 120, 46, "Cancel",
                   self._goto("power"), font=FONT_MD),
        ]

    def _confirm_shutdown(self):
        self.section = "power_confirm"
        self._power_action = "shutdown"
        self.buttons = [
            Button(SCREEN_W // 2 - 130, SCREEN_H // 2 + 10, 120, 46, "Shut Down",
                   self._do_shutdown, font=FONT_MD, bg=(180, 60, 60)),
            Button(SCREEN_W // 2 + 10, SCREEN_H // 2 + 10, 120, 46, "Cancel",
                   self._goto("power"), font=FONT_MD),
        ]

    def _do_restart(self):
        import subprocess
        try:
            self.os.lcd.close()
        except Exception:
            pass
        try:
            subprocess.Popen(["sudo", "reboot"])
        except Exception:
            # not on real hardware / no sudo -- just restart the OS process
            import sys
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _do_shutdown(self):
        import subprocess
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"], timeout=5)
        except Exception as e:
            self.section = "power"
            self._build_power()
            self.status_flash = f"Shutdown unavailable: {e}"

    # -- about ------------------------------------------------------------
    def _build_about(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 100, SCREEN_H - 190, 200, 40,
                   "Rename This Device", self._start_device_rename, font=FONT_SM),
            Button(SCREEN_W // 2 - 100, SCREEN_H - 140, 200, 44,
                   "Reset all settings", self._reset, font=FONT_SM),
            self._back_button(),
            self._home_button(SCREEN_W - 106),
        ]

    def _start_device_rename(self):
        self.section = "device_rename"
        self._device_name_draft = theme.get("device_name") or "Kos Device"
        self._rename_keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self.buttons = [
            Button(16, SCREEN_H - KEYBOARD_H - 44, 90, 36, "Cancel", self._cancel_device_rename, font=FONT_SM),
            Button(SCREEN_W - 106, SCREEN_H - KEYBOARD_H - 44, 90, 36, "Save", self._save_device_rename, font=FONT_SM),
        ]

    def _device_rename_key(self, val):
        if val == "BACKSPACE":
            self._device_name_draft = self._device_name_draft[:-1]
        elif val == "ENTER":
            self._save_device_rename()
        elif len(self._device_name_draft) < 24:
            self._device_name_draft += val

    def _cancel_device_rename(self):
        self.section = "about"
        self._build_about()

    def _save_device_rename(self):
        theme.set("device_name", self._device_name_draft.strip() or "Kos Device")
        self.section = "about"
        self._build_about()

    def _reset(self):
        theme.reset()
        self._build_about()

    # -- drawing ------------------------------------------------------------
    def draw(self, draw, canvas):
        titles = {"menu": "Settings", "display": "Display", "sound": "Sound",
                  "theme": "Theme", "wallpaper": "Wallpaper",
                  "wallpaper_photos": "Choose a Photo", "wifi": "Wi-Fi",
                  "wifi_password": "Enter Wi-Fi Password", "wifi_actions": "Network",
                  "bluetooth": "Bluetooth", "bt_actions": "Device",
                  "security": "Security", "security_verify": "Enter Current PIN",
                  "security_setpin": "Set New PIN", "datetime": "Date & Time",
                  "apps": "Installed Apps", "apps_confirm_uninstall": "Confirm Uninstall",
                  "developer": "Developer", "power": "Power",
                  "power_confirm": "Confirm", "device_rename": "Rename This Device",
                  "about": "About"}
        draw.text((SCREEN_W // 2, TOP), titles.get(self.section, "Settings"),
                   font=FONT_LG, fill=theme.fg_color(), anchor="mm")

        if self.section == "wifi":
            self._draw_wifi_rows(draw)
        elif self.section == "bluetooth":
            self._draw_bt_rows(draw)
        elif self.section in SCROLL_SECTIONS:
            self._draw_scroll_rows(draw)
        elif self.section == "display":
            self._draw_display(draw)
        elif self.section == "sound":
            self._draw_sound(draw)
        elif self.section == "theme":
            self._draw_theme(draw)
        elif self.section == "wifi_password":
            self._draw_wifi_password(draw)
        elif self.section == "wifi_actions":
            self._draw_wifi_actions(draw)
        elif self.section == "bt_actions":
            self._draw_bt_actions(draw)
        elif self.section in ("security_verify", "security_setpin"):
            self._draw_pin_screen(draw)
        elif self.section == "apps_confirm_uninstall":
            self._draw_confirm_uninstall(draw)
        elif self.section == "power_confirm":
            self._draw_power_confirm(draw)
        elif self.section == "power":
            self._draw_power(draw)
        elif self.section == "device_rename":
            self._draw_device_rename(draw)
        elif self.section == "about":
            self._draw_about(draw)

        for b in self.buttons:
            b.draw(draw)

    def _draw_display(self, draw):
        b = theme.get("brightness")
        draw.text((SCREEN_W // 2, TOP + 40), "Backlight", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        bar_x0, bar_x1 = 30, SCREEN_W - 30
        bar_y0, bar_y1 = TOP + 70, TOP + 100
        draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=10, fill=theme.card_color())
        fill_w = int((bar_x1 - bar_x0) * b / 100)
        draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + fill_w, bar_y1],
                                radius=10, fill=theme.accent_color())
        draw.text((SCREEN_W // 2, TOP + 157), f"{b}%", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")

        draw.text((SCREEN_W // 2, TOP + 200), "Auto-sleep after", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        current = theme.get("sleep_timeout")
        for btn, (secs, label) in zip(self.buttons[2:2 + len(SLEEP_CHOICES)], SLEEP_CHOICES):
            btn.bg = theme.accent_color() if secs == current else theme.card_color()

    def _draw_sound(self, draw):
        v = theme.get("volume")
        draw.text((SCREEN_W // 2, TOP + 40), "Volume", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        bar_x0, bar_x1 = 30, SCREEN_W - 30
        bar_y0, bar_y1 = TOP + 70, TOP + 100
        draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=10, fill=theme.card_color())
        fill_w = int((bar_x1 - bar_x0) * v / 100)
        draw.rounded_rectangle([bar_x0, bar_y0, bar_x0 + fill_w, bar_y1],
                                radius=10, fill=theme.accent_color())
        draw.text((SCREEN_W // 2, TOP + 157), f"{v}%", font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        self.buttons[2].label = self._sound_label()
        self.buttons[3].label = self._click_label()

    def _draw_theme(self, draw):
        current = theme.get("theme")
        for btn, name in zip(self.buttons, theme.PRESET_NAMES):
            palette = theme.PRESETS[name]
            swatch_x = btn.x + btn.w - 34
            draw.ellipse([swatch_x, btn.y + 12, swatch_x + 20, btn.y + 32], fill=palette["accent"])
            btn.bg = theme.accent_color() if name == current else theme.card_color()

    def _draw_pin_screen(self, draw):
        n = len(self._pin_draft)
        dot_gap = 34
        x0 = SCREEN_W // 2 - dot_gap * 3 // 2
        cy = TOP + 60
        for i in range(4):
            cx = x0 + i * dot_gap
            filled = i < n
            color = theme.accent_color() if filled else theme.card_color()
            draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=color, outline=theme.fg_color())
        if self._pin_error:
            draw.text((SCREEN_W // 2, TOP + 92), self._pin_error, font=FONT_SM,
                       fill=(230, 90, 90), anchor="mm")

    def _draw_confirm_uninstall(self, draw):
        name = self._pending_uninstall.get("app_name", "?") if self._pending_uninstall else "?"
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 40), f"Uninstall \"{name}\"?",
                   font=FONT_MD, fill=(230, 90, 90), anchor="mm", align="center")

    # -- Wi-Fi / Bluetooth row decoration -------------------------------------
    def _signal_bars(self, signal):
        if signal >= 85:
            return 4
        if signal >= 60:
            return 3
        if signal >= 30:
            return 2
        return 1

    def _draw_wifi_rows(self, draw):
        for label, handler, ry, rh, meta in self._scroll_rows:
            sy = self.scroll.y + (ry - self.scroll.offset)
            if sy + rh < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                continue
            connected = bool(meta and meta.get("connected"))
            bg = theme.accent_color() if connected else theme.card_color()
            draw.rounded_rectangle([20, sy, SCREEN_W - 20, sy + rh], radius=12, fill=bg)
            draw.text((34, sy + rh // 2), label, font=FONT_SM, fill=(255, 255, 255) if connected
                       else theme.fg_color(), anchor="lm")
            if meta:
                icon_x = SCREEN_W - 34
                if meta.get("secure"):
                    draw.text((icon_x, sy + rh // 2), "\U0001F512", font=FONT_SM,
                               fill=theme.fg_color(), anchor="mm")
                    icon_x -= 22
                bars = self._signal_bars(meta.get("signal", 0))
                for b in range(4):
                    bh = 4 + b * 3
                    bx = icon_x - 16 + b * 6
                    by = sy + rh // 2 + 7 - bh
                    color = theme.fg_color() if b < bars else (110, 110, 118)
                    draw.rectangle([bx, by, bx + 4, sy + rh // 2 + 7], fill=color)
        self.scroll.draw_scrollbar(draw, theme.accent_color())

    def _draw_bt_rows(self, draw):
        for label, handler, ry, rh, meta in self._scroll_rows:
            sy = self.scroll.y + (ry - self.scroll.offset)
            if sy + rh < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                continue
            connected = bool(meta and meta.get("connected"))
            bg = theme.accent_color() if connected else theme.card_color()
            draw.rounded_rectangle([20, sy, SCREEN_W - 20, sy + rh], radius=12, fill=bg)
            draw.text((34, sy + rh // 2), label, font=FONT_SM, fill=(255, 255, 255) if connected
                       else theme.fg_color(), anchor="lm")
            if meta and meta.get("paired") and not connected:
                draw.text((SCREEN_W - 34, sy + rh // 2), "\u2713", font=FONT_SM,
                           fill=theme.fg_color(), anchor="mm")
        self.scroll.draw_scrollbar(draw, theme.accent_color())

    def _draw_wifi_password(self, draw):
        ssid = self._wifi_target["ssid"] if self._wifi_target else ""
        draw.text((SCREEN_W // 2, TOP + 34), ssid, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")
        draw.rounded_rectangle([16, TOP + 56, SCREEN_W - 16, TOP + 96], radius=8,
                                fill=theme.card_color())
        shown = "\u2022" * len(self._wifi_password)
        draw.text((26, TOP + 76), shown or "Password", font=FONT_SM,
                   fill=theme.fg_color() if shown else (140, 140, 150), anchor="lm")
        self._wifi_keyboard.draw(draw)

    def _draw_wifi_actions(self, draw):
        ssid = self._wifi_target["ssid"] if self._wifi_target else ""
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 90), ssid, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")

    def _draw_bt_actions(self, draw):
        name = self._bt_target["name"] if self._bt_target else ""
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 90), name, font=FONT_MD,
                   fill=theme.fg_color(), anchor="mm")

    def _draw_power(self, draw):
        if self.status_flash:
            draw.text((SCREEN_W // 2, TOP + 180), self.status_flash, font=FONT_SM,
                       fill=(230, 90, 90), anchor="mm", align="center")

    def _draw_power_confirm(self, draw):
        if self._power_action == "shutdown":
            text = "Shut down Kos?\nMake sure you're ready to\nunplug or press the power button."
            color = (230, 90, 90)
        else:
            text = "Restart Kos?"
            color = (230, 170, 60)
        draw.text((SCREEN_W // 2, SCREEN_H // 2 - 50), text, font=FONT_MD,
                   fill=color, anchor="mm", align="center")

    def _draw_device_rename(self, draw):
        draw.rounded_rectangle([16, TOP + 30, SCREEN_W - 16, TOP + 70], radius=8,
                                fill=theme.card_color())
        draw.text((26, TOP + 50), self._device_name_draft or "Device name", font=FONT_SM,
                   fill=theme.fg_color(), anchor="lm")
        self._rename_keyboard.draw(draw)

    def _draw_about(self, draw):
        try:
            total, used, free = shutil.disk_usage("/")
            storage_line = f"Storage: {used // (1024**3)}GB used / {total // (1024**3)}GB"
        except Exception:
            storage_line = "Storage: unavailable"

        lines = [
            theme.get("device_name") or "Kos Device", "",
            "A tiny touchscreen OS for the",
            "Raspberry Pi + Waveshare 3.5\"",
            "LCD and UPS HAT (C).", "",
            f"Theme: {theme.get('theme')}",
            f"Sound: {'On' if theme.get('sound_enabled') else 'Off'}",
            storage_line,
        ]
        y = TOP + 44
        for line in lines:
            draw.text((SCREEN_W // 2, y), line, font=FONT_SM, fill=theme.fg_color(), anchor="mm")
            y += 22
