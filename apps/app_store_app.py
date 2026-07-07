"""
App Store -- browses and installs PiOS apps from a GitHub repo.

--------------------------------------------------------------------------
SETTING UP YOUR OWN STORE REPO
--------------------------------------------------------------------------
Point STORE_REPO_OWNER / STORE_REPO_NAME / STORE_REPO_BRANCH below at any
public GitHub repo. That repo needs one file, `apps.json`, at its root:

Single-file app:
[
  {
    "name": "Dice",
    "class_name": "DiceApp",
    "icon": "\\ud83c\\udfb2",
    "description": "Roll a virtual dice",
    "file": "dice_app.py"
  }
]

Folder package (images, helper modules, etc.):
[
  {
    "name": "Slots",
    "class_name": "SlotsApp",
    "icon": "\\U0001f3b0",
    "description": "Spin the reels",
    "folder": "slots",
    "file": "slots_app.py"
  }
]

- "file" is the main module inside the package (or the only file for
  single-file apps). It must define a class inheriting from ui.framework.App.
- "folder" (optional) names a directory in the repo. The whole folder is
  downloaded into apps/installed/<folder>/ so the app can ship assets and
  extra .py modules. Without "folder", only the single "file" is fetched.
- "files" (optional) is an explicit list of repo paths to download when
  you don't want to rely on the GitHub API to enumerate a folder.
- "class_name" is optional -- if omitted, the Store uses the first App
  subclass it finds in the main file.

Installs are remembered in ~/.pios_installed_apps.json and restored on boot
via load_installed_apps() in main.py.
--------------------------------------------------------------------------
"""

import os
import json
import shutil
import importlib.util
import sys

from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT

STORE_REPO_OWNER = "kd1211"
STORE_REPO_NAME = "Kos-App-Store"
STORE_REPO_BRANCH = "main"
STORE_MANIFEST_PATH = "apps.json"

INSTALL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "installed")
REGISTRY_FILE = os.path.expanduser("~/.pios_installed_apps.json")

ROW_H = 64
_HTTP_HEADERS = {"User-Agent": "PiOS/1.0"}


def _raw_url(path):
    return (f"https://raw.githubusercontent.com/{STORE_REPO_OWNER}/"
            f"{STORE_REPO_NAME}/{STORE_REPO_BRANCH}/{path}")


def _api_url(path):
    base = f"https://api.github.com/repos/{STORE_REPO_OWNER}/{STORE_REPO_NAME}/contents"
    url = f"{base}/{path}?ref={STORE_REPO_BRANCH}"
    return url


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


def entry_key(entry):
    """Stable id for matching store manifest rows to installed registry rows."""
    return entry.get("folder") or entry.get("file")


def installed_main_path(entry):
    """Absolute path to the installed app's main .py module."""
    main_file = entry.get("file")
    if not main_file:
        raise ValueError("Registry entry missing file")
    if entry.get("folder"):
        return os.path.join(INSTALL_DIR, entry["folder"], main_file)
    return os.path.join(INSTALL_DIR, os.path.basename(main_file))


def remove_installed(entry):
    """Delete an installed app from disk (single file or whole folder)."""
    if entry.get("folder"):
        path = os.path.join(INSTALL_DIR, entry["folder"])
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        return
    path = os.path.join(INSTALL_DIR, entry.get("file", ""))
    if os.path.isfile(path):
        os.remove(path)


