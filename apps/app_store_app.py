"""
App Store -- browses and installs single-file Kos apps from a GitHub repo.

--------------------------------------------------------------------------
SETTING UP YOUR OWN STORE REPO
--------------------------------------------------------------------------
Point STORE_REPO_OWNER / STORE_REPO_NAME / STORE_REPO_BRANCH below at any
public GitHub repo. That repo needs one file, `apps.json`, at its root:

[
  {
    "name": "Dice",
    "class_name": "DiceApp",
    "icon": "\\ud83c\\udfb2",
    "description": "Roll a virtual dice",
    "file": "dice_app.py"
  }
]

- "file" is the path (relative to the repo root) to a single-file app
  written the same way as anything in this project's apps/ folder: a
  module that defines a class inheriting from ui.framework.App.
- "class_name" is optional -- if omitted, the Store just uses the first
  App subclass it finds in the file.

Tapping "Install" downloads that file into apps/installed/, imports it,
and registers it live so it shows up on the Home screen immediately. The
choice is remembered in ~/.kos_installed_apps.json so it's restored
automatically on the next boot (see load_installed_apps() below, which
main.py calls at startup).
--------------------------------------------------------------------------
"""

import os
import json
import importlib.util

from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT

STORE_REPO_OWNER = "kd1211"
STORE_REPO_NAME = "Kos-App-Store"
STORE_REPO_BRANCH = "main"
STORE_MANIFEST_PATH = "apps.json"

INSTALL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "installed")
REGISTRY_FILE = os.path.expanduser("~/.kos_installed_apps.json")

ROW_H = 64


def _raw_url(path):
    return (f"https://raw.githubusercontent.com/{STORE_REPO_OWNER}/"
            f"{STORE_REPO_NAME}/{STORE_REPO_BRANCH}/{path}")


def _load_registry():
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_registry(entries):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(entries, f)


def _import_app_class(filepath, class_name=None):
    """Load a single-file app module from disk and return its App subclass."""
    mod_name = "kos_installed_" + os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if class_name and hasattr(module, class_name):
        return getattr(module, class_name)
    for attr in vars(module).values():
        if isinstance(attr, type) and issubclass(attr, App) and attr is not App:
            return attr
    raise ValueError("No App subclass found in " + filepath)


def load_installed_apps(os_ref):
    """Called once at boot (from main.py) to re-register apps that were
    installed from the Store in a previous session. Failures for any one
    app are swallowed so a bad download can't stop the OS from booting."""
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for entry in _load_registry():
        try:
            filepath = os.path.join(INSTALL_DIR, entry["file"])
            cls = _import_app_class(filepath, entry.get("class_name"))
            os_ref.register_app(cls)
        except Exception as e:
            print(f"[AppStore] Skipping {entry.get('app_name', '?')}: {e}")


class AppStoreApp(App):
    name = "App Store"
    icon = "\U0001F6D2"

    def on_open(self):
        self.state = "loading"
        self.entries = []
        self.status = None
        self.buttons = []
        self._fetch_manifest()

    # -- networking ------------------------------------------------------
    def _fetch_manifest(self):
        try:
            import requests
        except ImportError:
            self.state = "error"
            self.status = "The 'requests' package isn't installed"
            self._build_error_buttons()
            return
        try:
            resp = requests.get(_raw_url(STORE_MANIFEST_PATH), timeout=8,
                                 headers={"User-Agent": "Kos/1.0"})
            resp.raise_for_status()
            self.entries = resp.json()
            self.state = "list"
            self._build_list_buttons()
        except Exception as e:
            self.state = "error"
            self.status = f"Couldn't reach store: {e}"
            self._build_error_buttons()

    def _install(self, entry):
        try:
            import requests
        except ImportError:
            self.status = "The 'requests' package isn't installed"
            return
        try:
            file_rel = entry["file"]
            resp = requests.get(_raw_url(file_rel), timeout=10,
                                 headers={"User-Agent": "Kos/1.0"})
            resp.raise_for_status()

            os.makedirs(INSTALL_DIR, exist_ok=True)
            local_name = os.path.basename(file_rel)
            local_path = os.path.join(INSTALL_DIR, local_name)
            with open(local_path, "w") as f:
                f.write(resp.text)

            cls = _import_app_class(local_path, entry.get("class_name"))
            self.os.register_app(cls)

            registry = [e for e in _load_registry() if e.get("file") != local_name]
            registry.append({"file": local_name, "class_name": cls.__name__,
                              "app_name": cls.name})
            _save_registry(registry)

            self.status = f"Installed {cls.name} - find it on Home"
            self._build_list_buttons()
        except Exception as e:
            self.status = f"Install failed: {e}"

    # -- helpers ------------------------------------------------------
    def _registered_app_name(self, entry):
        for r in _load_registry():
            if r.get("file") == entry.get("file"):
                return r.get("app_name")
        return None

    def _open_installed(self, app_name):
        if app_name in self.os.apps:
            self.os.open_app(app_name)

    # -- buttons ------------------------------------------------------
    def _build_error_buttons(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 60, STATUS_BAR_H + 120, 120, 44,
                   "Retry", self.on_open, font=FONT_SM),
            Button(SCREEN_W // 2 - 60, SCREEN_H - 60, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD),
        ]

    def _build_list_buttons(self):
        self.buttons = []
        top = STATUS_BAR_H + 50
        for i, entry in enumerate(self.entries):
            y = top + i * ROW_H
            if y > SCREEN_H - 70:
                break
            app_name = self._registered_app_name(entry)
            if app_name:
                self.buttons.append(
                    Button(SCREEN_W - 106, y + 8, 90, 34, "Open",
                           (lambda n=app_name: self._open_installed(n)), font=FONT_SM))
            else:
                self.buttons.append(
                    Button(SCREEN_W - 106, y + 8, 90, 34, "Install",
                           (lambda e=entry: self._install(e)), font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2 - 60, SCREEN_H - 58, 120, 42,
                   "Home", self.os.go_home, font=FONT_SM))

    # -- drawing ------------------------------------------------------
    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 22), "App Store", font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")

        if self.state == "loading":
            draw.text((SCREEN_W // 2, SCREEN_H // 2), "Loading store...",
                       font=FONT_SM, fill=(180, 180, 190), anchor="mm")
            return

        if self.state == "error":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 80), self.status or "Error",
                       font=FONT_SM, fill=(230, 90, 90), anchor="mm", align="center")
            for b in self.buttons:
                b.draw(draw)
            return

        top = STATUS_BAR_H + 50
        for i, entry in enumerate(self.entries):
            y = top + i * ROW_H
            if y > SCREEN_H - 70:
                break
            draw.rounded_rectangle([12, y, SCREEN_W - 12, y + ROW_H - 8],
                                    radius=10, fill=CARD_COLOR)
            icon = entry.get("icon", "\U0001F4E6")
            draw.text((32, y + (ROW_H - 8) // 2), icon, font=FONT_LG,
                       fill=(255, 255, 255), anchor="mm")
            draw.text((56, y + 16), entry.get("name", "?"), font=FONT_SM,
                       fill=(255, 255, 255), anchor="lm")
            desc = entry.get("description", "")
            draw.text((56, y + 38), desc[:32], font=FONT_SM,
                       fill=(170, 170, 180), anchor="lm")

        if not self.entries:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 90), "No apps in the store yet",
                       font=FONT_SM, fill=(170, 170, 180), anchor="mm")

        if self.status:
            draw.text((SCREEN_W // 2, SCREEN_H - 76), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm")

        for b in self.buttons:
            b.draw(draw)
