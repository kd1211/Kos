"""
Messages -- a PictoChat-style local chat: four broadcast rooms (A/B/C/D,
same naming as the DSi/DS original), no accounts, no server, no 1:1 DMs
-- everyone on the same Wi-Fi with the room open sees the same feed.
Compose a message by drawing on a small canvas, typing text, or both
together, exactly like the original let you combine handwriting and a
keyboard in one message.

Protocol (deliberately tiny, UDP broadcast only -- true to the
original's "just shout it on the local network" simplicity):
  - Presence: UDP broadcast on ANNOUNCE_PORT, payload
    "KOS_HELLO:<device name>", every ~3s, purely to show a "N nearby"
    hint -- there's no peer list or DM screen anymore.
  - Chat: UDP broadcast on MSG_PORT, one JSON object per message:
        {"id": "<random hex>", "room": "A", "name": "...",
         "text": "...", "img": "<base64 PNG or null>", "ts": <float>}
    Every Kos device (and the companion/kos_chat_companion.py desktop
    app for people without one) listens on MSG_PORT and appends
    anything for a room it's displaying. Messages are de-duplicated by
    id (a broadcast can legitimately arrive more than once, including
    a device's own message looping back to itself) and kept in memory
    only -- there's no history across a reboot, same as the original.
"""

import base64
import io
import json
import os
import secrets
import socket
import threading
import time

from PIL import Image, ImageDraw
from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, \
    STATUS_BAR_H, FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT, FG_COLOR
from ui import notifications

ANNOUNCE_PORT = 50210
MSG_PORT = 50212
PEER_TIMEOUT = 12
HISTORY_LIMIT = 40
MAX_TEXT_LEN = 120
SEEN_IDS_CAP = 300

ROOMS = ["A", "B", "C", "D"]
DOODLE_W, DOODLE_H = 280, 64
PAPER_COLOR = (250, 250, 250)
INK_COLOR = (30, 30, 40)

TABS_TOP = STATUS_BAR_H
TABS_H = 34
FEED_TOP = TABS_TOP + TABS_H
COMPOSE_H = 214
FEED_BOTTOM = SCREEN_H - COMPOSE_H
COMPOSE_TOOLBAR_H = 34
ROW_H = 62

_device_name = f"Kos-{socket.gethostname()}"


def _encode_doodle(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _decode_doodle(data_b64):
    try:
        raw = base64.b64decode(data_b64)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None


class _Networking:
    """Background threads shared across app opens (so the feed and
    presence survive navigating away and back). Created lazily, once,
    at module scope."""

    def __init__(self):
        self.peers = {}                          # ip -> {"name","last_seen"}
        self.rooms = {r: [] for r in ROOMS}       # room -> [msg dict, ...]
        self.lock = threading.Lock()
        self._seen_ids = set()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_messages_loop, daemon=True).start()

    def _announce_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = f"KOS_HELLO:{_device_name}".encode()
        while True:
            try:
                sock.sendto(payload, ("255.255.255.255", ANNOUNCE_PORT))
            except Exception:
                pass
            time.sleep(3)

    def _listen_announce_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", ANNOUNCE_PORT))
        except Exception:
            return
        while True:
            try:
                data, (ip, _) = sock.recvfrom(256)
                text = data.decode(errors="ignore")
                if text.startswith("KOS_HELLO:"):
                    name = text.split(":", 1)[1]
                    with self.lock:
                        self.peers[ip] = {"name": name, "last_seen": time.time()}
            except Exception:
                time.sleep(0.5)

    def _listen_messages_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", MSG_PORT))
        except Exception:
            return
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
                self._handle_packet(data)
            except Exception:
                time.sleep(0.2)

    def _handle_packet(self, data):
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            return
        mid = msg.get("id")
        room = msg.get("room")
        if not mid or room not in ROOMS:
            return
        with self.lock:
            if mid in self._seen_ids:
                return
            if len(self._seen_ids) > SEEN_IDS_CAP:
                self._seen_ids.clear()
            self._seen_ids.add(mid)
            is_mine = msg.get("name") == _device_name
            self.rooms[room].append(msg)
            del self.rooms[room][:-HISTORY_LIMIT]
        if not is_mine:
            preview = msg.get("text") or "[drawing]"
            notifications.post(f"New in Room {room}", f"{msg.get('name','?')}: {preview}",
                                source="Messages")

    def send_message(self, room, text, doodle_img):
        mid = secrets.token_hex(8)
        img_b64 = _encode_doodle(doodle_img) if doodle_img is not None else None
        msg = {"id": mid, "room": room, "name": _device_name,
               "text": text or "", "img": img_b64, "ts": time.time()}
        # local echo first, so sending feels instant even before the
        # broadcast round-trips back (if it ever does -- see module docstring)
        with self.lock:
            self._seen_ids.add(mid)
            self.rooms[room].append(msg)
            del self.rooms[room][:-HISTORY_LIMIT]
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(json.dumps(msg).encode("utf-8"), ("255.255.255.255", MSG_PORT))
            sock.close()
            return True
        except Exception:
            return False

    def nearby_count(self):
        now = time.time()
        with self.lock:
            return sum(1 for p in self.peers.values() if now - p["last_seen"] < PEER_TIMEOUT)

    def room_history(self, room):
        with self.lock:
            return list(self.rooms.get(room, []))


