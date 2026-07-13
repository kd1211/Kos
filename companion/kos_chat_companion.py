#!/usr/bin/env python3
"""
Kos Chat Companion -- a standalone desktop client for Kos's Messages
app, for anyone on the same Wi-Fi/LAN who doesn't have (or isn't near)
an actual Kos device but still wants to join the PictoChat-style chat.

Speaks the exact same tiny UDP-broadcast protocol as
apps/messages_app.py on the device itself:
  - Presence: UDP broadcast on ANNOUNCE_PORT, "KOS_HELLO:<name>"
  - Chat: UDP broadcast on MSG_PORT, one JSON object per message --
        {"id": "<random hex>", "room": "A", "name": "...",
         "text": "...", "img": "<base64 PNG or null>", "ts": <float>}
There's no server and no accounts; every copy of this script (and every
Kos device) on the same network segment sees the same four rooms
(A/B/C/D), exactly like the DS/DSi original. Nothing is persisted --
close it and the history is gone, on purpose.

Requirements: Python 3 with tkinter (ships with most Python installs;
on Debian/Ubuntu, `sudo apt install python3-tk` if it's missing) and
Pillow (`pip install pillow`).

Run:
    python3 kos_chat_companion.py
"""

import base64
import io
import json
import secrets
import socket
import threading
import time
import tkinter as tk
from tkinter import simpledialog

from PIL import Image, ImageDraw, ImageTk

ANNOUNCE_PORT = 50210
MSG_PORT = 50212
PEER_TIMEOUT = 12
HISTORY_LIMIT = 40
MAX_TEXT_LEN = 120
SEEN_IDS_CAP = 300
ROOMS = ["A", "B", "C", "D"]

CANVAS_W, CANVAS_H = 280, 64
PAPER_COLOR = "#fafafa"
INK_COLOR = "#1e1e28"


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


