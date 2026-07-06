"""
System Updater -- checks a GitHub repo (this project's own source) for a
newer version, downloads it as a zip, and swaps it in. Keeps exactly one
previous version around in ~/.pios_backup so a bad update can be rolled
back with one tap.

Update repo layout expected (configurable below):
  - a `version.txt` file at the repo root containing a single version
    string, e.g. "1.2.0"
  - the repo's default branch zipball is downloaded and extracted wholesale

This mirrors the App Store's "best effort, never brick the boot" design:
every network/filesystem step is wrapped so failures just show a status
message instead of crashing.
"""

import os
import shutil
import zipfile
import tempfile

from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT

UPDATE_REPO_OWNER = "your-github-username"
UPDATE_REPO_NAME = "pios"
UPDATE_REPO_BRANCH = "main"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION_FILE = os.path.join(PROJECT_ROOT, "version.txt")
BACKUP_DIR = os.path.expanduser("~/.pios_backup")
CURRENT_VERSION_DEFAULT = "0.0.0"


def _current_version():
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip()
    except Exception:
        return CURRENT_VERSION_DEFAULT


class SystemUpdaterApp(App):
    name = "System Updater"
    icon = "\u2B06"

    def on_open(self):
        self.state = "menu"
        self.status = None
        self.remote_version = None
        self._build_menu()

    def _build_menu(self):
        self.buttons = [
            Button(SCREEN_W // 2 - 110, STATUS_BAR_H + 140, 220, 44,
                   "Check for updates", self._check, font=FONT_SM),
            Button(SCREEN_W // 2 - 110, STATUS_BAR_H + 200, 220, 44,
                   "Roll back last update", self._rollback, font=FONT_SM),
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD),
        ]

    def _raw_url(self, path):
        return (f"https://raw.githubusercontent.com/{UPDATE_REPO_OWNER}/"
                f"{UPDATE_REPO_NAME}/{UPDATE_REPO_BRANCH}/{path}")

    def _zip_url(self):
        return (f"https://github.com/{UPDATE_REPO_OWNER}/{UPDATE_REPO_NAME}/"
                f"archive/refs/heads/{UPDATE_REPO_BRANCH}.zip")

    def _check(self):
        try:
            import requests
        except ImportError:
            self.status = "The 'requests' package isn't installed"
            return
        try:
            resp = requests.get(self._raw_url("version.txt"), timeout=8,
                                 headers={"User-Agent": "PiOS/1.0"})
            resp.raise_for_status()
            self.remote_version = resp.text.strip()
            current = _current_version()
            if self.remote_version and self.remote_version != current:
                self.status = f"Update available: {current} -> {self.remote_version}"
                self.buttons.insert(0, Button(
                    SCREEN_W // 2 - 110, STATUS_BAR_H + 80, 220, 44,
                    "Install update", self._install, font=FONT_SM))
            else:
                self.status = f"Already up to date ({current})"
        except Exception as e:
            self.status = f"Couldn't check: {e}"

    def _install(self):
        try:
            import requests
        except ImportError:
            self.status = "The 'requests' package isn't installed"
            return
        try:
            self.status = "Downloading update..."
            resp = requests.get(self._zip_url(), timeout=30,
                                 headers={"User-Agent": "PiOS/1.0"})
            resp.raise_for_status()

            with tempfile.TemporaryDirectory() as tmp:
                zip_path = os.path.join(tmp, "update.zip")
                with open(zip_path, "wb") as f:
                    f.write(resp.content)
                with zipfile.ZipFile(zip_path) as zf:
                    zf.extractall(tmp)
                extracted = [d for d in os.listdir(tmp)
                             if os.path.isdir(os.path.join(tmp, d)) and d != "__MACOSX"]
                if not extracted:
                    raise RuntimeError("archive had no top-level folder")
                new_root = os.path.join(tmp, extracted[0])

                # back up the current install (single-slot rollback)
                if os.path.exists(BACKUP_DIR):
                    shutil.rmtree(BACKUP_DIR, ignore_errors=True)
                shutil.copytree(PROJECT_ROOT, BACKUP_DIR,
                                 ignore=shutil.ignore_patterns(".pios_backup"))

                # copy the new tree over the current one, file by file, so
                # a crash partway through still leaves most of the old app intact
                for dirpath, _, filenames in os.walk(new_root):
                    rel = os.path.relpath(dirpath, new_root)
                    dest_dir = os.path.join(PROJECT_ROOT, rel) if rel != "." else PROJECT_ROOT
                    os.makedirs(dest_dir, exist_ok=True)
                    for fname in filenames:
                        shutil.copy2(os.path.join(dirpath, fname),
                                     os.path.join(dest_dir, fname))

            self.status = "Update installed. Restart PiOS to apply."
        except Exception as e:
            self.status = f"Update failed: {e}"

    def _rollback(self):
        if not os.path.isdir(BACKUP_DIR):
            self.status = "No previous version saved to roll back to"
            return
        try:
            for dirpath, _, filenames in os.walk(BACKUP_DIR):
                rel = os.path.relpath(dirpath, BACKUP_DIR)
                dest_dir = os.path.join(PROJECT_ROOT, rel) if rel != "." else PROJECT_ROOT
                os.makedirs(dest_dir, exist_ok=True)
                for fname in filenames:
                    shutil.copy2(os.path.join(dirpath, fname),
                                 os.path.join(dest_dir, fname))
            self.status = "Rolled back. Restart PiOS to apply."
        except Exception as e:
            self.status = f"Rollback failed: {e}"

    def draw(self, draw, canvas):
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 40), "System Updater", font=FONT_LG,
                   fill=(255, 255, 255), anchor="mm")
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 74),
                   f"Current version: {_current_version()}", font=FONT_SM,
                   fill=(170, 170, 180), anchor="mm")
        if self.status:
            draw.text((SCREEN_W // 2, SCREEN_H - 110), self.status, font=FONT_SM,
                       fill=ACCENT, anchor="mm", align="center")
        for b in self.buttons:
            b.draw(draw)
