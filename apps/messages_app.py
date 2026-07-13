"""
Messages -- peer-to-peer chat + file transfer over the local Wi-Fi
network. No server, no accounts: every Kos device broadcasts its
presence over UDP and any other Kos device on the same LAN can see it
and start a text chat or send it a file directly over TCP.

Protocol (deliberately tiny):
  - UDP broadcast on ANNOUNCE_PORT, payload "KOS_HELLO:<device name>",
    every ~3s. Anyone who hears one records/refreshes that peer.
  - TCP on CHAT_PORT, one connection per message. First line is either
        MSG <utf8 text>
        FILE <filename> <size_bytes>\n<raw bytes...>
    Files land in ~/Downloads.
"""

import os
import socket
import threading
import time

from ui.framework import App, Button, Keyboard, SCREEN_W, SCREEN_H, \
    STATUS_BAR_H, FONT_SM, FONT_MD, FONT_LG, CARD_COLOR, ACCENT, FG_COLOR
from ui import notifications

ANNOUNCE_PORT = 50210
CHAT_PORT = 50211
PEER_TIMEOUT = 12
KEYBOARD_H = 188
DOWNLOADS_DIR = os.path.expanduser("~/Downloads")

_device_name = f"Kos-{socket.gethostname()}"


class _Networking:
    """Background threads shared across app opens (so peers/history survive
    navigating away and back). Created lazily, once, at module scope."""

    def __init__(self):
        self.peers = {}          # ip -> {"name": str, "last_seen": float}
        self.chats = {}          # ip -> [("me"/"them", text)]
        self.lock = threading.Lock()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_announce_loop, daemon=True).start()
        threading.Thread(target=self._listen_chat_loop, daemon=True).start()

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

    def _listen_chat_loop(self):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("", CHAT_PORT))
            srv.listen(5)
        except Exception:
            return
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        while True:
            try:
                conn, (ip, _) = srv.accept()
                header = b""
                while not header.endswith(b"\n"):
                    chunk = conn.recv(1)
                    if not chunk:
                        break
                    header += chunk
                header = header.decode(errors="ignore").strip()

                if header.startswith("MSG "):
                    text = header[4:]
                    with self.lock:
                        self.chats.setdefault(ip, []).append(("them", text))
                    sender = self.peers.get(ip, {}).get("name", ip)
                    notifications.post(f"Message from {sender}", text, source="Messages")
                elif header.startswith("FILE "):
                    _, fname, size_s = (header.split(" ", 2) + ["", "0"])[:3]
                    size = int(size_s) if size_s.isdigit() else 0
                    data = b""
                    while len(data) < size:
                        chunk = conn.recv(min(4096, size - len(data)))
                        if not chunk:
                            break
                        data += chunk
                    safe_name = os.path.basename(fname) or "received_file"
                    with open(os.path.join(DOWNLOADS_DIR, safe_name), "wb") as f:
                        f.write(data)
                    with self.lock:
                        self.chats.setdefault(ip, []).append(
                            ("them", f"[sent a file: {safe_name}]"))
                    sender = self.peers.get(ip, {}).get("name", ip)
                    notifications.post(f"File from {sender}", safe_name, source="Messages")
                conn.close()
            except Exception:
                time.sleep(0.2)

    def send_text(self, ip, text):
        try:
            with socket.create_connection((ip, CHAT_PORT), timeout=5) as s:
                s.sendall(f"MSG {text}\n".encode())
            with self.lock:
                self.chats.setdefault(ip, []).append(("me", text))
            return True
        except Exception:
            return False

    def send_file(self, ip, path):
        try:
            size = os.path.getsize(path)
            with socket.create_connection((ip, CHAT_PORT), timeout=10) as s:
                header = f"FILE {os.path.basename(path)} {size}\n".encode()
                s.sendall(header)
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        s.sendall(chunk)
            with self.lock:
                self.chats.setdefault(ip, []).append(
                    ("me", f"[sent a file: {os.path.basename(path)}]"))
            return True
        except Exception:
            return False

    def live_peers(self):
        now = time.time()
        with self.lock:
            return {ip: p for ip, p in self.peers.items()
                    if now - p["last_seen"] < PEER_TIMEOUT}


_net = _Networking()