_net = _Networking()


class MessagesApp(App):
    name = "Messages"
    icon = "\U0001F4AC"

    def on_open(self):
        _net.start()
        self.room = "A"
        self.compose_mode = "draw"      # draw | type
        self.draft_text = ""
        self.canvas_img = Image.new("RGB", (DOODLE_W, DOODLE_H), PAPER_COLOR)
        self.canvas_draw = ImageDraw.Draw(self.canvas_img)
        self.canvas_dirty = False
        self._last_point = None
        self.keyboard = Keyboard(4, FEED_BOTTOM + COMPOSE_TOOLBAR_H + 24,
                                  SCREEN_W - 8, COMPOSE_H - COMPOSE_TOOLBAR_H - 28)
        self.status = None
        self._doodle_thumb_cache = {}
        self._build_buttons()

    @property
    def wants_animation(self):
        return True  # a broadcast from someone else can arrive at any time

    def _build_buttons(self):
        self.buttons = []
        tab_w = SCREEN_W // len(ROOMS)
        for i, r in enumerate(ROOMS):
            self.buttons.append(
                Button(i * tab_w, TABS_TOP, tab_w, TABS_H, f"Room {r}",
                       (lambda r=r: self._switch_room(r)), font=FONT_SM))

        ty = FEED_BOTTOM
        third = SCREEN_W // 3
        self.buttons.append(
            Button(0, ty, third, COMPOSE_TOOLBAR_H,
                   "\u270F Draw" if self.compose_mode == "type" else "\u2328 Type",
                   self._toggle_compose_mode, font=FONT_SM))
        self.buttons.append(
            Button(third, ty, third, COMPOSE_TOOLBAR_H, "Clear",
                   self._clear_compose, font=FONT_SM))
        self.buttons.append(
            Button(2 * third, ty, third, COMPOSE_TOOLBAR_H, "Send",
                   self._send, font=FONT_SM, bg=ACCENT))

    def _switch_room(self, r):
        self.room = r
        self.status = None

    def _toggle_compose_mode(self):
        self.compose_mode = "type" if self.compose_mode == "draw" else "draw"
        self._build_buttons()

    def _clear_compose(self):
        if self.compose_mode == "draw":
            self.canvas_draw.rectangle([0, 0, DOODLE_W, DOODLE_H], fill=PAPER_COLOR)
            self.canvas_dirty = False
        else:
            self.draft_text = ""

    def _has_doodle_content(self):
        return self.canvas_dirty

    def _send(self):
        text = self.draft_text.strip()
        doodle = self.canvas_img.copy() if self._has_doodle_content() else None
        if not text and doodle is None:
            self.status = "Nothing to send - draw or type something first"
            return
        _net.send_message(self.room, text, doodle)
        self.draft_text = ""
        self.canvas_draw.rectangle([0, 0, DOODLE_W, DOODLE_H], fill=PAPER_COLOR)
        self.canvas_dirty = False
        self.status = None

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft_text = self.draft_text[:-1]
        elif val == "ENTER":
            self._send()
        elif len(self.draft_text) < MAX_TEXT_LEN:
            self.draft_text += val

    # -- touch handling -------------------------------------------------------
    def on_tap(self, x, y):
        if self.compose_mode == "type" and self.keyboard.on_tap(x, y, self._on_key):
            return True
        if super().on_tap(x, y):
            return True
        if self.compose_mode == "draw" and self._in_canvas(x, y):
            self._last_point = None
            self._draw_at(x, y)
            return True
        return False

    def _in_canvas(self, x, y):
        cx0, cy0 = self._canvas_origin()
        return cx0 <= x <= cx0 + DOODLE_W and cy0 <= y <= cy0 + DOODLE_H

    def _canvas_origin(self):
        cx0 = (SCREEN_W - DOODLE_W) // 2
        cy0 = FEED_BOTTOM + COMPOSE_TOOLBAR_H + 6
        return cx0, cy0

    def _draw_at(self, x, y):
        cx0, cy0 = self._canvas_origin()
        lx, ly = x - cx0, y - cy0
        if self._last_point is not None:
            self.canvas_draw.line([self._last_point, (lx, ly)], fill=INK_COLOR, width=3)
        self.canvas_draw.ellipse([lx - 2, ly - 2, lx + 2, ly + 2], fill=INK_COLOR)
        self._last_point = (lx, ly)
        self.canvas_dirty = True

    def on_touch_move(self, x, y):
        if self.compose_mode == "draw" and self._in_canvas(x, y):
            self._draw_at(x, y)
        else:
            self._last_point = None

    def on_touch_up(self):
        self._last_point = None

    # -- drawing --------------------------------------------------------------
    def draw(self, draw, canvas):
        for b in self.buttons[:len(ROOMS)]:
            active = (b.label == f"Room {self.room}")
            draw.rectangle([b.x, b.y, b.x + b.w - 1, b.y + b.h], fill=ACCENT if active else CARD_COLOR)
            draw.text((b.x + b.w // 2, b.y + b.h // 2), b.label, font=FONT_SM,
                       fill=(255, 255, 255), anchor="mm")

        nearby = _net.nearby_count()
        if nearby:
            draw.text((SCREEN_W - 8, FEED_TOP + 12), f"{nearby} nearby", font=FONT_SM,
                       fill=(140, 140, 150), anchor="rm")

        self._draw_feed(draw, canvas)

        draw.rectangle([0, FEED_BOTTOM, SCREEN_W, SCREEN_H], fill=(18, 18, 22))
        for b in self.buttons[len(ROOMS):]:
            b.draw(draw)

        if self.compose_mode == "draw":
            cx0, cy0 = self._canvas_origin()
            draw.rectangle([cx0 - 2, cy0 - 2, cx0 + DOODLE_W + 2, cy0 + DOODLE_H + 2],
                            outline=(90, 90, 100), width=2)
            canvas.paste(self.canvas_img, (cx0, cy0))
            if self.draft_text:
                draw.text((SCREEN_W // 2, cy0 + DOODLE_H + 16), f'+ "{self.draft_text[:30]}"',
                           font=FONT_SM, fill=(160, 160, 170), anchor="mm")
        else:
            ty = FEED_BOTTOM + COMPOSE_TOOLBAR_H + 4
            draw.rounded_rectangle([16, ty, SCREEN_W - 16, ty + 20], radius=6, fill=CARD_COLOR)
            draw.text((24, ty + 10), self.draft_text[-40:] or "Type a message...",
                       font=FONT_SM, fill=FG_COLOR if self.draft_text else (140, 140, 150), anchor="lm")
            self.keyboard.draw(draw)

        if self.status:
            draw.rounded_rectangle([SCREEN_W // 2 - 130, FEED_BOTTOM - 26,
                                     SCREEN_W // 2 + 130, FEED_BOTTOM - 4], radius=8, fill=(0, 0, 0))
            draw.text((SCREEN_W // 2, FEED_BOTTOM - 15), self.status, font=FONT_SM,
                       fill=(230, 130, 130), anchor="mm")

    def _draw_feed(self, draw, canvas):
        history = _net.room_history(self.room)
        draw.rectangle([0, FEED_TOP, SCREEN_W, FEED_BOTTOM], fill=(12, 12, 16))
        if not history:
            draw.text((SCREEN_W // 2, (FEED_TOP + FEED_BOTTOM) // 2),
                       f"No messages in Room {self.room} yet", font=FONT_SM,
                       fill=(120, 120, 130), anchor="mm")
            return

        visible_rows = (FEED_BOTTOM - FEED_TOP) // ROW_H
        shown = history[-visible_rows:]
        y = FEED_TOP + 4
        for msg in shown:
            mine = msg.get("name") == _device_name
            name = "Me" if mine else msg.get("name", "?")
            draw.text((10, y), name, font=FONT_SM, fill=ACCENT if mine else (200, 200, 210),
                       anchor="lt")
            row_y = y + 16
            img_b64 = msg.get("img")
            if img_b64:
                thumb = self._thumb_for(msg["id"], img_b64)
                if thumb is not None:
                    canvas.paste(thumb, (10, row_y))
                    if msg.get("text"):
                        draw.text((10 + thumb.width + 8, row_y + thumb.height // 2),
                                   msg["text"][:26], font=FONT_SM, fill=(210, 210, 220), anchor="lm")
            elif msg.get("text"):
                draw.text((10, row_y + 8), msg["text"][:44], font=FONT_SM,
                           fill=(210, 210, 220), anchor="lm")
            y += ROW_H

    def _thumb_for(self, msg_id, img_b64):
        if msg_id in self._doodle_thumb_cache:
            return self._doodle_thumb_cache[msg_id]
        img = _decode_doodle(img_b64)
        if img is not None:
            scale = 0.32
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        if len(self._doodle_thumb_cache) > 60:
            self._doodle_thumb_cache.clear()
        self._doodle_thumb_cache[msg_id] = img
        return img
