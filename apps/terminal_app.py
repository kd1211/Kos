"""
Terminal -- a minimal shell prompt with the on-screen Keyboard.

Runs each entered line as a real shell command (via subprocess) in the
user's home directory, capturing stdout+stderr, and scrolls the last N
lines of combined history in a monospace-ish view. `cd` is handled
specially (subprocess can't change this process's directory), and `clear`
wipes the local scrollback.

This is intentionally simple -- no job control, no pipes-to-stdin, no
signals -- just enough to poke around the filesystem, check on
processes, or run one-off scripts.
"""

import os
import subprocess

from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, \
    STATUS_BAR_H, FONT_SM, CARD_COLOR, FG_COLOR, ACCENT

KEYBOARD_H = 188
MAX_LINES = 10
LINE_H = 18
MAX_CMD_LEN = 90
HISTORY_LEN = 40


class TerminalApp(App):
    name = "Terminal"
    icon = "\u2328"

    def on_open(self):
        self.cwd = os.path.expanduser("~")
        self.scrollback = [f"PiOS Terminal -- {self.cwd}", ""]
        self.draft = ""
        self.history = []
        self.hist_index = None
        self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
        self.buttons = [
            Button(16, STATUS_BAR_H + 4, 70, 30, "Clear", self._clear, font=FONT_SM),
            Button(SCREEN_W - 96, STATUS_BAR_H + 4, 80, 30, "Home",
                   self.os.go_home, font=FONT_SM),
        ]

    def _clear(self):
        self.scrollback = [f"{self.cwd}"]

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft = self.draft[:-1]
        elif val == "ENTER":
            self._run()
        elif len(self.draft) < MAX_CMD_LEN:
            self.draft += val

    def on_tap(self, x, y):
        if self.keyboard.on_tap(x, y, self._on_key):
            return True
        return super().on_tap(x, y)

    def _run(self):
        cmd = self.draft.strip()
        self.draft = ""
        if not cmd:
            return
        self.history.append(cmd)
        self.history = self.history[-HISTORY_LEN:]
        self.hist_index = None
        self.scrollback.append(f"$ {cmd}")

        if cmd == "clear":
            self._clear()
            return

        if cmd.startswith("cd"):
            target = cmd[2:].strip() or os.path.expanduser("~")
            new_dir = os.path.abspath(os.path.join(self.cwd, os.path.expanduser(target)))
            if os.path.isdir(new_dir):
                self.cwd = new_dir
            else:
                self.scrollback.append(f"cd: no such directory: {target}")
            return

        try:
            result = subprocess.run(
                cmd, shell=True, cwd=self.cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=15, text=True)
            out = result.stdout or ""
        except subprocess.TimeoutExpired:
            out = "[command timed out after 15s]"
        except Exception as e:
            out = f"[error: {e}]"

        for line in out.splitlines() or [""]:
            self.scrollback.append(line)
        self.scrollback = self.scrollback[-300:]

    def draw(self, draw, canvas):
        for b in self.buttons:
            b.draw(draw)

        top = STATUS_BAR_H + 40
        console_bottom = self.keyboard.y - 34
        draw.rounded_rectangle([8, top, SCREEN_W - 8, console_bottom],
                                radius=8, fill=(8, 8, 10))

        visible_h = console_bottom - top - 8
        max_lines = max(1, visible_h // LINE_H)
        lines = self.scrollback[-max_lines:]
        y = top + 6
        for line in lines:
            draw.text((14, y), line[:44], font=FONT_SM, fill=(120, 230, 140), anchor="lm")
            y += LINE_H

        # prompt line just above the keyboard
        prompt_y = console_bottom + 16
        prompt = f"{os.path.basename(self.cwd) or '/'} $ {self.draft}"
        draw.rounded_rectangle([8, prompt_y - 14, SCREEN_W - 8, prompt_y + 14],
                                radius=8, fill=CARD_COLOR)
        draw.text((16, prompt_y), prompt[-46:], font=FONT_SM, fill=ACCENT, anchor="lm")

        self.keyboard.draw(draw)