class MessagesApp(App):
    name = "Messages"
    icon = "\U0001F4AC"

    def on_open(self):
        _net.start()
        self.mode = "peers"
        self.chat_ip = None
        self.draft = ""
        self.file_draft = ""
        self.keyboard = None
        self._build_peer_buttons()

    def _build_peer_buttons(self):
        self.buttons = []
        peers = list(_net.live_peers().items())
        self._peers_cache = peers
        top = STATUS_BAR_H + 50
        for i, (ip, info) in enumerate(peers):
            y = top + i * 46
            self.buttons.append(
                Button(16, y, SCREEN_W - 32, 40, f"{info['name']}  ({ip})",
                       self._open_chat(ip), font=FONT_SM))
        self.buttons.append(
            Button(SCREEN_W // 2 - 60, SCREEN_H - 56, 120, 42,
                   "Home", self.os.go_home, font=FONT_MD))

    def _open_chat(self, ip):
        def handler():
            self.mode = "chat"
            self.chat_ip = ip
            self.draft = ""
            self.keyboard = Keyboard(4, SCREEN_H - KEYBOARD_H, SCREEN_W - 8, KEYBOARD_H - 4)
            self.buttons = [
                Button(10, STATUS_BAR_H + 4, 70, 30, "Peers", self._back_to_peers, font=FONT_SM),
                Button(88, STATUS_BAR_H + 4, 90, 30, "Send File", self._start_file, font=FONT_SM),
                Button(SCREEN_W - 96, STATUS_BAR_H + 4, 80, 30, "Home",
                       self.os.go_home, font=FONT_SM),
            ]
        return handler

    def _back_to_peers(self):
        self.mode = "peers"
        self._build_peer_buttons()

    def _on_key(self, val):
        if val == "BACKSPACE":
            self.draft = self.draft[:-1]
        elif val == "ENTER":
            self._send()
        elif len(self.draft) < 200:
            self.draft += val

    def _send(self):
        if self.draft.strip() and self.chat_ip:
            _net.send_text(self.chat_ip, self.draft.strip())
        self.draft = ""

    def _start_file(self):
        self.mode = "sendfile"
        self.file_draft = os.path.expanduser("~/Pictures/")
        self.buttons = [
            Button(16, STATUS_BAR_H + 92, 90, 34, "Cancel", self._cancel_file, font=FONT_SM),
            Button(SCREEN_W - 106, STATUS_BAR_H + 92, 90, 34, "Send", self._confirm_file, font=FONT_SM),
        ]

    def _cancel_file(self):
        self.mode = "chat"
        self._open_chat(self.chat_ip)()

    def _confirm_file(self):
        path = self.file_draft.strip()
        if path and os.path.isfile(path) and self.chat_ip:
            ok = _net.send_file(self.chat_ip, path)
            if not ok:
                with _net.lock:
                    _net.chats.setdefault(self.chat_ip, []).append(
                        ("me", "[file send failed]"))
        self.mode = "chat"
        self._open_chat(self.chat_ip)()

    def _file_key(self, val):
        if val == "BACKSPACE":
            self.file_draft = self.file_draft[:-1]
        elif val == "ENTER":
            self._confirm_file()
        elif len(self.file_draft) < 200:
            self.file_draft += val

    def on_tap(self, x, y):
        if self.mode in ("chat", "sendfile") and self.keyboard:
            handler = self._file_key if self.mode == "sendfile" else self._on_key
            if self.keyboard.on_tap(x, y, handler):
                return True
        return super().on_tap(x, y)

    def draw(self, draw, canvas):
        if self.mode == "peers":
            self._build_peer_buttons()  # refresh peer liveness each frame
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 22), "Nearby Devices",
                       font=FONT_LG, fill=(255, 255, 255), anchor="mm")
            if not self._peers_cache:
                draw.text((SCREEN_W // 2, SCREEN_H // 2),
                           "Looking for other Kos\ndevices on this Wi-Fi...",
                           font=FONT_SM, fill=(150, 150, 160), anchor="mm", align="center")
            for b in self.buttons:
                b.draw(draw)
            return

        if self.mode == "sendfile":
            draw.text((SCREEN_W // 2, STATUS_BAR_H + 18), "File path to send",
                       font=FONT_MD, fill=(255, 255, 255), anchor="mm")
            draw.rounded_rectangle([16, STATUS_BAR_H + 38, SCREEN_W - 16, STATUS_BAR_H + 78],
                                    radius=10, fill=CARD_COLOR)
            draw.text((24, STATUS_BAR_H + 58), self.file_draft[-40:], font=FONT_SM,
                       fill=FG_COLOR, anchor="lm")
            for b in self.buttons:
                b.draw(draw)
            self.keyboard.draw(draw)
            return

        # chat mode
        name = _net.live_peers().get(self.chat_ip, {}).get("name", self.chat_ip)
        draw.text((SCREEN_W // 2, STATUS_BAR_H + 44), name, font=FONT_MD,
                   fill=(255, 255, 255), anchor="mm")

        history = _net.chats.get(self.chat_ip, [])[-8:]
        y = STATUS_BAR_H + 66
        for who, text in history:
            prefix = "Me: " if who == "me" else ""
            color = ACCENT if who == "me" else FG_COLOR
            draw.text((16, y), (prefix + text)[:44], font=FONT_SM, fill=color, anchor="lm")
            y += 20

        draw_top = self.keyboard.y - 34
        draw.rounded_rectangle([8, draw_top, SCREEN_W - 8, draw_top + 28], radius=8, fill=CARD_COLOR)
        draw.text((16, draw_top + 14), self.draft[-42:] or "Type a message...",
                   font=FONT_SM, fill=FG_COLOR if self.draft else (140, 140, 150), anchor="lm")

        for b in self.buttons:
            b.draw(draw)
        self.keyboard.draw(draw)