def _import_app_class(filepath, class_name=None):
    """Load an app module from disk and return its App subclass."""
    filepath = os.path.abspath(filepath)
    pkg_dir = os.path.dirname(filepath)
    if pkg_dir and pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    mod_name = "pios_installed_" + os.path.splitext(os.path.basename(filepath))[0]
    spec = importlib.util.spec_from_file_location(mod_name, filepath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if class_name and hasattr(module, class_name):
        return getattr(module, class_name)
    for attr in vars(module).values():
        if isinstance(attr, type) and issubclass(attr, App) and attr is not App:
            return attr
    raise ValueError("No App subclass found in " + filepath)


def _download_text(url, timeout=12):
    import requests
    resp = requests.get(url, timeout=timeout, headers=_HTTP_HEADERS)
    resp.raise_for_status()
    return resp.text


def _download_bytes(url, timeout=12):
    import requests
    resp = requests.get(url, timeout=timeout, headers=_HTTP_HEADERS)
    resp.raise_for_status()
    return resp.content


def _write_repo_file(repo_path, local_path):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    lower = repo_path.lower()
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".ch8", ".zip")):
        data = _download_bytes(_raw_url(repo_path))
        with open(local_path, "wb") as f:
            f.write(data)
    else:
        text = _download_text(_raw_url(repo_path))
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(text)


def _download_folder_tree(repo_folder, local_dir):
    """Recursively download every file under repo_folder via the GitHub API."""
    import requests
    resp = requests.get(_api_url(repo_folder), timeout=12, headers=_HTTP_HEADERS)
    resp.raise_for_status()
    for item in resp.json():
        name = item["name"]
        if item["type"] == "file":
            repo_path = item["path"]
            _write_repo_file(repo_path, os.path.join(local_dir, name))
        elif item["type"] == "dir":
            _download_folder_tree(item["path"], os.path.join(local_dir, name))


def download_store_package(entry):
    """Fetch a store entry into apps/installed/. Returns local main .py path."""
    os.makedirs(INSTALL_DIR, exist_ok=True)
    folder = entry.get("folder")
    main_file = entry.get("file")
    if not main_file:
        raise ValueError("Store entry missing file")

    if folder:
        local_dir = os.path.join(INSTALL_DIR, folder)
        if os.path.isdir(local_dir):
            shutil.rmtree(local_dir)
        os.makedirs(local_dir, exist_ok=True)

        explicit = entry.get("files")
        if explicit:
            for repo_path in explicit:
                rel = repo_path
                prefix = folder + "/"
                if rel.startswith(prefix):
                    rel = rel[len(prefix):]
                elif rel.startswith(folder + os.sep):
                    rel = rel[len(folder) + 1:]
                _write_repo_file(repo_path, os.path.join(local_dir, rel.replace("/", os.sep)))
        else:
            _download_folder_tree(folder, local_dir)

        local_path = os.path.join(local_dir, main_file)
    else:
        local_name = os.path.basename(main_file)
        local_path = os.path.join(INSTALL_DIR, local_name)
        _write_repo_file(main_file, local_path)

    if not os.path.isfile(local_path):
        raise FileNotFoundError("Main module not found after download: " + local_path)
    return local_path


def registry_row_for(cls, store_entry):
    row = {
        "class_name": cls.__name__,
        "app_name": cls.name,
        "file": store_entry.get("file") or "app.py",
    }
    if store_entry.get("folder"):
        row["folder"] = store_entry["folder"]
    return row


def install_store_entry(os_ref, store_entry):
    """Download, import, register, and persist one store manifest entry."""
    local_path = download_store_package(store_entry)
    cls = _import_app_class(local_path, store_entry.get("class_name"))
    os_ref.register_app(cls)

    key = entry_key(store_entry)
    registry = [e for e in _load_registry() if entry_key(e) != key]
    registry.append(registry_row_for(cls, store_entry))
    _save_registry(registry)
    return cls


def load_installed_apps(os_ref):
    """Called once at boot (from main.py) to re-register apps that were
    installed from the Store in a previous session. Failures for any one
    app are swallowed so a bad download can't stop the OS from booting."""
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for entry in _load_registry():
        try:
            filepath = installed_main_path(entry)
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
                                 headers=_HTTP_HEADERS)
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
            cls = install_store_entry(self.os, entry)
            self.status = f"Installed {cls.name} - find it on Home"
            self._build_list_buttons()
        except Exception as e:
            self.status = f"Install failed: {e}"

    # -- helpers ------------------------------------------------------
    def _registered_app_name(self, entry):
        key = entry_key(entry)
        for r in _load_registry():
            if entry_key(r) == key:
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
