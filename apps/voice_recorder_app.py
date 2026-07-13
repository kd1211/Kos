"""
Voice Recorder -- records via `arecord` (drivers/audio_recorder.py) and
plays recordings back through the same pygame mixer Music already uses
(ui/sound.py's play_music), so a .wav voice note is just another audio
file as far as playback is concerned.

A microphone is optional hardware, so this degrades the same way
Camera and Wi-Fi/Bluetooth do: if arecord isn't installed or there's no
input device, the app still opens and just says so.
"""

import os
import time
import wave
from ui import sound
from ui.framework import App, Button, ScrollArea, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT
from drivers.audio_recorder import AudioRecorder

RECORDINGS_DIR = os.path.expanduser("~/Recordings")
LIST_TOP = STATUS_BAR_H + 44
LIST_BOTTOM = SCREEN_H - 110
ROW_H = 56


def _duration_str(path):
    try:
        with wave.open(path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 1
            secs = frames / float(rate)
            return f"{int(secs) // 60}:{int(secs) % 60:02d}"
    except Exception:
        return "--:--"


class VoiceRecorderApp(App):
    name = "Voice Recorder"
    icon = "\U0001F3A4"

    def on_open(self):
        self.recorder = AudioRecorder()
        self.mode = "list"          # list | recording
        self.playing_path = None
        self.status = None
        self.scroll = ScrollArea(0, LIST_TOP, SCREEN_W, LIST_BOTTOM - LIST_TOP)
        self._press_row = None
        self._press_start = None
        self._load_recordings()
        self._build_buttons()

    def on_close(self):
        if self.recorder.is_recording():
            self.recorder.stop()
        sound.stop_music()

    @property
    def wants_animation(self):
        return self.mode == "recording" or (self.playing_path is not None and sound.is_music_playing())

    def _load_recordings(self):
        try:
            names = sorted(f for f in os.listdir(RECORDINGS_DIR) if f.lower().endswith(".wav"))
            names.reverse()  # newest first (timestamped filenames sort chronologically)
        except Exception:
            names = []
        self.recordings = names
        self.scroll.offset = 0
        self.scroll.set_content_height(len(names) * ROW_H)

    def _build_buttons(self):
        if not self.recorder.available:
            self.buttons = [Button(SCREEN_W // 2 - 60, SCREEN_H - 60, 120, 42,
                                    "Home", self.os.go_home, font=FONT_SM)]
            return
        if self.mode == "recording":
            self.buttons = [
                Button(SCREEN_W // 2 - 60, SCREEN_H - 100, 120, 60, "Stop",
                       self._stop_recording, font=FONT_MD, bg=(180, 60, 60)),
            ]
            return
        self.buttons = [
            Button(SCREEN_W // 2 - 44, SCREEN_H - 60, 88, 44, "\u25CF Record",
                   self._start_recording, font=FONT_SM, bg=(180, 60, 60)),
            Button(16, SCREEN_H - 60, 60, 44, "Home", self.os.go_home, font=FONT_SM),
        ]

    # -- recording --------------------------------------------------------
    def _start_recording(self):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        fname = f"recording_{time.strftime('%Y%m%d_%H%M%S')}.wav"
        path = os.path.join(RECORDINGS_DIR, fname)
        if self.recorder.start(path):
            self.mode = "recording"
            self._build_buttons()
        else:
            self.status = "Couldn't start recording"

    def _stop_recording(self):
        self.recorder.stop()
        self.mode = "list"
        self.status = "Recording saved"
        self._load_recordings()
        self._build_buttons()

    # -- playback -----------------------------------------------------------
    def _toggle_play(self, name):
        path = os.path.join(RECORDINGS_DIR, name)
        if self.playing_path == path and sound.is_music_playing():
            sound.stop_music()
            self.playing_path = None
        else:
            if sound.play_music(path):
                self.playing_path = path
            else:
                self.status = "Couldn't play recording"

    def _delete_recording(self, name):
        path = os.path.join(RECORDINGS_DIR, name)
        if self.playing_path == path:
            sound.stop_music()
            self.playing_path = None
        try:
            os.remove(path)
        except Exception:
            pass
        self._load_recordings()

    # -- list scroll dispatch ------------------------------------------------
    def on_tap(self, x, y):
        if not self.recorder.available or self.mode == "recording":
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
            idx = int(content_y // ROW_H)
            if 0 <= idx < len(self.recordings):
                # the right-hand third of a row is the delete button
                local_x = x
                if local_x > SCREEN_W - 56:
                    self._press_row = ("delete", self.recordings[idx])
                else:
                    self._press_row = ("play", self.recordings[idx])
        return True

    def on_touch_move(self, x, y):
        if not self.recorder.available or self.mode == "recording" or self._press_start is None:
            return
        self.scroll.drag_to(y)

    def on_touch_up(self):
        if not self.recorder.available or self.mode == "recording":
            return
        self.scroll.end_drag()
        if not self.scroll.was_drag() and self._press_row is not None:
            kind, name = self._press_row
            if kind == "play":
                self._toggle_play(name)
            else:
                self._delete_recording(name)
        self._press_row = None
        self._press_start = None

    # -- drawing --------------------------------------------------------------
    def draw(self, draw, canvas):
        if not self.recorder.available:
            draw.text((SCREEN_W // 2, SCREEN_H // 2 - 30), "\U0001F3A4", font=FONT_LG,
                       fill=(120, 120, 130), anchor="mm")
            draw.text((SCREEN_W // 2, SCREEN_H // 2 + 10), "No microphone available",
                       font=FONT_MD, fill=(200, 200, 210), anchor="mm")
            draw.text((SCREEN_W // 2, SCREEN_H // 2 + 34), "arecord isn't installed",
                       font=FONT_SM, fill=(140, 140, 150), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            return

        if self.mode == "recording":
            elapsed = self.recorder.elapsed()
            mm, ss = int(elapsed) // 60, int(elapsed) % 60
            draw.ellipse([SCREEN_W // 2 - 50, 140, SCREEN_W // 2 + 50, 240], fill=(180, 30, 30))
            draw.text((SCREEN_W // 2, 190), "\U0001F3A4", font=FONT_LG, fill=(255, 255, 255),
                       anchor="mm")
            draw.text((SCREEN_W // 2, 280), f"{mm}:{ss:02d}", font=FONT_LG,
                       fill=(255, 255, 255), anchor="mm")
            draw.text((SCREEN_W // 2, 316), "Recording\u2026", font=FONT_SM,
                       fill=(200, 200, 210), anchor="mm")
            for b in self.buttons:
                b.draw(draw)
            return

        draw.text((SCREEN_W // 2, STATUS_BAR_H + 20), "Voice Recorder", font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")

        if self.status:
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 38), self.status, font=FONT_SM,
                       fill=(150, 220, 150), anchor="mm")

        if not self.recordings:
            draw.text((SCREEN_W // 2, LIST_TOP + 100), "No recordings yet", font=FONT_SM,
                       fill=(150, 150, 160), anchor="mm")
        else:
            for i, name in enumerate(self.recordings):
                ry = i * ROW_H
                sy = self.scroll.y + (ry - self.scroll.offset)
                if sy + ROW_H < self.scroll.y or sy > self.scroll.y + self.scroll.h:
                    continue
                path = os.path.join(RECORDINGS_DIR, name)
                playing = (self.playing_path == path and sound.is_music_playing())
                bg = ACCENT if playing else CARD_COLOR
                draw.rounded_rectangle([16, sy, SCREEN_W - 16, sy + ROW_H - 8], radius=10, fill=bg)
                label = name.replace("recording_", "").replace(".wav", "")
                icon = "\u23F8" if playing else "\u25B6"
                draw.text((30, sy + 16), f"{icon}  {label}", font=FONT_SM,
                           fill=(255, 255, 255), anchor="lm")
                draw.text((30, sy + 36), _duration_str(path), font=FONT_SM,
                           fill=(220, 220, 230) if playing else (160, 160, 170), anchor="lm")
                draw.text((SCREEN_W - 34, sy + (ROW_H - 8) // 2), "\U0001F5D1", font=FONT_SM,
                           fill=(230, 130, 130), anchor="mm")
            self.scroll.draw_scrollbar(draw, ACCENT)

        for b in self.buttons:
            b.draw(draw)
