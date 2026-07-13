"""
Music -- a minimal audio player.

Plays anything pygame's mixer can decode (mp3/ogg/wav) from ~/Music
(create the folder and drop files in). Uses ui/sound.py so it shares
the same master volume as the rest of Kos -- turning volume down in
Settings turns the music down too.
"""

import os

from ui import theme, sound
from ui.framework import App, Button, SCREEN_W, SCREEN_H, STATUS_BAR_H, \
    FONT_MD, FONT_SM, FONT_LG

MUSIC_DIR = os.path.expanduser("~/Music")
EXTENSIONS = (".mp3", ".ogg", ".wav")
ROW_H = 38
PAGE_SIZE = 4

LIST_TOP = STATUS_BAR_H + 40
LIST_BOTTOM = LIST_TOP + PAGE_SIZE * ROW_H
FOOTER_Y = LIST_BOTTOM + 12
TRANSPORT_Y = FOOTER_Y + 48
NOW_PLAYING_Y = TRANSPORT_Y + 60
VOL_Y = NOW_PLAYING_Y + 18
HOME_Y = SCREEN_H - 56


class MusicApp(App):
    name = "Music"
    icon = "\U0001F3B5"

    def on_open(self):
        self.page = 0
        self.playing_index = None
        self.paused = False
        self._scan()
        self._build_buttons()

    def on_close(self):
        # this is a single-screen OS with no background task model, so
        # leaving the app cleanly stops playback rather than leaving a
        # track running invisibly
        sound.stop_music()

    def _scan(self):
        self.tracks = []
        if os.path.isdir(MUSIC_DIR):
            self.tracks = sorted(
                f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(EXTENSIONS))

    def _build_buttons(self):
        self.buttons = []
        start = self.page * PAGE_SIZE
        page_tracks = self.tracks[start:start + PAGE_SIZE]
        for i, name in enumerate(page_tracks):
            y = LIST_TOP + i * ROW_H
            idx = start + i
            label = ("\u25B6 " if idx == self.playing_index else "") + name
            self.buttons.append(
                Button(16, y, SCREEN_W - 32, ROW_H - 6, label,
                       self._play(idx), font=FONT_SM))

        total_pages = max(1, (len(self.tracks) + PAGE_SIZE - 1) // PAGE_SIZE)
        self._total_pages = total_pages
        self.buttons.append(Button(16, FOOTER_Y, 60, 34, "Prev", self._prev_page, font=FONT_SM))
        self.buttons.append(Button(84, FOOTER_Y, 60, 34, "Next", self._next_page, font=FONT_SM))

        w = (SCREEN_W - 16 * 2 - 8 * 2) // 3
        self.buttons.append(Button(16, TRANSPORT_Y, w, 42,
                                    "\u23EE", self._prev_track, font=FONT_MD))
        self.buttons.append(Button(16 + w + 8, TRANSPORT_Y, w, 42,
                                    self._play_pause_label(), self._toggle_play, font=FONT_MD))
        self.buttons.append(Button(16 + (w + 8) * 2, TRANSPORT_Y, w, 42,
                                    "\u23ED", self._next_track, font=FONT_MD))

        self.buttons.append(Button(30, VOL_Y, 60, 40, "Vol -", self._adjust_volume(-10), font=FONT_SM))
        self.buttons.append(Button(SCREEN_W - 90, VOL_Y, 60, 40, "Vol +", self._adjust_volume(10), font=FONT_SM))
        self.buttons.append(Button(SCREEN_W // 2 - 60, HOME_Y, 120, 42,
                                    "Home", self.os.go_home, font=FONT_SM))

    def _play_pause_label(self):
        if self.playing_index is None:
            return "\u25B6"
        return "\u25B6" if self.paused else "\u23F8"

    def _prev_page(self):
        if self.page > 0:
            self.page -= 1
            self._build_buttons()

    def _next_page(self):
        if (self.page + 1) * PAGE_SIZE < len(self.tracks):
            self.page += 1
            self._build_buttons()

    def _play(self, idx):
        def handler():
            name = self.tracks[idx]
            if sound.play_music(os.path.join(MUSIC_DIR, name)):
                self.playing_index = idx
                self.paused = False
            self._build_buttons()
        return handler

    def _toggle_play(self):
        if self.playing_index is None:
            if self.tracks:
                self._play(0)()
            return
        if self.paused:
            sound.resume_music()
            self.paused = False
        else:
            sound.pause_music()
            self.paused = True
        self._build_buttons()

    def _prev_track(self):
        if self.playing_index is not None and self.tracks:
            self._play((self.playing_index - 1) % len(self.tracks))()

    def _next_track(self):
        if self.playing_index is not None and self.tracks:
            self._play((self.playing_index + 1) % len(self.tracks))()

    def _adjust_volume(self, delta):
        def handler():
            v = max(0, min(100, theme.get("volume") + delta))
            theme.set("volume", v)
            sound.refresh_volume()
        return handler

    def draw(self, draw, canvas):
        fg, accent = theme.fg_color(), theme.accent_color()
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 16), "Music", font=FONT_LG,
                   fill=fg, anchor="mm")

        if not self.tracks:
            draw.text((SCREEN_W // 2, SCREEN_H // 2 - 60),
                       f"No audio files found.\nAdd .mp3/.ogg/.wav files to\n{MUSIC_DIR}",
                       font=FONT_SM, fill=(180, 180, 190), anchor="mm", align="center")

        for b in self.buttons:
            b.draw(draw)

        if self.playing_index is not None and self.playing_index < len(self.tracks):
            now_playing = self.tracks[self.playing_index]
            status = "Paused" if self.paused else "Playing"
            draw.text((SCREEN_W // 2, NOW_PLAYING_Y), f"{status}: {now_playing}",
                       font=FONT_SM, fill=accent, anchor="mm")

        draw.text((SCREEN_W // 2, VOL_Y + 20), f"{theme.get('volume')}%",
                   font=FONT_SM, fill=(150, 150, 160), anchor="mm")
        draw.text((SCREEN_W // 2, FOOTER_Y - 8),
                   f"Page {self.page + 1}/{self._total_pages}", font=FONT_SM,
                   fill=(120, 120, 130), anchor="mm")