class Networking:
    """Same shape as apps/messages_app.py's _Networking, so the two
    interoperate -- this is a from-scratch reimplementation (a desktop
    script can't import from the device's OS package), but the wire
    format has to match exactly."""

    def __init__(self, device_name, on_message=None):
        self.device_name = device_name
        self.on_message = on_message  # callback(room, msg_dict) on new messages
        self.peers = {}
        self.rooms = {r: [] for r in ROOMS}
        self.lock = threading.Lock()
        self._seen_ids = set()
        self._running = True

    def start(self):
        threading.Thread(target=self._announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_messages_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _announce_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = f"KOS_HELLO:{self.device_name}".encode()
        while self._running:
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
        while self._running:
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
        while self._running:
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
            self.rooms[room].append(msg)
            del self.rooms[room][:-HISTORY_LIMIT]
        if self.on_message:
            self.on_message(room, msg)

    def send_message(self, room, text, doodle_img):
        mid = secrets.token_hex(8)
        img_b64 = _encode_doodle(doodle_img) if doodle_img is not None else None
        msg = {"id": mid, "room": room, "name": self.device_name,
               "text": text or "", "img": img_b64, "ts": time.time()}
        with self.lock:
            self._seen_ids.add(mid)
            self.rooms[room].append(msg)
            del self.rooms[room][:-HISTORY_LIMIT]
        if self.on_message:
            self.on_message(room, msg)
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


class ChatApp:
    def __init__(self, root, device_name):
        self.root = root
        self.device_name = device_name
        self.room = "A"
        self._thumb_refs = {}  # keep PhotoImage references alive

        root.title(f"Kos Chat Companion -- {device_name}")
        root.geometry("420x560")
        root.configure(bg="#141418")

        self.net = Networking(device_name, on_message=self._on_message)
        self._build_ui()
        self.net.start()
        self._refresh_feed()
        self._tick_nearby()

    # -- UI construction --------------------------------------------------
    def _build_ui(self):
        tabs = tk.Frame(self.root, bg="#141418")
        tabs.pack(fill="x", pady=(6, 0))
        self.tab_buttons = {}
        for r in ROOMS:
            b = tk.Button(tabs, text=f"Room {r}", relief="flat",
                           bg="#2a2a32", fg="#ccc",
                           activebackground="#3a6fd8", activeforeground="white",
                           command=lambda r=r: self._switch_room(r))
            b.pack(side="left", expand=True, fill="x", padx=2)
            self.tab_buttons[r] = b

        self.nearby_label = tk.Label(self.root, text="", bg="#141418", fg="#888")
        self.nearby_label.pack(anchor="e", padx=8)

        # scrollable feed (classic Tkinter canvas+frame trick)
        feed_container = tk.Frame(self.root, bg="#141418")
        feed_container.pack(fill="both", expand=True, padx=6, pady=6)
        self.feed_canvas = tk.Canvas(feed_container, bg="#0c0c10", highlightthickness=0)
        scrollbar = tk.Scrollbar(feed_container, orient="vertical", command=self.feed_canvas.yview)
        self.feed_inner = tk.Frame(self.feed_canvas, bg="#0c0c10")
        self.feed_inner.bind("<Configure>",
                              lambda e: self.feed_canvas.configure(scrollregion=self.feed_canvas.bbox("all")))
        self._feed_window = self.feed_canvas.create_window((0, 0), window=self.feed_inner, anchor="nw")
        self.feed_canvas.bind("<Configure>", self._on_feed_canvas_configure)
        self.feed_canvas.configure(yscrollcommand=scrollbar.set)
        self.feed_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # compose area: drawing canvas + text entry + buttons
        compose = tk.Frame(self.root, bg="#1a1a20")
        compose.pack(fill="x", padx=6, pady=(0, 6))

        self.draw_canvas = tk.Canvas(compose, width=CANVAS_W, height=CANVAS_H,
                                      bg=PAPER_COLOR, highlightthickness=1,
                                      highlightbackground="#444")
        self.draw_canvas.pack(pady=4)
        self.draw_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.draw_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.draw_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self._doodle_img = Image.new("RGB", (CANVAS_W, CANVAS_H), PAPER_COLOR)
        self._doodle_draw = ImageDraw.Draw(self._doodle_img)
        self._last_xy = None
        self._doodle_dirty = False

        row = tk.Frame(compose, bg="#1a1a20")
        row.pack(fill="x", pady=(0, 4))
        self.text_entry = tk.Entry(row, bg="#2a2a32", fg="#eee",
                                    insertbackground="#eee",
                                    relief="flat", highlightthickness=1,
                                    highlightbackground="#444")
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.text_entry.bind("<Return>", lambda e: self._send())
        tk.Button(row, text="Clear", command=self._clear_compose).pack(side="left", padx=2)
        tk.Button(row, text="Send", command=self._send, bg="#3a6fd8", fg="white").pack(side="left", padx=2)

        self.status_label = tk.Label(self.root, text="", bg="#141418", fg="#e08080")
        self.status_label.pack(pady=(0, 4))

        self._switch_room("A")
        self.root.update_idletasks()

    def _on_feed_canvas_configure(self, event):
        self.feed_canvas.itemconfigure(self._feed_window, width=event.width)

    # -- drawing ------------------------------------------------------------
    def _on_canvas_press(self, event):
        self._last_xy = (event.x, event.y)

    def _on_canvas_drag(self, event):
        if self._last_xy is not None:
            self.draw_canvas.create_line(self._last_xy[0], self._last_xy[1], event.x, event.y,
                                          fill=INK_COLOR, width=3, capstyle="round")
            self._doodle_draw.line([self._last_xy, (event.x, event.y)], fill=INK_COLOR, width=3)
            self._doodle_dirty = True
        self._last_xy = (event.x, event.y)

    def _on_canvas_release(self, event):
        self._last_xy = None

    def _clear_compose(self):
        self.draw_canvas.delete("all")
        self._doodle_draw.rectangle([0, 0, CANVAS_W, CANVAS_H], fill=PAPER_COLOR)
        self._doodle_dirty = False
        self.text_entry.delete(0, tk.END)

    # -- rooms / sending ------------------------------------------------------
    def _switch_room(self, room):
        self.room = room
        for r, b in self.tab_buttons.items():
            b.configure(bg="#3a6fd8" if r == room else "#2a2a32",
                        fg="white" if r == room else "#ccc")
        self._refresh_feed()

    def _send(self):
        text = self.text_entry.get().strip()[:MAX_TEXT_LEN]
        doodle = self._doodle_img.copy() if self._doodle_dirty else None
        if not text and doodle is None:
            self.status_label.configure(text="Nothing to send - draw or type something first")
            return
        self.net.send_message(self.room, text, doodle)
        self.text_entry.delete(0, tk.END)
        self._clear_compose()
        self.status_label.configure(text="")

    def _on_message(self, room, msg):
        # called from a background thread -- hop to the Tk main thread
        self.root.after(0, self._refresh_feed)

    def _tick_nearby(self):
        n = self.net.nearby_count()
        self.nearby_label.configure(text=f"{n} nearby" if n else "")
        self.root.after(2000, self._tick_nearby)

    # -- feed rendering ---------------------------------------------------
    def _refresh_feed(self):
        for w in self.feed_inner.winfo_children():
            w.destroy()
        self._thumb_refs.clear()

        history = self.net.room_history(self.room)
        if not history:
            tk.Label(self.feed_inner, text=f"No messages in Room {self.room} yet",
                     bg="#0c0c10", fg="#666").pack(pady=20)
            return

        for msg in history:
            row = tk.Frame(self.feed_inner, bg="#0c0c10")
            row.pack(fill="x", anchor="w", padx=4, pady=3)
            name = "Me" if msg.get("name") == self.device_name else msg.get("name", "?")
            color = "#6fa8ff" if name == "Me" else "#ddd"
            tk.Label(row, text=name, bg="#0c0c10", fg=color, font=("TkDefaultFont", 9, "bold")) \
                .pack(anchor="w")
            inner = tk.Frame(row, bg="#0c0c10")
            inner.pack(anchor="w", fill="x")
            if msg.get("img"):
                img = _decode_doodle(msg["img"])
                if img is not None:
                    photo = ImageTk.PhotoImage(img)
                    self._thumb_refs[msg["id"]] = photo
                    tk.Label(inner, image=photo, bg="#0c0c10").pack(side="left")
            if msg.get("text"):
                tk.Label(inner, text=msg["text"], bg="#0c0c10", fg="#ccc",
                         wraplength=300, justify="left").pack(side="left", padx=6)

        self.feed_canvas.update_idletasks()
        self.feed_canvas.yview_moveto(1.0)


def main():
    root = tk.Tk()
    root.withdraw()
    name = simpledialog.askstring("Kos Chat Companion", "Your name:",
                                    initialvalue=f"Guest-{secrets.token_hex(2)}", parent=root)
    if not name:
        root.destroy()
        return
    root.deiconify()
    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)
    root.update_idletasks()
    ChatApp(root, name.strip()[:24])
    root.update()
    root.mainloop()


if __name__ == "__main__":
    main()
